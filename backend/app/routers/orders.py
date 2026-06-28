"""
Router unificado de comandas.

Exporta tres routers que se registran en main.py:
  router        → /api/orders          (operaciones estándar, todos los roles)
  admin_router  → /api/admin/orders    (edición admin, solo admin)
  import_router → /api/admin/import    (carga histórica, solo admin)

Un único _next_comanda() garantiza numeración consecutiva global
para comandas creadas desde el POS o cargadas manualmente.
"""
import re
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func, text
from typing import List, Optional
from datetime import date, datetime, time as time_type
from pydantic import BaseModel
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.menu import MenuItem
from app.models.table import Table
from app.models.payment import Payment
from app.models.audit_log import AuditLog
from app.models.domiciliario import Domiciliario
from app.models.order_estado_log import OrderEstadoLog
from app.services.inventory_service import descontar_inventario
from app.auth.dependencies import get_current_user, admin_only
from app.models.user import User
from app.models.cash_register import CashRegister
from app.schemas.order import OrderCreate, OrderUpdate, OrderOut

# ── Routers ───────────────────────────────────────────────────────────────────

router        = APIRouter(prefix="/api/orders",        tags=["orders"])
admin_router  = APIRouter(prefix="/api/admin/orders",  tags=["admin-orders"])
import_router = APIRouter(prefix="/api/admin/import",  tags=["import"])


# ── Helpers compartidos ───────────────────────────────────────────────────────

def _calc_total(items, valor_domicilio=0.0):
    return sum(i.precio_unitario * i.cantidad for i in items) + (valor_domicilio or 0.0)


def _next_comanda(db: Session) -> int:
    """Número consecutivo único global para toda la tabla orders."""
    last = db.query(func.max(Order.comanda_numero)).scalar()
    return (last or 0) + 1


def _build_order(o: Order) -> dict:
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    d["items"] = [
        {**{c.name: getattr(i, c.name) for c in i.__table__.columns},
         "item_nombre": i.item.nombre if i.item else None}
        for i in o.items
    ]
    return d


def _dom_map(db: Session) -> dict:
    rows = db.query(Domiciliario.id, Domiciliario.nombre).all()
    return {r.id: r.nombre for r in rows}


def _build_order_admin(o: Order, dom: dict = None) -> dict:
    """Versión extendida para admin: incluye domiciliario_nombre y metodo_pago."""
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    if dom is not None:
        d["domiciliario_nombre"] = dom.get(o.domiciliario_id) if o.domiciliario_id else None
    else:
        d["domiciliario_nombre"] = o.domiciliario.nombre if o.domiciliario else None
    # Usar metodo_pago de la orden (incluye 'mixto'); fallback al primer pago
    d["metodo_pago"] = o.metodo_pago or (o.pagos[0].metodo if o.pagos else None)
    # Detalle de pagos (útil para mixto)
    d["pagos"] = [{"metodo": p.metodo, "monto": float(p.monto)} for p in o.pagos]
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


def _log_estado(db: Session, order: Order, estado_de: Optional[str], estado_a: str,
                usuario_id: Optional[int] = None, usuario_nombre: Optional[str] = None):
    """Registra una transición de estado en order_estado_logs para análisis de tiempos."""
    entry = OrderEstadoLog(
        order_id=order.id,
        tipo_orden=order.tipo,
        estado_de=estado_de,
        estado_a=estado_a,
        usuario_id=usuario_id,
        usuario_nombre=usuario_nombre,
    )
    db.add(entry)


# ─────────────────────────────────────────────────────────────────────────────
#  /api/orders  — operaciones estándar (POS)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[OrderOut])
def list_orders(estado: Optional[str] = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Order).options(joinedload(Order.items))
    if estado:
        q = q.filter(Order.estado == estado)
    return [_build_order(o) for o in q.order_by(Order.created_at.desc()).all()]


