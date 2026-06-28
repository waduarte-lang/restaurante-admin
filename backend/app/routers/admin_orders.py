from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from typing import Optional
from datetime import date
import json

from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.menu import MenuItem
from app.models.audit_log import AuditLog
from app.models.payment import Payment
from app.models.domiciliario import Domiciliario
from app.auth.dependencies import admin_only, require_roles
from app.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])


# ── Helpers ─────────────────────────────────────────────────────────────────

def _calc_total(items):
    return sum(i.precio_unitario * i.cantidad for i in items)


def _dom_map(db: Session) -> dict:
    """Devuelve {id: nombre} de todos los domiciliarios."""
    rows = db.query(Domiciliario.id, Domiciliario.nombre).all()
    return {r.id: r.nombre for r in rows}


def _build_order(o: Order, dom: dict = None) -> dict:
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    if dom is not None:
        d["domiciliario_nombre"] = dom.get(o.domiciliario_id) if o.domiciliario_id else None
    else:
        d["domiciliario_nombre"] = o.domiciliario.nombre if o.domiciliario else None
    # Método de pago del primer registro de pago (puede haber split)
    d["metodo_pago"] = o.pagos[0].metodo if o.pagos else None
    d["items"] = [
        {**{c.name: getattr(i, c.name) for c in i.__table__.columns},
         "item_nombre": i.item.nombre if i.item else None}
        for i in o.items
    ]
    return d


def _log(db: Session, user: User, accion: str, order_id: int, detalle: dict):
    entry = AuditLog(
        usuario_id=user.id,
        usuario_nombre=user.nombre,
        accion=accion,
        entidad="comanda",
        entidad_id=order_id,
        detalle=json.dumps(detalle, ensure_ascii=False),
    )
    db.add(entry)


# ── Schemas ─────────────────────────────────────────────────────────────────

class EditItemData(BaseModel):
    precio_unitario: Optional[float] = None
    cantidad: Optional[int] = None
    nota: Optional[str] = None


class AddItemData(BaseModel):
    item_id: int
    cantidad: int = 1
    precio_unitario: Optional[float] = None
    nota: Optional[str] = None


# ── Listado con filtro de fecha ───────────────────────────────────────────────

