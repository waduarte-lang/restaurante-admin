from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Optional
from decimal import Decimal

from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.alegra_factura import AlegraFactura
from app.models.alegra_pago import AlegraPago
import json

router = APIRouter(prefix="/api/crm/alegra", tags=["crm-alegra"])
_ROLES = ("admin", "gerente", "asesor")


def _mes_range(mes: str) -> tuple[date, date]:
    """Convierte 'YYYY-MM' en (inicio, fin) para filtrar por rango de fechas.

    Se usa en vez de func.strftime() porque strftime es sintaxis SQLite y
    falla contra Postgres (producción); un rango de fechas funciona igual
    en ambos motores y además permite usar índices.
    """
    year, month = (int(p) for p in mes.split("-"))
    inicio = date(year, month, 1)
    fin = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return inicio, fin


def _to_dict(f: AlegraFactura) -> dict:
    hoy = date.today()
    dias_vencido = None
    if f.fecha_vencimiento:
        dias_vencido = (hoy - f.fecha_vencimiento).days
    return {
        "id": f.id,
        "alegra_id": f.alegra_id,
        "num_factura": f.num_factura,
        "fecha_factura": f.fecha_factura.isoformat() if f.fecha_factura else None,
        "fecha_vencimiento": f.fecha_vencimiento.isoformat() if f.fecha_vencimiento else None,
        "status": f.status,
        "termino_pago": f.termino_pago,
        "nit": f.nit,
        "nombre_cliente": f.nombre_cliente,
        "subtotal": float(f.subtotal or 0),
        "iva": float(f.iva or 0),
        "total": float(f.total or 0),
        "total_pagado": float(f.total_pagado or 0),
        "saldo": float(f.saldo or 0),
        "vendedor": f.vendedor,
        "dias_vencido": dias_vencido,
    }