@router.get("/domicilio-pendientes")
def count_domicilio_pendientes(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Cuenta pedidos de domicilio en estado 'abierto' (por aprobar)."""
    count = db.query(func.count(Order.id)).filter(
        Order.tipo == "domicilio",
        Order.estado == "abierto"
    ).scalar()
    return {"count": int(count or 0)}


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return _build_order(order)


@router.post("", response_model=OrderOut)
def create_order(data: OrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if data.tipo == "mesa":
        if data.mesa_id:
            table = db.query(Table).filter(Table.id == data.mesa_id).first()
            if not table:
                raise HTTPException(status_code=404, detail="Mesa no encontrada")
    elif data.tipo == "domicilio":
        if not data.cliente_nombre:
            raise HTTPException(status_code=400, detail="Nombre del cliente requerido para domicilio")

    caja_activa = db.query(CashRegister).filter(CashRegister.estado == "abierta").first()

    estado_inicial = data.estado if data.estado in ("abierto", "en_cocina", "listo", "pagado", "cancelado") else "pagado"

    order = Order(
        comanda_numero=_next_comanda(db),
        comanda_fecha=date.today(),
        tipo=data.tipo,
        mesa_id=data.mesa_id,
        mesero_id=current_user.id,
        estado=estado_inicial,
        observaciones=data.observaciones,
        cliente_nombre=data.cliente_nombre,
        cliente_telefono=data.cliente_telefono,
        cliente_direccion=data.cliente_direccion,
        domiciliario_id=data.domiciliario_id if data.tipo == "domicilio" else None,
        valor_domicilio=data.valor_domicilio if data.tipo == "domicilio" else 0.0,
        metodo_pago=data.metodo_pago,
        caja_id=caja_activa.id if caja_activa else None,
        fuente="pos",
    )
    db.add(order)
    db.flush()

    for item_data in data.items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item_data.item_id, MenuItem.activo == True).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Item {item_data.item_id} no encontrado")
        precio = item_data.precio_unitario if item_data.precio_unitario is not None else menu_item.precio
        oi = OrderItem(order_id=order.id, item_id=menu_item.id, cantidad=item_data.cantidad,
                       precio_unitario=precio, nota=item_data.nota)
        db.add(oi)

    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items, order.valor_domicilio)

    # Si nace pagada → crear registro(s) de pago automáticamente
    if estado_inicial == "pagado" and order.total > 0:
        if data.metodo_pago == "mixto" and data.monto_efectivo is not None:
            met1 = data.mixto_metodo1 or "efectivo"
            met2 = data.mixto_metodo2 or "transferencia"
            monto1 = max(0.0, min(float(data.monto_efectivo), order.total))
            monto2 = round(order.total - monto1, 2)
            caja_id = caja_activa.id if caja_activa else None
            if monto1 > 0:
                db.add(Payment(order_id=order.id, monto=monto1, metodo=met1,
                               cajero_id=current_user.id, caja_id=caja_id))
            if monto2 > 0:
                db.add(Payment(order_id=order.id, monto=monto2, metodo=met2,
                               cajero_id=current_user.id, caja_id=caja_id))
        else:
            db.add(Payment(order_id=order.id, monto=order.total,
                           metodo=data.metodo_pago or "efectivo",
                           cajero_id=current_user.id, caja_id=caja_activa.id if caja_activa else None))

    # Estado de la mesa según el estado final de la comanda
    if data.tipo == "mesa" and data.mesa_id:
        table = db.query(Table).filter(Table.id == data.mesa_id).first()
        if table:
            table.estado = "libre" if estado_inicial == "pagado" else "ocupada"

    # Registrar estado inicial en log de trazabilidad
    _log_estado(db, order, estado_de=None, estado_a=estado_inicial,
                usuario_id=current_user.id, usuario_nombre=current_user.nombre)

    # Descontar inventario si nace como pagado (carga manual / importación)
    if estado_inicial == "pagado":
        descontar_inventario(db, order)

    db.commit()
    db.refresh(order)
    return _build_order(order)


@router.put("/{order_id}", response_model=OrderOut)
def update_order(order_id: int, data: OrderUpdate, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    # Capturar estado anterior antes de actualizar
    estado_anterior = order.estado
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(order, field, value)
    if data.estado == "pagado" and order.mesa_id:
        table = db.query(Table).filter(Table.id == order.mesa_id).first()
        if table:
            table.estado = "libre"
    # Registrar cambio de estado en log de trazabilidad
    if data.estado is not None and data.estado != estado_anterior:
        _log_estado(db, order, estado_de=estado_anterior, estado_a=data.estado,
                    usuario_id=current_user.id, usuario_nombre=current_user.nombre)
    # Descontar inventario al pagar
    if data.estado == "pagado" and estado_anterior != "pagado":
        descontar_inventario(db, order)
    db.commit()
    db.refresh(order)
    return _build_order(order)


@router.post("/{order_id}/items")
def add_item_to_order(order_id: int, item_id: int, cantidad: int = 1, nota: str = None,
                      db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.estado in ("pagado", "cancelado"):
        raise HTTPException(status_code=400, detail="Pedido no disponible para modificar")
    menu_item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.activo == True).first()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    oi = OrderItem(order_id=order.id, item_id=menu_item.id, cantidad=cantidad,
                   precio_unitario=menu_item.precio, nota=nota)
    db.add(oi)
    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items, order.valor_domicilio)
    db.commit()
    return {"ok": True, "total": order.total}


@router.put("/{order_id}/items/bulk", response_model=OrderOut)
def replace_order_items(order_id: int, data: OrderCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Reemplaza todos los ítems de un pedido existente (usado al editar desde el POS)."""
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if order.estado in ("pagado", "cancelado"):
        raise HTTPException(status_code=400, detail="No se puede editar un pedido pagado o cancelado")

    for item in list(order.items):
        db.delete(item)
    db.flush()

    for item_data in data.items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item_data.item_id).first()
        if not menu_item:
            continue
        precio = item_data.precio_unitario if item_data.precio_unitario is not None else menu_item.precio
        oi = OrderItem(order_id=order.id, item_id=menu_item.id, cantidad=item_data.cantidad,
                       precio_unitario=precio, nota=item_data.nota)
        db.add(oi)

    if data.observaciones is not None:
        order.observaciones = data.observaciones

    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items, order.valor_domicilio)
    db.commit()
    db.refresh(order)
    return _build_order(order)


