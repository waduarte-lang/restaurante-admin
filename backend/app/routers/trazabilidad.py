"""
Módulo de trazabilidad — análisis de tiempos por etapa para domicilios.

Fuentes de datos:
  - order_estado_logs : transiciones precisas (a partir de la activación del módulo)
  - audit_logs        : transiciones históricas parciales (abierto→en_cocina)
  - orders.created_at / updated_at : fallback para estimar tiempos

Etapas medidas:
  t_aprobacion : created_at  → en_cocina  (caja aprueba + fija valor domicilio)
  t_cocina     : en_cocina   → listo      (cocina prepara — opcional, no siempre existe)
  t_entrega    : en_cocina/listo → pagado (domiciliario entrega)
  t_total      : created_at  → pagado
"""
import json
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.database import get_db
from app.auth.dependencies import get_current_user, admin_only
from app.models.order import Order
from app.models.order_estado_log import OrderEstadoLog
from app.models.audit_log import AuditLog
from app.models.domiciliario import Domiciliario

router = APIRouter(prefix="/api/trazabilidad", tags=["trazabilidad"])


# ─── helpers ─────────────────────────────────────────────────────────────────

def _mins(a, b) -> Optional[float]:
    """Diferencia en minutos entre dos datetimes. Retorna None si alguno es None o el resultado es negativo."""
    if not a or not b:
        return None
    diff = (b - a).total_seconds() / 60
    return round(diff, 1) if diff >= 0 else None


def _parse_dt(val) -> Optional[datetime]:
    """Convierte string ISO o datetime a datetime (timezone-naive para comparar)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                pass
    return None


def _tiempos_orden(order: Order, logs: list, audit_logs: list) -> dict:
    """
    Calcula los tiempos de cada etapa para una orden.
    Retorna un dict con t_aprobacion, t_cocina, t_entrega, t_total (en minutos) y fuente.
    """
    t_recepcion = _parse_dt(order.created_at)
    t_cocina_dt = None
    t_listo_dt  = None
    t_pagado_dt = None
    fuente      = "estimado"

    # Prioridad 1: order_estado_logs (precisos)
    for log in sorted(logs, key=lambda l: l.created_at):
        ts = _parse_dt(log.created_at)
        if log.estado_a == "en_cocina" and not t_cocina_dt:
            t_cocina_dt = ts
            fuente = "log"
        elif log.estado_a == "listo" and not t_listo_dt:
            t_listo_dt = ts
        elif log.estado_a == "pagado" and not t_pagado_dt:
            t_pagado_dt = ts

    # Prioridad 2: audit_logs históricos (solo tienen abierto→en_cocina)
    if not t_cocina_dt:
        for al in sorted(audit_logs, key=lambda a: a.created_at):
            try:
                d = json.loads(al.detalle or "{}")
                cambios = d.get("cambios", {})
                if "estado" in cambios and cambios["estado"].get("despues") == "en_cocina":
                    t_cocina_dt = _parse_dt(al.created_at)
                    if fuente == "estimado":
                        fuente = "audit"
            except Exception:
                pass

    # Fallback: updated_at como aproximación de t_pagado
    if not t_pagado_dt and order.estado == "pagado":
        t_pagado_dt = _parse_dt(order.updated_at)

    return {
        "t_aprobacion": _mins(t_recepcion, t_cocina_dt),
        "t_cocina":     _mins(t_cocina_dt, t_listo_dt),
        "t_entrega":    _mins(t_listo_dt or t_cocina_dt, t_pagado_dt),
        "t_total":      _mins(t_recepcion, t_pagado_dt),
        "fuente":       fuente,
    }


def _avg(values: list) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


# ─── endpoint: resumen agregado del período ──────────────────────────────────

@router.get("/domicilios/resumen")
def get_resumen(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Resumen de tiempos promedio por etapa para domicilios completados en el período.
    """
    hoy = date.today()
    d_desde = date.fromisoformat(desde) if desde else (hoy - timedelta(days=29))
    d_hasta = date.fromisoformat(hasta) if hasta else hoy

    orders = (
        db.query(Order)
        .filter(
            Order.tipo == "domicilio",
            Order.estado == "pagado",
            func.date(Order.created_at) >= d_desde,
            func.date(Order.created_at) <= d_hasta,
        )
        .all()
    )

    if not orders:
        return {
            "count": 0,
            "desde": str(d_desde),
            "hasta": str(d_hasta),
            "avg_t_aprobacion": None,
            "avg_t_cocina": None,
            "avg_t_entrega": None,
            "avg_t_total": None,
        }

    order_ids = [o.id for o in orders]
    logs_by_order: dict = {}
    for log in db.query(OrderEstadoLog).filter(OrderEstadoLog.order_id.in_(order_ids)).all():
        logs_by_order.setdefault(log.order_id, []).append(log)

    audits_by_order: dict = {}
    for al in db.query(AuditLog).filter(
        AuditLog.entidad_id.in_(order_ids),
        AuditLog.accion == "editar_comanda",
    ).all():
        audits_by_order.setdefault(al.entidad_id, []).append(al)

    resultados = [
        _tiempos_orden(o, logs_by_order.get(o.id, []), audits_by_order.get(o.id, []))
        for o in orders
    ]

    return {
        "count":             len(orders),
        "desde":             str(d_desde),
        "hasta":             str(d_hasta),
        "avg_t_aprobacion":  _avg([r["t_aprobacion"] for r in resultados]),
        "avg_t_cocina":      _avg([r["t_cocina"]     for r in resultados]),
        "avg_t_entrega":     _avg([r["t_entrega"]    for r in resultados]),
        "avg_t_total":       _avg([r["t_total"]      for r in resultados]),
        "con_log_preciso":   sum(1 for r in resultados if r["fuente"] == "log"),
    }


