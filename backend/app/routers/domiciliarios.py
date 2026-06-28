from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.models.domiciliario import Domiciliario
from app.models.domiciliario_liquidacion import DomiciliarioLiquidacion
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.auth.dependencies import get_current_user, require_roles, admin_only
from app.models.user import User

router = APIRouter(prefix="/api/domiciliarios", tags=["domiciliarios"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DomiciliarioIn(BaseModel):
    nombre:   str
    telefono: Optional[str] = None
    pin:      Optional[str] = None
    activo:   bool = True


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("")
def list_domiciliarios(
    activo: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Domiciliario)
    if activo is not None:
        q = q.filter(Domiciliario.activo == activo)
    return [
        {"id": d.id, "nombre": d.nombre, "telefono": d.telefono, "pin": d.pin, "activo": d.activo}
        for d in q.order_by(Domiciliario.nombre).all()
    ]


@router.post("")
def create_domiciliario(
    data: DomiciliarioIn,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    d = Domiciliario(nombre=data.nombre.strip(), telefono=data.telefono, pin=data.pin, activo=data.activo)
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "nombre": d.nombre, "telefono": d.telefono, "pin": d.pin, "activo": d.activo}


@router.put("/{dom_id}")
def update_domiciliario(
    dom_id: int,
    data: DomiciliarioIn,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")
    d.nombre   = data.nombre.strip()
    d.telefono = data.telefono
    d.pin      = data.pin
    d.activo   = data.activo
    db.commit()
    db.refresh(d)
    return {"id": d.id, "nombre": d.nombre, "telefono": d.telefono, "pin": d.pin, "activo": d.activo}


@router.delete("/{dom_id}")
def delete_domiciliario(
    dom_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")
    # Soft delete si ya tiene pedidos asignados
    tiene_pedidos = db.query(Order).filter(Order.domiciliario_id == dom_id).first()
    if tiene_pedidos:
        d.activo = False
        db.commit()
        return {"detail": "Desactivado (tiene pedidos registrados)"}
    db.delete(d)
    db.commit()
    return {"detail": "Eliminado"}


# ── Reporte diario de domiciliarios ──────────────────────────────────────────

@router.get("/report/daily")
def daily_domiciliario_report(
    fecha: date = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    """
    Cierre diario: ventas en mesa vs domicilio, detalle por domiciliario.
    Muestra para cada repartidor: comandas entregadas, total cobrado.
    """
    if not fecha:
        fecha = date.today()

    start = datetime.combine(fecha, datetime.min.time())
    end   = datetime.combine(fecha, datetime.max.time())

    # Todas las comandas del día (pagadas y abiertas)
    orders = db.query(Order).filter(Order.comanda_fecha == fecha).all()
    pagos  = db.query(Payment).filter(Payment.created_at.between(start, end)).all()

    payment_map: dict = {}
    for p in pagos:
        payment_map.setdefault(p.order_id, []).append(
            {"metodo": p.metodo, "monto": p.monto}
        )

    # ── Separar mesa vs domicilio ─────────────────────────────────────────────
    mesa_orders  = [o for o in orders if o.tipo == "mesa"]
    dom_orders   = [o for o in orders if o.tipo == "domicilio"]

    def order_cobrado(o: Order) -> float:
        return sum(p["monto"] for p in payment_map.get(o.id, []))

    total_mesa_cobrado  = sum(order_cobrado(o) for o in mesa_orders if o.estado == "pagado")
    total_dom_cobrado   = sum(order_cobrado(o) for o in dom_orders  if o.estado == "pagado")

    resumen_mesa = {
        "total_comandas":  len(mesa_orders),
        "comandas_pagadas": sum(1 for o in mesa_orders if o.estado == "pagado"),
        "total_cobrado":   round(total_mesa_cobrado, 2),
    }

    # ── Por domiciliario ──────────────────────────────────────────────────────
    dom_ids = {o.domiciliario_id for o in dom_orders if o.domiciliario_id}
    doms    = {d.id: d for d in db.query(Domiciliario).filter(Domiciliario.id.in_(dom_ids)).all()}

    por_domiciliario = []
    sin_asignar = []

    for o in dom_orders:
        cobrado  = order_cobrado(o)
        pagos_o  = payment_map.get(o.id, [])
        row = {
            "order_id":       o.id,
            "comanda_numero": o.comanda_numero,
            "cliente_nombre": o.cliente_nombre or "—",
            "cliente_direccion": o.cliente_direccion or "—",
            "estado":         o.estado,
            "total":          o.total,
            "cobrado":        round(cobrado, 2),
            "pagos":          pagos_o,
            "hora": o.created_at.strftime("%H:%M") if o.created_at else "—",
        }
        if o.domiciliario_id:
            row["domiciliario_id"] = o.domiciliario_id
            sin_asignar.append(row) if o.domiciliario_id not in doms else None
        else:
            sin_asignar.append(row)

    # Agrupar por domiciliario
    grupos: dict = {}
    for o in dom_orders:
        did = o.domiciliario_id
        if not did:
            continue
        if did not in grupos:
            dom_obj = doms.get(did)
            grupos[did] = {
                "domiciliario_id":     did,
                "domiciliario_nombre": dom_obj.nombre if dom_obj else "—",
                "domiciliario_tel":    dom_obj.telefono if dom_obj else "",
                "total_envios":        0,
                "envios_cobrados":     0,
                "total_cobrado":       0.0,
                "total_valor_domicilio": 0.0,
                "comandas":            [],
            }
        cobrado = order_cobrado(o)
        val_dom = o.valor_domicilio or 0.0
        grupos[did]["total_envios"] += 1
        grupos[did]["total_valor_domicilio"] += val_dom
        if o.estado == "pagado":
            grupos[did]["envios_cobrados"] += 1
            grupos[did]["total_cobrado"]   += cobrado
        grupos[did]["comandas"].append({
            "order_id":          o.id,
            "comanda_numero":    o.comanda_numero,
            "cliente_nombre":    o.cliente_nombre or "—",
            "cliente_direccion": o.cliente_direccion or "",
            "hora":              o.created_at.strftime("%H:%M") if o.created_at else "—",
            "estado":            o.estado,
            "total":             o.total,
            "cobrado":           round(cobrado, 2),
            "valor_domicilio":   val_dom,
            "pagos":             payment_map.get(o.id, []),
        })

    for g in grupos.values():
        g["total_cobrado"] = round(g["total_cobrado"], 2)
        g["total_valor_domicilio"] = round(g["total_valor_domicilio"], 2)
        g["comandas"].sort(key=lambda x: x["comanda_numero"])

    # Domicilios sin domiciliario asignado
    sin_asignar_list = [
        {
            "order_id":          o.id,
            "comanda_numero":    o.comanda_numero,
            "cliente_nombre":    o.cliente_nombre or "—",
            "estado":            o.estado,
            "total":             o.total,
            "cobrado":           round(order_cobrado(o), 2),
            "pagos":             payment_map.get(o.id, []),
            "hora":              o.created_at.strftime("%H:%M") if o.created_at else "—",
        }
        for o in dom_orders if not o.domiciliario_id
    ]

    total_valor_domicilios = sum(o.valor_domicilio or 0.0 for o in dom_orders)

    return {
        "fecha": str(fecha),
        "resumen_mesa": resumen_mesa,
        "resumen_domicilio": {
            "total_comandas":        len(dom_orders),
            "comandas_pagadas":      sum(1 for o in dom_orders if o.estado == "pagado"),
            "total_cobrado":         round(total_dom_cobrado, 2),
            "sin_asignar":           len(sin_asignar_list),
            "total_valor_domicilios": round(total_valor_domicilios, 2),
        },
        "total_dia": {
            "total_comandas":        len(orders),
            "total_cobrado":         round(total_mesa_cobrado + total_dom_cobrado, 2),
            "total_valor_domicilios": round(total_valor_domicilios, 2),
        },
        "por_domiciliario":   sorted(grupos.values(), key=lambda x: x["domiciliario_nombre"]),
        "domicilios_sin_asignar": sin_asignar_list,
    }


# ── Liquidaciones ─────────────────────────────────────────────────────────────

class LiquidarBody(BaseModel):
    fecha: date
    notas: Optional[str] = None


def _fmt_liq(liq: DomiciliarioLiquidacion) -> dict:
    neto = round((liq.total_efectivo or 0) - (liq.total_domicilios or 0), 2)
    return {
        "id":                  liq.id,
        "domiciliario_id":     liq.domiciliario_id,
        "fecha":               str(liq.fecha),
        "total_efectivo":      round(liq.total_efectivo or 0, 2),
        "total_transferencia": round(liq.total_transferencia or 0, 2),
        "total_tarjeta":       round(liq.total_tarjeta or 0, 2),
        "total_domicilios":    round(liq.total_domicilios or 0, 2),
        "neto_a_entregar":     neto,
        "notas":               liq.notas,
        "registrado_por":      liq.registrado_por,
        "created_at":          liq.created_at.isoformat() if liq.created_at else None,
    }


@router.post("/{dom_id}/liquidar")
def liquidar_domiciliario(
    dom_id: int,
    body: LiquidarBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "cajero")),
):
    """Calcula y registra la liquidación diaria de un domiciliario."""
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")

    fecha = body.fecha
    start = datetime.combine(fecha, datetime.min.time())
    end   = datetime.combine(fecha, datetime.max.time())

    # Órdenes pagadas del día de este domiciliario
    orders = db.query(Order).filter(
        Order.domiciliario_id == dom_id,
        Order.tipo == "domicilio",
        Order.estado == "pagado",
        Order.comanda_fecha == fecha,
    ).all()

    order_ids = [o.id for o in orders]

    # Pagos por método (solo platos — valor_domicilio ya está excluido)
    pagos = db.query(Payment).filter(
        Payment.order_id.in_(order_ids),
        Payment.created_at.between(start, end),
    ).all() if order_ids else []

    total_efectivo      = sum(p.monto for p in pagos if p.metodo == "efectivo")
    total_transferencia = sum(p.monto for p in pagos if p.metodo == "transferencia")
    total_tarjeta       = sum(p.monto for p in pagos if p.metodo == "tarjeta")
    total_domicilios    = sum(float(o.valor_domicilio or 0) for o in orders)

    # Upsert: si ya existe para ese día, actualiza
    liq = db.query(DomiciliarioLiquidacion).filter(
        DomiciliarioLiquidacion.domiciliario_id == dom_id,
        DomiciliarioLiquidacion.fecha == fecha,
    ).first()

    if liq:
        liq.total_efectivo      = total_efectivo
        liq.total_transferencia = total_transferencia
        liq.total_tarjeta       = total_tarjeta
        liq.total_domicilios    = total_domicilios
        liq.notas               = body.notas
        liq.registrado_por      = current_user.id
    else:
        liq = DomiciliarioLiquidacion(
            domiciliario_id     = dom_id,
            fecha               = fecha,
            total_efectivo      = total_efectivo,
            total_transferencia = total_transferencia,
            total_tarjeta       = total_tarjeta,
            total_domicilios    = total_domicilios,
            notas               = body.notas,
            registrado_por      = current_user.id,
        )
        db.add(liq)

    db.commit()
    db.refresh(liq)
    return _fmt_liq(liq)


@router.get("/{dom_id}/liquidaciones")
def get_liquidaciones_domiciliario(
    dom_id: int,
    limit: int = Query(default=30),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    """Historial de liquidaciones de un domiciliario."""
    liqs = (
        db.query(DomiciliarioLiquidacion)
        .filter(DomiciliarioLiquidacion.domiciliario_id == dom_id)
        .order_by(DomiciliarioLiquidacion.fecha.desc())
        .limit(limit)
        .all()
    )
    return [_fmt_liq(l) for l in liqs]


@router.get("/liquidaciones")
def get_todas_liquidaciones(
    fecha: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    """Todas las liquidaciones, opcionalmente filtradas por fecha."""
    q = db.query(DomiciliarioLiquidacion)
    if fecha:
        q = q.filter(DomiciliarioLiquidacion.fecha == fecha)
    liqs = q.order_by(DomiciliarioLiquidacion.fecha.desc()).all()
    return [_fmt_liq(l) for l in liqs]