@router.get("/{order_id}/comanda", response_class=HTMLResponse)
def print_comanda(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if order.mesa:
        mesa_info = f"Mesa {order.mesa.numero}"
    elif order.tipo == "domicilio":
        mesa_info = order.cliente_nombre or "DOMICILIO"
    else:
        mesa_info = "Sin mesa"
    fecha_str = order.created_at.strftime("%d/%m/%Y %H:%M") if order.created_at else ""
    mesero_nombre = order.mesero.nombre if order.mesero else ""

    # ── Construir lista numerada de platos ──────────────────────────────────
    # Regla: sopa (precio > 0) + proteína compañera (precio = 0) → una línea "SOPA - PROTEÍNA"
    # Ítems regulares (bowls, platos completos, etc.) → línea individual por unidad
    numbered_lines = []  # lista de strings a mostrar numerados
    processed = set()

    # Primero agrupar sopas con su proteína compañera
    for item in order.items:
        if item.id in processed:
            continue
        tipo = item.item.tipo_plato if item.item else None
        price = float(item.precio_unitario or 0)
        nombre = item.item.nombre.upper() if item.item else f"ITEM #{item.item_id}"

        if tipo == 'sopa' and price > 0:
            # Buscar proteína compañera ($0) aún no procesada
            companion = next(
                (it for it in order.items
                 if it.id not in processed
                 and float(it.precio_unitario or 0) == 0
                 and it.item and it.item.tipo_plato == 'proteina'),
                None
            )
            if companion:
                prot_nombre = companion.item.nombre.upper() if companion.item else ""
                display = f"{nombre} - {prot_nombre}"
                processed.add(companion.id)
            else:
                display = nombre
            for _ in range(item.cantidad or 1):
                numbered_lines.append(display)
            processed.add(item.id)

        elif tipo == 'proteina' and price == 0:
            # Proteína compañera: ya procesada o se procesará con la sopa
            processed.add(item.id)

        else:
            # Ítem regular: una línea por unidad
            for _ in range(item.cantidad or 1):
                numbered_lines.append(nombre)
            processed.add(item.id)

    # Generar HTML numerado
    items_html = ""
    for idx, linea in enumerate(numbered_lines, 1):
        items_html += f"""
        <div class="item">
          <span class="num">{idx}.-</span>
          <span class="nombre">{linea}</span>
        </div>"""

    domicilio_html = ""
    if order.tipo == "domicilio":
        domicilio_html = f"""
        <div class="domicilio">
          <div><b>Cliente:</b> {order.cliente_nombre or ''}</div>
          {'<div><b>Tel:</b> ' + order.cliente_telefono + '</div>' if order.cliente_telefono else ''}
          {'<div><b>Dir:</b> ' + order.cliente_direccion + '</div>' if order.cliente_direccion else ''}
        </div>"""

    # Observaciones: mostrar solo partes con ":" (Acompañante, Bebida, notas libres)
    # Las descripciones de platos sin ":" ya están en los ítems numerados
    if order.observaciones:
        obs_parts = [p.strip() for p in order.observaciones.split('|') if p.strip()]
        real_obs = [p for p in obs_parts if ':' in p]
        if real_obs:
            obs_content = '<br>'.join(real_obs)
            observaciones_html = f'<div class="obs">Obs: {obs_content}</div>'
        else:
            observaciones_html = ""
    else:
        observaciones_html = ""

    metodo_labels = {'efectivo': '💵 Efectivo', 'transferencia': '📲 Transferencia',
                     'tarjeta': '💳 Tarjeta', 'credito': '📋 Crédito', 'mixto': '💵📲 Mixto'}
    pago_html = ""
    if order.metodo_pago == 'mixto' and order.pagos:
        partes = ' + '.join(
            f"{metodo_labels.get(p.metodo, p.metodo)} ${p.monto:,.0f}".replace(",", ".")
            for p in order.pagos
        )
        pago_html = f'<div class="pago">{partes}</div>'
    elif order.metodo_pago:
        pago_html = f'<div class="pago">{metodo_labels.get(order.metodo_pago, order.metodo_pago.capitalize())}</div>'

    # ── Total a cobrar (siempre visible, destacado en domicilio) ──
    def fmt_cop(v):
        return f"${v:,.0f}".replace(",", ".")

    subtotal_items = sum(i.precio_unitario * i.cantidad for i in order.items)
    valor_dom = order.valor_domicilio or 0.0
    total = order.total or (subtotal_items + valor_dom)

    total_html = f"""
        <div class="total-box">
          <div class="total-row-main"><span>TOTAL</span><span>{fmt_cop(total)}</span></div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Comanda #{order.comanda_numero:03d}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Courier New', monospace; font-size: 10px; width: 80mm; }}

  /* ── Cabecera fija ── */
  .header {{
    position: fixed;
    top: 0; left: 0; right: 0;
    padding: 3px 5px 3px;
    text-align: center;
    border-bottom: 2px dashed #000;
    background: white;
  }}
  .comanda-num {{ font-size: 22px; font-weight: bold; line-height: 1.1; }}
  .tipo {{ font-size: 11px; font-weight: bold; letter-spacing: 1px; margin: 1px 0; }}
  .mesa {{ font-size: 13px; font-weight: bold; }}

  /* ── Contenido ── */
  #content {{ padding: 0 5px 4px; }}

  .items {{ margin: 3px 0; border-bottom: 1px dashed #000; padding-bottom: 3px; }}
  .item {{ margin: 3px 0; display: flex; gap: 4px; align-items: baseline; }}
  .num {{ font-weight: bold; font-size: 11px; min-width: 22px; flex-shrink: 0; }}
  .nombre {{ font-size: 10px; font-weight: bold; line-height: 1.3; }}
  .nota {{ font-size: 9px; color: #444; padding-left: 26px; font-style: italic; }}
  .domicilio {{ background: #f0f0f0; padding: 3px 4px; margin: 3px 0; border: 1px solid #bbb; font-size: 9px; line-height: 1.4; }}
  .obs {{ font-size: 9px; font-style: italic; margin: 3px 0; border-top: 1px dashed #000; padding-top: 3px; line-height: 1.6; }}
  .pago {{ font-size: 10px; font-weight: bold; text-align: center; margin: 3px 0; border-top: 1px dashed #000; padding-top: 3px; border-bottom: 1px dashed #000; padding-bottom: 3px; }}
  .total-box {{ border-top: 2px solid #000; margin: 4px 0 3px; padding-top: 3px; }}
  .total-row-sm {{ display: flex; justify-content: space-between; font-size: 9px; color: #444; margin-bottom: 1px; }}
  .total-row-main {{ display: flex; justify-content: space-between; font-size: 14px; font-weight: bold; margin-top: 2px; }}
  .footer {{ text-align: center; font-size: 9px; margin-top: 3px; line-height: 1.4; border-top: 1px dashed #000; padding-top: 3px; }}

  @page {{
    size: 80mm 100mm;
    margin: 0 0 5mm 0;
    @bottom-right {{
      content: counter(page) " / " counter(pages);
      font-family: 'Courier New', monospace;
      font-size: 8px;
      padding: 0 3px 1px 0;
    }}
  }}
  @media print {{
    body {{ width: 80mm; }}
  }}
</style>
</head>
<body>

<div class="header" id="hdr">
  <div class="comanda-num">#{order.comanda_numero:03d}</div>
  <div class="tipo">{'🛵 DOMICILIO' if order.tipo == 'domicilio' else '🍽 MESA'}</div>
  <div class="mesa">{mesa_info}</div>
</div>

<div id="content">
  {domicilio_html}
  <div class="items">{items_html}</div>
  {observaciones_html}
  {pago_html}
  {total_html}
  <div class="footer">
    <div>{fecha_str}</div>
    <div>— Gracias —</div>
  </div>
</div>

<script>
window.onload = function() {{
  var hdr = document.getElementById('hdr');
  document.getElementById('content').style.paddingTop = (hdr.offsetHeight + 4) + 'px';
  window.print();
}};
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ─────────────────────────────────────────────────────────────────────────────
#  /api/admin/orders  — edición administrativa (solo admin)
# ─────────────────────────────────────────────────────────────────────────────

class EditItemData(BaseModel):
    precio_unitario: Optional[float] = None
    cantidad: Optional[int] = None
    nota: Optional[str] = None


class AddItemData(BaseModel):
    item_id: int
    cantidad: int = 1
    precio_unitario: Optional[float] = None
    nota: Optional[str] = None


class EditOrderData(BaseModel):
    comanda_fecha: Optional[str] = None   # "YYYY-MM-DD"
    comanda_numero: Optional[int] = None
    estado: Optional[str] = None
    total: Optional[float] = None
    observaciones: Optional[str] = None
    domiciliario_id: Optional[int] = None
    valor_domicilio: Optional[float] = None


@admin_router.get("/list")
def list_orders_admin(
    fecha_inicio: Optional[date] = Query(default=None),
    fecha_fin:    Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    """Lista todas las comandas con filtro de rango de fechas."""
    try:
        q = db.query(Order).options(
            selectinload(Order.items).selectinload(OrderItem.item),
            selectinload(Order.pagos),
        )
        if fecha_inicio:
            q = q.filter(Order.comanda_fecha >= fecha_inicio.isoformat())
        if fecha_fin:
            q = q.filter(Order.comanda_fecha <= fecha_fin.isoformat())
        orders = q.order_by(Order.comanda_fecha.desc(), Order.comanda_numero.desc()).all()
        dom = _dom_map(db)
        return [_build_order_admin(o, dom) for o in orders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.delete("/{order_id}")
def delete_order_admin(
    order_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    """Elimina permanentemente una comanda y sus pagos."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")
    db.query(Payment).filter(Payment.order_id == order_id).delete()
    db.query(OrderItem).filter(OrderItem.order_id == order_id).delete()
    db.delete(order)
    db.commit()
    return {"ok": True}