# ─── endpoint: serie histórica para gráficas ─────────────────────────────────

@router.get("/domicilios/historico")
def get_historico(
    desde:      Optional[str] = Query(None),
    hasta:      Optional[str] = Query(None),
    agrupacion: str           = Query("dia"),   # dia | semana | mes
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Serie temporal de tiempos promedio agrupados por día/semana/mes.
    Retorna lista de {fecha, avg_t_aprobacion, avg_t_entrega, avg_t_total, count}.
    """
    hoy = date.today()

    if agrupacion == "mes":
        d_desde = date.fromisoformat(desde) if desde else date(hoy.year - 1, hoy.month, 1)
    elif agrupacion == "semana":
        d_desde = date.fromisoformat(desde) if desde else (hoy - timedelta(weeks=11))
    else:  # dia
        d_desde = date.fromisoformat(desde) if desde else (hoy - timedelta(days=29))

    d_hasta = date.fromisoformat(hasta) if hasta else hoy

    orders = (
        db.query(Order)
        .filter(
            Order.tipo == "domicilio",
            Order.estado == "pagado",
            func.date(Order.created_at) >= d_desde,
            func.date(Order.created_at) <= d_hasta,
        )
        .all()
    )

    if not orders:
        return []

    order_ids = [o.id for o in orders]
    logs_by_order: dict = {}
    for log in db.query(OrderEstadoLog).filter(OrderEstadoLog.order_id.in_(order_ids)).all():
        logs_by_order.setdefault(log.order_id, []).append(log)

    audits_by_order: dict = {}
    for al in db.query(AuditLog).filter(
        AuditLog.entidad_id.in_(order_ids),
        AuditLog.accion == "editar_comanda",
    ).all():
        audits_by_order.setdefault(al.entidad_id, []).append(al)

    # Calcular tiempos individuales y agrupar
    grupos: dict = {}
    for o in orders:
        t = _tiempos_orden(o, logs_by_order.get(o.id, []), audits_by_order.get(o.id, []))
        if t["t_total"] is None:
            continue

        # Calcular clave de agrupación
        d = o.created_at.date() if hasattr(o.created_at, "date") else date.fromisoformat(str(o.created_at)[:10])
        if agrupacion == "semana":
            # Lunes de la semana
            key = str(d - timedelta(days=d.weekday()))
        elif agrupacion == "mes":
            key = f"{d.year}-{d.month:02d}-01"
        else:
            key = str(d)

        grupos.setdefault(key, []).append(t)

    resultado = []
    for key in sorted(grupos.keys()):
        ts = grupos[key]
        resultado.append({
            "fecha":            key,
            "count":            len(ts),
            "avg_t_aprobacion": _avg([t["t_aprobacion"] for t in ts]),
            "avg_t_entrega":    _avg([t["t_entrega"]    for t in ts]),
            "avg_t_total":      _avg([t["t_total"]      for t in ts]),
        })

    return resultado


# ─── endpoint: timeline de una comanda específica ────────────────────────────

@router.get("/comanda/{comanda_numero}")
def get_comanda_timeline(
    comanda_numero: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Historial completo de una comanda: transiciones de estado con timestamps y duración.
    """
    # Buscar la comanda más reciente con ese número
    order = (
        db.query(Order)
        .filter(Order.comanda_numero == comanda_numero)
        .order_by(Order.id.desc())
        .first()
    )
    if not order:
        raise HTTPException(404, "Comanda no encontrada")

    # Obtener logs de estado precisos
    logs = (
        db.query(OrderEstadoLog)
        .filter(OrderEstadoLog.order_id == order.id)
        .order_by(OrderEstadoLog.created_at)
        .all()
    )

    # Obtener audit logs de esta orden
    audits = (
        db.query(AuditLog)
        .filter(AuditLog.entidad_id == order.id, AuditLog.accion == "editar_comanda")
        .order_by(AuditLog.created_at)
        .all()
    )

    # Construir timeline
    timeline = []

    # Evento de creación (siempre disponible)
    timeline.append({
        "evento":    "Pedido recibido",
        "estado_de": None,
        "estado_a":  order.estado if not logs else "abierto",
        "timestamp": str(order.created_at),
        "usuario":   None,
        "fuente":    "sistema",
    })

    # Eventos de order_estado_logs (precisos)
    estado_inicial_log = {log.estado_de for log in logs if log.estado_de is None}
    for log in logs:
        if log.estado_de is None:
            continue  # estado inicial, ya lo mostramos arriba
        etiquetas = {
            "en_cocina": "Enviado a cocina / aprobado",
            "listo":     "Listo para entregar",
            "pagado":    "Entregado / pagado",
            "cancelado": "Cancelado",
        }
        timeline.append({
            "evento":    etiquetas.get(log.estado_a, f"→ {log.estado_a}"),
            "estado_de": log.estado_de,
            "estado_a":  log.estado_a,
            "timestamp": str(log.created_at),
            "usuario":   log.usuario_nombre,
            "fuente":    "log",
        })

    # Si no hay logs, complementar con audit_logs para en_cocina
    if not any(e["fuente"] == "log" and e["estado_a"] == "en_cocina" for e in timeline):
        for al in audits:
            try:
                d = json.loads(al.detalle or "{}")
                cambios = d.get("cambios", {})
                if "estado" in cambios:
                    de = cambios["estado"].get("antes")
                    a  = cambios["estado"].get("despues")
                    etiquetas = {
                        "en_cocina": "Enviado a cocina (audit)",
                        "listo":     "Listo para entregar (audit)",
                        "pagado":    "Entregado / pagado (audit)",
                    }
                    timeline.append({
                        "evento":    etiquetas.get(a, f"→ {a}"),
                        "estado_de": de,
                        "estado_a":  a,
                        "timestamp": str(al.created_at),
                        "usuario":   al.usuario_nombre,
                        "fuente":    "audit",
                    })
            except Exception:
                pass

    # Si el pedido está pagado y no tenemos timestamp de pagado, agregar con updated_at
    tiene_pagado = any(e["estado_a"] == "pagado" for e in timeline)
    if not tiene_pagado and order.estado == "pagado" and order.updated_at:
        timeline.append({
            "evento":    "Entregado / pagado (estimado)",
            "estado_de": None,
            "estado_a":  "pagado",
            "timestamp": str(order.updated_at),
            "usuario":   None,
            "fuente":    "estimado",
        })

    # Ordenar por timestamp
    timeline.sort(key=lambda e: e["timestamp"])

    # Calcular duración entre eventos consecutivos
    for i in range(1, len(timeline)):
        try:
            t0 = _parse_dt(timeline[i-1]["timestamp"])
            t1 = _parse_dt(timeline[i]["timestamp"])
            m  = _mins(t0, t1)
            timeline[i]["duracion_desde_anterior_min"] = m
        except Exception:
            timeline[i]["duracion_desde_anterior_min"] = None

    if timeline:
        timeline[0]["duracion_desde_anterior_min"] = None

    # Resumen de tiempos totales
    tiempos = _tiempos_orden(order, logs, audits)

    # Info del domiciliario
    dom_nombre = None
    if order.domiciliario_id:
        dom = db.query(Domiciliario).filter(Domiciliario.id == order.domiciliario_id).first()
        if dom:
            dom_nombre = dom.nombre

    return {
        "comanda_numero":    order.comanda_numero,
        "order_id":          order.id,
        "tipo":              order.tipo,
        "estado_actual":     order.estado,
        "cliente_nombre":    order.cliente_nombre,
        "cliente_direccion": order.cliente_direccion,
        "domiciliario":      dom_nombre,
        "total":             float(order.total or 0),
        "valor_domicilio":   float(order.valor_domicilio or 0),
        "metodo_pago":       order.metodo_pago,
        "created_at":        str(order.created_at),
        "timeline":          timeline,
        "tiempos_min":       tiempos,
    }