@router.get("/list")
def list_orders_admin(
    fecha_inicio: Optional[date] = Query(default=None),
    fecha_fin:    Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "cajero", "mesero")),
):
    """Lista todas las comandas con filtro de rango de fechas."""
    try:
        q = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos))
        if fecha_inicio:
            q = q.filter(Order.comanda_fecha >= fecha_inicio.isoformat())
        if fecha_fin:
            q = q.filter(Order.comanda_fecha <= fecha_fin.isoformat())
        orders = q.order_by(Order.comanda_fecha.desc(), Order.comanda_numero.desc()).all()
        dom = _dom_map(db)
        return [_build_order(o, dom) for o in orders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Eliminar comanda (solo admin) ─────────────────────────────────────────────

@router.delete("/{order_id}")
def delete_order_admin(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    """Elimina permanentemente una comanda y renumera las restantes del mismo día."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")
    db.query(Payment).filter(Payment.order_id == order_id).delete()
    db.query(OrderItem).filter(OrderItem.order_id == order_id).delete()
    db.delete(order)
    db.commit()
    return {"ok": True}


# ── Editar campos de la comanda (solo admin) ─────────────────────────────────

class EditOrderData(BaseModel):
    comanda_fecha: Optional[str] = None   # "YYYY-MM-DD"
    comanda_numero: Optional[int] = None
    estado: Optional[str] = None
    total: Optional[float] = None
    domiciliario_id: Optional[int] = None
    valor_domicilio: Optional[float] = None
    mesa_id: Optional[int] = None


@router.put("/{order_id}")
def edit_order_admin(
    order_id: int,
    data: EditOrderData,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "cajero", "mesero")),
):
    """Edita campos de cabecera de una comanda (fecha, estado, total)."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")

    changes: dict = {}
    if data.comanda_numero is not None and data.comanda_numero != order.comanda_numero:
        changes["comanda_numero"] = {"antes": order.comanda_numero, "despues": data.comanda_numero}
        order.comanda_numero = data.comanda_numero
    if data.comanda_fecha is not None:
        from datetime import date as date_type
        nueva_fecha = date_type.fromisoformat(data.comanda_fecha)
        if nueva_fecha != order.comanda_fecha:
            changes["comanda_fecha"] = {"antes": str(order.comanda_fecha), "despues": str(nueva_fecha)}
            order.comanda_fecha = nueva_fecha
    if data.estado is not None and data.estado != order.estado:
        changes["estado"] = {"antes": order.estado, "despues": data.estado}
        order.estado = data.estado
    if data.total is not None and data.total != order.total:
        changes["total"] = {"antes": order.total, "despues": data.total}
        order.total = data.total
    if data.valor_domicilio is not None and data.valor_domicilio != order.valor_domicilio:
        changes["valor_domicilio"] = {"antes": order.valor_domicilio, "despues": data.valor_domicilio}
        order.valor_domicilio = data.valor_domicilio
    if data.domiciliario_id is not None and data.domiciliario_id != order.domiciliario_id:
        changes["domiciliario_id"] = {"antes": order.domiciliario_id, "despues": data.domiciliario_id}
        order.domiciliario_id = data.domiciliario_id
    if data.mesa_id is not None and data.mesa_id != order.mesa_id:
        changes["mesa_id"] = {"antes": order.mesa_id, "despues": data.mesa_id}
        order.mesa_id = data.mesa_id

    if changes:
        _log(db, current_user, "editar_comanda", order_id, {
            "comanda": order.comanda_numero,
            "cambios": changes,
        })

    db.commit()
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    return _build_order(order, _dom_map(db))


# ── Endpoints de edición de ítems (solo admin) ────────────────────────────────

@router.put("/{order_id}/items/{item_id}")
def edit_order_item(
    order_id: int,
    item_id: int,
    data: EditItemData,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")
    if order.estado == "cancelado":
        raise HTTPException(400, "No se puede editar una comanda cancelada")

    oi = db.query(OrderItem).filter(
        OrderItem.id == item_id, OrderItem.order_id == order_id
    ).first()
    if not oi:
        raise HTTPException(404, "Ítem no encontrado en la comanda")

    changes: dict = {}
    if data.precio_unitario is not None and data.precio_unitario != oi.precio_unitario:
        changes["precio_unitario"] = {"antes": oi.precio_unitario, "despues": data.precio_unitario}
        oi.precio_unitario = data.precio_unitario
    if data.cantidad is not None and data.cantidad != oi.cantidad:
        changes["cantidad"] = {"antes": oi.cantidad, "despues": data.cantidad}
        oi.cantidad = data.cantidad
    if data.nota is not None and data.nota != oi.nota:
        changes["nota"] = {"antes": oi.nota, "despues": data.nota}
        oi.nota = data.nota

    if changes:
        nombre = oi.item.nombre if oi.item else f"Item #{oi.item_id}"
        _log(db, current_user, "editar_item", order_id, {
            "comanda": order.comanda_numero,
            "item": nombre,
            "order_item_id": item_id,
            "cambios": changes,
        })

    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items)
    db.commit()
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    return _build_order(order, _dom_map(db))


@router.post("/{order_id}/items")
def add_item_admin(
    order_id: int,
    data: AddItemData,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")
    if order.estado == "cancelado":
        raise HTTPException(400, "No se puede editar una comanda cancelada")

    menu_item = db.query(MenuItem).filter(MenuItem.id == data.item_id).first()
    if not menu_item:
        raise HTTPException(404, "Ítem del menú no encontrado")

    precio = data.precio_unitario if data.precio_unitario is not None else menu_item.precio
    oi = OrderItem(
        order_id=order.id,
        item_id=menu_item.id,
        cantidad=data.cantidad,
        precio_unitario=precio,
        nota=data.nota,
    )
    db.add(oi)

    _log(db, current_user, "agregar_item", order_id, {
        "comanda": order.comanda_numero,
        "item": menu_item.nombre,
        "cantidad": data.cantidad,
        "precio_unitario": precio,
    })

    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items)
    db.commit()
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    return _build_order(order, _dom_map(db))


@router.delete("/{order_id}/items/{item_id}")
def remove_item_admin(
    order_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")
    if order.estado == "cancelado":
        raise HTTPException(400, "No se puede editar una comanda cancelada")

    oi = db.query(OrderItem).filter(
        OrderItem.id == item_id, OrderItem.order_id == order_id
    ).first()
    if not oi:
        raise HTTPException(404, "Ítem no encontrado en la comanda")

    nombre = oi.item.nombre if oi.item else f"Item #{oi.item_id}"
    _log(db, current_user, "eliminar_item", order_id, {
        "comanda": order.comanda_numero,
        "item": nombre,
        "cantidad": oi.cantidad,
        "precio_unitario": oi.precio_unitario,
    })

    db.delete(oi)
    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items)
    db.commit()
    order = db.query(Order).options(selectinload(Order.items), selectinload(Order.pagos)).filter(Order.id == order_id).first()
    return _build_order(order, _dom_map(db))


# ── Historial de cambios (solo lectura, solo admin) ──────────────────────────

@router.get("/audit-log")
def get_audit_log(
    fecha: Optional[str] = None,
    limit: int = 300,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if fecha:
        # SQLite: func.date() sobre columna datetime devuelve "YYYY-MM-DD"
        q = q.filter(func.date(AuditLog.created_at) == fecha)
    logs = q.limit(limit).all()
    return [
        {
            "id": l.id,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "usuario_nombre": l.usuario_nombre,
            "accion": l.accion,
            "entidad": l.entidad,
            "entidad_id": l.entidad_id,
            "detalle": l.detalle,  # JSON string — el frontend lo parsea
        }
        for l in logs
    ]