@admin_router.put("/{order_id}")
def edit_order_admin(
    order_id: int,
    data: EditOrderData,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
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
    if data.observaciones is not None and data.observaciones != (order.observaciones or ''):
        changes["observaciones"] = {"antes": order.observaciones, "despues": data.observaciones}
        order.observaciones = data.observaciones or None

    if changes:
        _log(db, current_user, "editar_comanda", order_id, {
            "comanda": order.comanda_numero,
            "cambios": changes,
        })
        # Registrar cambio de estado en log de trazabilidad
        if "estado" in changes:
            _log_estado(db, order,
                        estado_de=changes["estado"]["antes"],
                        estado_a=changes["estado"]["despues"],
                        usuario_id=current_user.id,
                        usuario_nombre=current_user.nombre)
        # Descontar inventario si el admin marca como pagado
        if "estado" in changes and changes["estado"]["despues"] == "pagado":
            descontar_inventario(db, order)

    db.commit()
    order = db.query(Order).options(
        selectinload(Order.items).selectinload(OrderItem.item),
        selectinload(Order.pagos),
    ).filter(Order.id == order_id).first()
    return _build_order_admin(order, _dom_map(db))


@admin_router.put("/{order_id}/items/{item_id}")
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
    order.total = _calc_total(order.items, order.valor_domicilio)
    db.commit()
    order = db.query(Order).options(
        selectinload(Order.items).selectinload(OrderItem.item),
        selectinload(Order.pagos),
    ).filter(Order.id == order_id).first()
    return _build_order_admin(order, _dom_map(db))


@admin_router.post("/{order_id}/items")
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
    order.total = _calc_total(order.items, order.valor_domicilio)
    db.commit()
    order = db.query(Order).options(
        selectinload(Order.items).selectinload(OrderItem.item),
        selectinload(Order.pagos),
    ).filter(Order.id == order_id).first()
    return _build_order_admin(order, _dom_map(db))


@admin_router.delete("/{order_id}/items/{item_id}")
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
    order.total = _calc_total(order.items, order.valor_domicilio)
    db.commit()
    order = db.query(Order).options(
        selectinload(Order.items).selectinload(OrderItem.item),
        selectinload(Order.pagos),
    ).filter(Order.id == order_id).first()
    return _build_order_admin(order, _dom_map(db))


@admin_router.get("/audit-log")
def get_audit_log(
    fecha: Optional[str] = None,
    limit: int = 300,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if fecha:
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
            "detalle": l.detalle,
        }
        for l in logs
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  /api/admin/import  — carga histórica de comandas (solo admin)
# ─────────────────────────────────────────────────────────────────────────────

class ImportItemIn(BaseModel):
    item_id: int
    cantidad: int = 1
    precio_unitario: float
    nota: Optional[str] = None


class ImportComandaIn(BaseModel):
    fecha: date
    hora: str = "12:00"
    tipo: str = "mesa"                    # "mesa" | "domicilio"
    mesa_numero: Optional[int] = None
    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_direccion: Optional[str] = None
    domiciliario_id: Optional[int] = None
    observaciones: Optional[str] = None
    items: List[ImportItemIn]
    metodo_pago: str = "efectivo"
    monto_efectivo: Optional[float] = None  # monto del primer método en pago mixto
    mixto_metodo1: Optional[str] = None
    mixto_metodo2: Optional[str] = None
    valor_domicilio: float = 0.0
    total_override: Optional[float] = None


class ImportComandaOut(BaseModel):
    ok: bool
    order_id: int
    comanda_numero: int
    total: float
    aviso: Optional[str] = None


@import_router.post("/comanda", response_model=ImportComandaOut)
def import_comanda(
    data: ImportComandaIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="La comanda debe tener al menos un ítem")

    for it in data.items:
        if not db.query(MenuItem).filter(MenuItem.id == it.item_id).first():
            raise HTTPException(status_code=404, detail=f"Plato con id {it.item_id} no encontrado en el menú")

    aviso: Optional[str] = None
    mesa_id = None
    obs_extra = ""

    if data.tipo == "mesa":
        if not data.mesa_numero:
            raise HTTPException(status_code=400, detail="Indica el número de mesa")
        table = db.query(Table).filter(Table.numero == data.mesa_numero).first()
        if table:
            mesa_id = table.id
        else:
            aviso = f"Mesa {data.mesa_numero} no está registrada en el sistema; la comanda se guardó sin asignación de mesa."
            obs_extra = f"[Mesa {data.mesa_numero}] "
    elif data.tipo == "domicilio":
        if not data.cliente_nombre:
            raise HTTPException(status_code=400, detail="Nombre del cliente requerido para domicilio")

    obs_final = (obs_extra + (data.observaciones or "")).strip() or None
    comanda_num = _next_comanda(db)

    order = Order(
        comanda_numero=comanda_num,
        comanda_fecha=data.fecha,
        tipo=data.tipo,
        mesa_id=mesa_id,
        mesero_id=current_user.id,
        estado="pagado",
        observaciones=obs_final,
        cliente_nombre=data.cliente_nombre,
        cliente_telefono=data.cliente_telefono,
        cliente_direccion=data.cliente_direccion,
        domiciliario_id=data.domiciliario_id if data.tipo == "domicilio" else None,
        valor_domicilio=data.valor_domicilio if data.tipo == "domicilio" else 0.0,
        metodo_pago=data.metodo_pago,
        total=0.0,
        fuente="manual",
    )
    db.add(order)
    db.flush()

    subtotal = 0.0
    for it in data.items:
        oi = OrderItem(
            order_id=order.id,
            item_id=it.item_id,
            cantidad=it.cantidad,
            precio_unitario=it.precio_unitario,
            nota=it.nota,
            estado="listo",
        )
        db.add(oi)
        subtotal += it.cantidad * it.precio_unitario

    total_calculado = subtotal + (data.valor_domicilio if data.tipo == "domicilio" else 0.0)
    order.total = data.total_override if data.total_override is not None else total_calculado
    db.flush()

    if data.metodo_pago == "mixto" and data.monto_efectivo is not None:
        met1 = data.mixto_metodo1 or "efectivo"
        met2 = data.mixto_metodo2 or "transferencia"
        monto1 = max(0.0, min(float(data.monto_efectivo), order.total))
        monto2 = round(order.total - monto1, 2)
        if monto1 > 0:
            db.add(Payment(order_id=order.id, monto=monto1, metodo=met1, cajero_id=current_user.id))
        if monto2 > 0:
            db.add(Payment(order_id=order.id, monto=monto2, metodo=met2, cajero_id=current_user.id))
    else:
        db.add(Payment(order_id=order.id, monto=order.total, metodo=data.metodo_pago, cajero_id=current_user.id))
    db.flush()

    # Retrofechar timestamps
    try:
        h, m = data.hora.split(":")
        dt = datetime.combine(data.fecha, time_type(int(h), int(m)))
    except Exception:
        dt = datetime.combine(data.fecha, time_type(12, 0))

    dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    db.execute(text(f"UPDATE orders   SET created_at = '{dt_str}' WHERE id = {order.id}"))
    db.execute(text(f"UPDATE payments SET created_at = '{dt_str}' WHERE id = {payment.id}"))

    db.commit()

    return ImportComandaOut(
        ok=True,
        order_id=order.id,
        comanda_numero=comanda_num,
        total=order.total,
        aviso=aviso,
    )