@router.get("/resumen")
def resumen(
    mes: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    q = db.query(AlegraFactura)
    if mes:
        inicio, fin = _mes_range(mes)
        q = q.filter(AlegraFactura.fecha_factura >= inicio, AlegraFactura.fecha_factura < fin)
    facturas = q.all()
    total_facturado = sum(float(f.total or 0) for f in facturas)
    total_pendiente = sum(float(f.saldo or 0) for f in facturas)
    total_cobrado = total_facturado - total_pendiente
    num_clientes = len({f.nit for f in facturas})
    return {
        "num_facturas": len(facturas),
        "num_clientes": num_clientes,
        "total_facturado": total_facturado,
        "total_cobrado": total_cobrado,
        "total_pendiente": total_pendiente,
    }


@router.get("/facturas")
def listar_facturas(
    mes: Optional[str] = None,
    status: Optional[str] = None,
    nit: Optional[str] = None,
    q: Optional[str] = None,
    vendedor: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    query = db.query(AlegraFactura)
    if mes:
        inicio, fin = _mes_range(mes)
        query = query.filter(AlegraFactura.fecha_factura >= inicio, AlegraFactura.fecha_factura < fin)
    if status:
        query = query.filter(AlegraFactura.status == status)
    if nit:
        query = query.filter(AlegraFactura.nit.ilike(f"%{nit}%"))
    if q:
        query = query.filter(
            AlegraFactura.nombre_cliente.ilike(f"%{q}%")
            | AlegraFactura.num_factura.ilike(f"%{q}%")
            | AlegraFactura.nit.ilike(f"%{q}%")
        )
    if vendedor:
        query = query.filter(AlegraFactura.vendedor.ilike(f"%{vendedor}%"))

    query = query.order_by(AlegraFactura.fecha_factura.desc(), AlegraFactura.num_factura.desc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_to_dict(r) for r in rows],
    }


@router.get("/por-cliente/{nit}")
def facturas_cliente(
    nit: str,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    rows = (
        db.query(AlegraFactura)
        .filter(AlegraFactura.nit == nit)
        .order_by(AlegraFactura.fecha_factura.desc())
        .all()
    )
    return [_to_dict(r) for r in rows]


@router.get("/resumen-vendedores")
def resumen_vendedores(
    mes: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    q = db.query(AlegraFactura)
    if mes:
        inicio, fin = _mes_range(mes)
        q = q.filter(AlegraFactura.fecha_factura >= inicio, AlegraFactura.fecha_factura < fin)
    facturas = q.all()
    result: dict = {}
    for f in facturas:
        v = (f.vendedor or "SIN ASESOR").upper().strip()
        if v not in result:
            result[v] = {"vendedor": v, "num_facturas": 0, "total": 0.0, "cobrado": 0.0, "pendiente": 0.0}
        result[v]["num_facturas"] += 1
        result[v]["total"] += float(f.total or 0)
        result[v]["cobrado"] += float(f.total or 0) - float(f.saldo or 0)
        result[v]["pendiente"] += float(f.saldo or 0)
    return sorted(result.values(), key=lambda x: x["total"], reverse=True)


# ─── Cobranzas / Pagos ───────────────────────────────────────────────────────

def _pago_dict(p: AlegraPago) -> dict:
    facturas = []
    try:
        facturas = json.loads(p.facturas_aplicadas or "[]")
    except Exception:
        pass
    return {
        "id": p.id,
        "alegra_id": p.alegra_id,
        "num_recibo": p.num_recibo,
        "fecha_pago": p.fecha_pago.isoformat() if p.fecha_pago else None,
        "metodo_pago": p.metodo_pago,
        "monto": float(p.monto or 0),
        "anotacion": p.anotacion,
        "banco": p.banco,
        "nit": p.nit,
        "nombre_cliente": p.nombre_cliente,
        "facturas_aplicadas": facturas,
        "es_anticipo": p.es_anticipo,
    }


@router.get("/pagos")
def listar_pagos(
    mes: Optional[str] = None,
    nit: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    query = db.query(AlegraPago)
    if mes:
        inicio, fin = _mes_range(mes)
        query = query.filter(AlegraPago.fecha_pago >= inicio, AlegraPago.fecha_pago < fin)
    if nit:
        query = query.filter(AlegraPago.nit.ilike(f"%{nit}%"))
    if q:
        query = query.filter(
            AlegraPago.nombre_cliente.ilike(f"%{q}%")
            | AlegraPago.num_recibo.ilike(f"%{q}%")
            | AlegraPago.nit.ilike(f"%{q}%")
        )
    query = query.order_by(AlegraPago.fecha_pago.desc())
    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    total_monto = db.query(func.sum(AlegraPago.monto)).filter(
        AlegraPago.id.in_([r.id for r in rows])
    ).scalar() or 0
    return {
        "total": total,
        "total_monto": float(total_monto),
        "page": page,
        "per_page": per_page,
        "items": [_pago_dict(r) for r in rows],
    }


@router.get("/pagos/cliente/{nit}")
def pagos_cliente(
    nit: str,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    rows = (
        db.query(AlegraPago)
        .filter(AlegraPago.nit == nit)
        .order_by(AlegraPago.fecha_pago.desc())
        .limit(50)
        .all()
    )
    return [_pago_dict(r) for r in rows]


@router.get("/resumen-cobranzas")
def resumen_cobranzas(
    mes: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    q = db.query(AlegraPago)
    if mes:
        inicio, fin = _mes_range(mes)
        q = q.filter(AlegraPago.fecha_pago >= inicio, AlegraPago.fecha_pago < fin)
    pagos = q.all()
    total_cobrado = sum(float(p.monto or 0) for p in pagos)
    anticipos = sum(float(p.monto or 0) for p in pagos if p.es_anticipo)
    aplicados = total_cobrado - anticipos
    por_metodo: dict = {}
    for p in pagos:
        m = p.metodo_pago or "otro"
        por_metodo[m] = por_metodo.get(m, 0) + float(p.monto or 0)
    return {
        "num_recibos": len(pagos),
        "total_cobrado": total_cobrado,
        "aplicados_facturas": aplicados,
        "anticipos": anticipos,
        "por_metodo": por_metodo,
    }


# ── Sync endpoints ────────────────────────────────────────────────────────────

@router.get("/sync-status")
def sync_status(_=Depends(require_roles("admin", "gerente", "asesor"))):
    """Estado de la última sincronización con Alegra."""
    from app.services.alegra_sync import get_status
    return get_status()


@router.post("/sync-now")
def sync_now(background_tasks: BackgroundTasks, _=Depends(require_roles("admin", "gerente"))):
    """Dispara sync manual contra la API REST de Alegra."""
    from app.services.alegra_sync import run_sync, get_status
    status = get_status()
    if status["running"]:
        return {"ok": False, "msg": "Sync ya en progreso"}
    if not status["credentials_ok"]:
        return {"ok": False, "msg": "Credenciales Alegra no configuradas en el servidor"}
    background_tasks.add_task(run_sync)
    return {"ok": True, "msg": "Sync iniciado — puede tardar 1-2 minutos"}
