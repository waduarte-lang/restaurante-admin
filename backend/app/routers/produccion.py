"""Módulo de Producción — industria plástica.

Conecta a la base de datos comercial externa (PostgreSQL) y expone los
endpoints necesarios para el panel de producción.
"""
from __future__ import annotations

import decimal
from datetime import date, datetime, time, timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database_produccion import get_prod_db

router = APIRouter(prefix="/api/produccion", tags=["produccion"])


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _serialize(v: Any) -> Any:
    """Convierte tipos no-JSON-serializables a primitivos."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, timedelta):
        return v.total_seconds()
    return v


def _rows(result) -> list[dict]:
    keys = list(result.keys())
    return [{k: _serialize(v) for k, v in zip(keys, row)} for row in result.fetchall()]


def _row(result) -> dict | None:
    keys = list(result.keys())
    row = result.fetchone()
    return {k: _serialize(v) for k, v in zip(keys, row)} if row else None


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD — KPIs en tiempo real
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_prod_db)):
    hoy = date.today()

    # Órdenes activas por estado
    estados = _rows(db.execute(text("""
        SELECT status, COUNT(*) as total
        FROM production_order
        WHERE "isActive" = true
        GROUP BY status
    """)))

    # Unidades producidas hoy (corridas finalizadas)
    unidades_hoy = _row(db.execute(text("""
        SELECT
            COALESCE(SUM(pr.units_produced), 0)  AS producidas,
            COALESCE(SUM(pr.units_defective), 0) AS defectuosas
        FROM production_run pr
        WHERE pr.start_time::date = :hoy
    """), {"hoy": hoy}))

    # Máquinas activas / en paro
    maquinas = _rows(db.execute(text("""
        SELECT
            m."currentStatus",
            COUNT(*) as total
        FROM machine m
        WHERE m."isActive" = true
        GROUP BY m."currentStatus"
    """)))

    # Paros no cerrados en las últimas 24h
    paros_activos = _row(db.execute(text("""
        SELECT COUNT(*) as total
        FROM machine_stop_records
        WHERE end_time IS NULL
          AND start_time >= NOW() - INTERVAL '24 hours'
    """)))

    # Órdenes en proceso por área
    por_area = _rows(db.execute(text("""
        SELECT a.name AS area, COUNT(po.id) AS ordenes
        FROM production_order po
        JOIN machine m ON m.id = po.machine_id
        JOIN area a ON a.id = (
            SELECT "areaId" FROM mold WHERE id = (
                SELECT "moldId" FROM product WHERE id = (
                    SELECT product_id FROM sales_order_product WHERE id = po.sales_order_product_id
                )
            )
        )
        WHERE po.status IN ('programada','en_proceso')
          AND po."isActive" = true
        GROUP BY a.name
    """)))

    # Eficiencia últimos 7 días
    eficiencia = _rows(db.execute(text("""
        SELECT
            pr.start_time::date AS fecha,
            SUM(pr.units_produced)  AS producidas,
            SUM(pr.units_defective) AS defectuosas,
            COUNT(pr.id) AS corridas
        FROM production_run pr
        WHERE pr.start_time >= NOW() - INTERVAL '7 days'
        GROUP BY pr.start_time::date
        ORDER BY fecha
    """)))

    # Órdenes terminadas este mes
    terminadas_mes = _row(db.execute(text("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(quantity_produced), 0) AS unidades
        FROM production_order
        WHERE status = 'terminada'
          AND "isActive" = true
          AND DATE_TRUNC('month', updated_at) = DATE_TRUNC('month', NOW())
    """)))

    # Top 5 productos más producidos este mes
    top_productos = _rows(db.execute(text("""
        SELECT p.name AS producto, p.sku,
               SUM(po.quantity_produced) AS unidades
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        WHERE po.status = 'terminada'
          AND po."isActive" = true
          AND DATE_TRUNC('month', po.updated_at) = DATE_TRUNC('month', NOW())
        GROUP BY p.name, p.sku
        ORDER BY unidades DESC
        LIMIT 5
    """)))

    return {
        "estados_ordenes": [dict(r) for r in estados],
        "unidades_hoy": dict(unidades_hoy) if unidades_hoy else {},
        "maquinas_estado": [dict(r) for r in maquinas],
        "paros_activos": dict(paros_activos)["total"] if paros_activos else 0,
        "por_area": [dict(r) for r in por_area],
        "eficiencia_7dias": [dict(r) for r in eficiencia],
        "terminadas_mes": dict(terminadas_mes) if terminadas_mes else {},
        "top_productos": [dict(r) for r in top_productos],
    }


# ─────────────────────────────────────────────────────────────────────────────
# ÓRDENES DE PRODUCCIÓN
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ordenes")
def listar_ordenes(
    estado: Optional[str] = None,
    area: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    buscar: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_prod_db),
):
    filters = ["po.\"isActive\" = true"]
    params: dict[str, Any] = {}

    if estado:
        filters.append("po.status = :estado")
        params["estado"] = estado
    if fecha_desde:
        filters.append("po.updated_at::date >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        filters.append("po.updated_at::date <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta
    if buscar:
        filters.append("(po.order_number ILIKE :buscar OR p.name ILIKE :buscar OR p.sku ILIKE :buscar OR c.\"mainContact\" ILIKE :buscar)")
        params["buscar"] = f"%{buscar}%"
    if area:
        filters.append("a.name ILIKE :area")
        params["area"] = f"%{area}%"

    where = " AND ".join(filters)
    offset = (page - 1) * per_page
    params.update({"limit": per_page, "offset": offset})

    sql = text(f"""
        SELECT
            po.id,
            po.order_number,
            po.status,
            po.priority,
            po.quantity_to_produce,
            po.quantity_produced,
            po.quantity_defective,
            po.actual_start_date,
            po.actual_end_date,
            po.created_at,
            po.notes,
            po.batch_code,
            po.estimated_production_time,
            p.id   AS product_id,
            p.name AS product_name,
            p.sku  AS product_sku,
            p.color AS product_color,
            m.name AS machine_name,
            m.type AS machine_type,
            md.name AS mold_name,
            md.cavities,
            a.name AS area_name,
            so.order_number AS sales_order_number,
            c."businessName" AS customer_name,
            sc.name AS shift_name,
            ROUND(
                CASE WHEN po.quantity_to_produce > 0
                THEN (po.quantity_produced::numeric / po.quantity_to_produce) * 100
                ELSE 0 END, 1
            ) AS avance_pct
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN mold md ON md.id = p."moldId"
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        LEFT JOIN shift_category sc ON sc.id = po.shift_category_id
        WHERE {where}
        ORDER BY
            CASE po.status
                WHEN 'en_proceso' THEN 1
                WHEN 'programada' THEN 2
                WHEN 'pausada'    THEN 3
                ELSE 4
            END,
            po.priority ASC,
            po.updated_at DESC
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"""
        SELECT COUNT(*) FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN mold md ON md.id = p."moldId"
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE {where}
    """)

    rows = _rows(db.execute(sql, params))
    total = db.execute(count_sql, {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar()

    return {
        "items": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": -(-total // per_page),
    }


@router.get("/ordenes/{orden_id}")
def detalle_orden(
    orden_id: str,
    db: Session = Depends(get_prod_db),
):
    orden = _row(db.execute(text("""
        SELECT
            po.*,
            p.name AS product_name, p.sku, p.color, p.weight, p."theoreticalCycle",
            p.price, p."packagingUnit",
            m.name AS machine_name, m.type AS machine_type, m."referenceCode",
            md.name AS mold_name, md.code AS mold_code, md.cavities, md."maintenanceUnits",
            a.name AS area_name,
            so.order_number AS sales_order_number, so.delivery_date,
            c."businessName" AS customer_name, c.city AS customer_city,
            sc.name AS shift_name, sc."startTime" AS shift_start, sc."endTime" AS shift_end,
            u_created.email AS created_by_name,
            u_approved.email AS approved_by_name,
            ROUND(
                CASE WHEN po.quantity_to_produce > 0
                THEN (po.quantity_produced::numeric / po.quantity_to_produce) * 100
                ELSE 0 END, 1
            ) AS avance_pct
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN mold md ON md.id = p."moldId"
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        LEFT JOIN shift_category sc ON sc.id = po.shift_category_id
        LEFT JOIN "user" u_created ON u_created.id = po.created_by_id
        LEFT JOIN "user" u_approved ON u_approved.id = po.approved_by_id
        WHERE po.id = :id AND po."isActive" = true
    """), {"id": orden_id}))

    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # Corridas de producción
    runs = _rows(db.execute(text("""
        SELECT pr.*
        FROM production_run pr
        WHERE pr.production_order_id = :id
        ORDER BY pr.start_time DESC
    """), {"id": orden_id}))

    # Historial de estados
    historial = _rows(db.execute(text("""
        SELECT posh.*, u.email AS changed_by
        FROM production_order_status_history posh
        LEFT JOIN "user" u ON u.id = posh.user_id
        WHERE posh.production_order_id = :id
        ORDER BY posh.change_date DESC
    """), {"id": orden_id}))

    # Parámetros de proceso
    params_rec = _rows(db.execute(text("""
        SELECT pop.parameter_type, pop.parameters, pop.recorded_at,
               u.email AS recorded_by
        FROM production_order_parameters pop
        LEFT JOIN "user" u ON u.id = pop.recorded_by_id
        WHERE pop.production_order_id = :id
        ORDER BY pop.recorded_at DESC
    """), {"id": orden_id}))

    # Control de calidad
    qc_records = _rows(db.execute(text("""
        SELECT qc.*, u.email AS responsible_name
        FROM quality_control qc
        LEFT JOIN "user" u ON u.id = qc.responsible_id
        WHERE qc.production_order_id = :id
        ORDER BY qc.inspection_date DESC
    """), {"id": orden_id}))

    # Solicitudes de material
    mat_requests = _rows(db.execute(text("""
        SELECT mr.id, mr.status, mr."createdAt", mr."approvedAt",
               mri.quantity, mri.unit,
               rm.name AS material_name, rm.type AS material_type
        FROM material_request mr
        JOIN material_request_item mri ON mri."materialRequestId" = mr.id
        JOIN raw_material rm ON rm.id = mri."rawMaterialId"
        WHERE mr."productionOrderId" = :id
        ORDER BY mr."createdAt" DESC
    """), {"id": orden_id}))

    return {
        **orden,
        "runs": [dict(r) for r in runs],
        "historial_estados": [dict(h) for h in historial],
        "parametros": [dict(p) for p in params_rec],
        "calidad": [dict(q) for q in qc_records],
        "solicitudes_material": [dict(m) for m in mat_requests],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CORRIDAS DE PRODUCCIÓN (Production Runs)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/corridas")
def listar_corridas(
    activas: bool = False,
    orden_id: Optional[str] = None,
    fecha: Optional[date] = None,
    db: Session = Depends(get_prod_db),
):
    filters = ["1=1"]
    params: dict[str, Any] = {}

    if activas:
        filters.append("pr.status IN ('INICIADO','EN_PROGRESO','PAUSADO')")
    if orden_id:
        filters.append("pr.production_order_id = :orden_id")
        params["orden_id"] = orden_id
    if fecha:
        filters.append("pr.start_time::date = :fecha")
        params["fecha"] = fecha

    where = " AND ".join(filters)

    rows = _rows(db.execute(text(f"""
        SELECT
            pr.id, pr.status, pr.start_time, pr.end_time,
            pr.units_produced, pr.units_defective, pr.total_cycles,
            pr.target_cycle_time, pr.actual_cycle_time, pr.avg_cycle_time,
            pr.real_cavities,
            po.order_number,
            p.name AS product_name, p.sku,
            m.name AS machine_name, m.type AS machine_type,
            e."firstNames" || ' ' || e."paternalLastName" AS operator_name,
            EXTRACT(EPOCH FROM (COALESCE(pr.end_time, NOW()) - pr.start_time))/3600 AS horas_corrida,
            COUNT(msr.id) FILTER (WHERE msr.end_time IS NULL) AS paros_activos,
            COUNT(msr.id) AS total_paros
        FROM production_run pr
        JOIN production_order po ON po.id = pr.production_order_id
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN employee e ON e.id = pr.operator_id::integer
        LEFT JOIN machine_stop_records msr ON msr.production_run_id = pr.id
        WHERE {where}
        GROUP BY pr.id, po.order_number, p.name, p.sku, m.name, m.type, e."firstNames", e."paternalLastName"
        ORDER BY pr.start_time DESC
        LIMIT 100
    """), params))

    return [dict(r) for r in rows]


@router.get("/corridas/{run_id}/paros")
def paros_corrida(
    run_id: str,
    db: Session = Depends(get_prod_db),
):
    rows = _rows(db.execute(text("""
        SELECT
            msr.*,
            cs.name AS categoria_nombre, cs.type AS categoria_tipo,
            e1."firstNames" || ' ' || e1."paternalLastName" AS reportado_por,
            e2."firstNames" || ' ' || e2."paternalLastName" AS resuelto_por,
            EXTRACT(EPOCH FROM (COALESCE(msr.end_time, NOW()) - msr.start_time))/60 AS minutos_paro
        FROM machine_stop_records msr
        LEFT JOIN category_stop cs ON cs.name = msr.category
        LEFT JOIN employee e1 ON e1.id = msr.reported_by_id::integer
        LEFT JOIN employee e2 ON e2.id = msr.resolved_by_id::integer
        WHERE msr.production_run_id = :id
        ORDER BY msr.start_time DESC
    """), {"id": run_id}))
    return [dict(r) for r in rows]


@router.get("/corridas/{run_id}/defectos")
def defectos_corrida(
    run_id: str,
    db: Session = Depends(get_prod_db),
):
    rows = _rows(db.execute(text("""
        SELECT
            dur.*,
            e1."firstNames" || ' ' || e1."paternalLastName" AS contado_por,
            e2."firstNames" || ' ' || e2."paternalLastName" AS justificado_por
        FROM defective_unit_records dur
        LEFT JOIN employee e1 ON e1.id = dur.counted_by_id::integer
        LEFT JOIN employee e2 ON e2.id = dur.justified_by_id::integer
        WHERE dur.production_run_id = :id
        ORDER BY dur.recorded_at DESC
    """), {"id": run_id}))
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# MÁQUINAS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/maquinas")
def listar_maquinas(
    db: Session = Depends(get_prod_db),
):
    rows = _rows(db.execute(text("""
        SELECT
            m.*,
            a.name AS area_nombre,
            -- Orden activa actual
            po.order_number AS orden_activa,
            po.id AS orden_activa_id,
            po.status AS orden_status,
            p.name AS producto_actual,
            -- Mantenimientos recientes
            (SELECT COUNT(*) FROM machine_maintenance mm
             WHERE mm."machineId" = m.id
               AND mm."maintenanceDate" >= NOW() - INTERVAL '90 days') AS mantenimientos_90d,
            -- Última corrida
            (SELECT MAX(pr.start_time) FROM production_run pr
             JOIN production_order po2 ON po2.id = pr.production_order_id
             WHERE po2.machine_id = m.id) AS ultima_corrida,
            -- Paros activos
            (SELECT COUNT(*) FROM machine_stop_records msr
             JOIN production_run pr ON pr.id = msr.production_run_id
             JOIN production_order po3 ON po3.id = pr.production_order_id
             WHERE po3.machine_id = m.id AND msr.end_time IS NULL) AS paros_activos,
            -- Cola de producción: órdenes programadas
            (SELECT COUNT(*) FROM production_order po_q
             WHERE po_q.machine_id = m.id AND po_q.status = 'programada'
               AND po_q."isActive" = true) AS ordenes_cola,
            (SELECT ROUND(COALESCE(SUM(
                GREATEST(po_q.quantity_to_produce - po_q.quantity_produced, 0)
                * COALESCE(p_q.weight, 0) / 1000.0
             ), 0)::numeric, 1)
             FROM production_order po_q
             JOIN sales_order_product sop_q ON sop_q.id = po_q.sales_order_product_id
             JOIN product p_q ON p_q.id = sop_q.product_id
             WHERE po_q.machine_id = m.id AND po_q.status = 'programada'
               AND po_q."isActive" = true) AS cola_kg,
            -- Kg producidos últimos 30 días
            (SELECT ROUND(COALESCE(SUM(
                po_t.quantity_produced * COALESCE(p_t.weight, 0) / 1000.0
             ), 0)::numeric, 0)
             FROM production_order po_t
             JOIN sales_order_product sop_t ON sop_t.id = po_t.sales_order_product_id
             JOIN product p_t ON p_t.id = sop_t.product_id
             WHERE po_t.machine_id = m.id AND po_t.status = 'terminada'
               AND po_t."isActive" = true
               AND po_t.actual_end_date >= NOW() - INTERVAL '90 days') AS kg_90d
        FROM machine m
        LEFT JOIN area a ON a.id = (
            SELECT "areaId" FROM mold md
            JOIN product pr ON pr."moldId" = md.id
            JOIN sales_order_product sop ON sop.product_id = pr.id
            JOIN production_order po4 ON po4.sales_order_product_id = sop.id
            WHERE po4.machine_id = m.id AND po4.status = 'en_proceso'
              AND po4."isActive" = true
            LIMIT 1
        )
        LEFT JOIN LATERAL (
            SELECT po.order_number, po.id, po.status, sop2.product_id
            FROM production_order po
            JOIN sales_order_product sop2 ON sop2.id = po.sales_order_product_id
            WHERE po.machine_id = m.id AND po.status = 'en_proceso' AND po."isActive" = true
            ORDER BY po.created_at DESC
            LIMIT 1
        ) po ON true
        LEFT JOIN product p ON p.id = po.product_id
        WHERE m."isActive" = true
        ORDER BY m.type, m.name
    """)))
    result = []
    for r in rows:
        m = dict(r)
        cola_kg = float(m.get("cola_kg") or 0)
        kg_90d  = float(m.get("kg_90d") or 0)
        ritmo   = kg_90d / 90.0
        m["cola_dias"] = round(cola_kg / ritmo, 1) if ritmo > 0 else None
        result.append(m)
    return result


@router.get("/maquinas/{maquina_id}/mantenimientos")
def mantenimientos_maquina(
    maquina_id: str,
    db: Session = Depends(get_prod_db),
):
    rows = _rows(db.execute(text("""
        SELECT mm.*
        FROM machine_maintenance mm
        WHERE mm."machineId" = :id
        ORDER BY mm."maintenanceDate" DESC
        LIMIT 50
    """), {"id": maquina_id}))
    return [dict(r) for r in rows]


@router.get("/maquinas/{maquina_id}/detalle")
def detalle_maquina(maquina_id: str, db: Session = Depends(get_prod_db)):
    """Devuelve cola de órdenes programadas, historial reciente y mantenimientos."""
    cola = _rows(db.execute(text("""
        SELECT
            po.order_number,
            po.id         AS orden_id,
            po.priority,
            po.quantity_to_produce,
            po.quantity_produced,
            GREATEST(po.quantity_to_produce - po.quantity_produced, 0) AS qty_pendiente,
            ROUND((GREATEST(po.quantity_to_produce - po.quantity_produced, 0)
                   * COALESCE(p.weight, 0) / 1000.0)::numeric, 1)     AS kg_pendientes,
            p.name        AS product_name,
            p.sku,
            p.color,
            p.weight      AS peso_nominal,
            COALESCE(p."theoreticalCycle", 0)    AS ciclo_teorico_s,
            COALESCE(p."numberOfCavities", 1)    AS cavidades,
            so.order_number AS sales_order,
            c."mainContact" AS cliente,
            sop.delivery_date,
            (
                SELECT ROUND(AVG(
                    CASE WHEN pr.real_cavities > 0
                         THEN pr.avg_cycle_time / pr.real_cavities END
                )::numeric, 2)
                FROM production_run pr
                JOIN production_order po2 ON po2.id = pr.production_order_id
                JOIN sales_order_product sop2 ON sop2.id = po2.sales_order_product_id
                WHERE sop2.product_id = p.id
            ) AS seg_real_por_pieza
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p               ON p.id   = sop.product_id
        LEFT JOIN sales_order so     ON so.id  = sop.sales_order_id
        LEFT JOIN customer c         ON c.id   = so.customer_id
        WHERE po.machine_id = :id AND po.status = 'programada' AND po."isActive" = true
        ORDER BY po.priority ASC, sop.delivery_date ASC
        LIMIT 50
    """), {"id": maquina_id}))

    historial = _rows(db.execute(text("""
        SELECT
            po.order_number,
            po.quantity_produced,
            po.quantity_defective,
            ROUND((po.quantity_produced * COALESCE(p.weight, 0) / 1000.0)::numeric, 1) AS kg_producidos,
            p.name AS product_name,
            p.sku,
            po.actual_start_date::date AS inicio,
            po.actual_end_date::date   AS fin,
            ROUND(EXTRACT(EPOCH FROM (po.actual_end_date - po.actual_start_date)) / 3600.0, 1) AS horas
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p               ON p.id   = sop.product_id
        WHERE po.machine_id = :id AND po.status = 'terminada' AND po."isActive" = true
          AND po.actual_end_date IS NOT NULL
        ORDER BY po.actual_end_date DESC
        LIMIT 10
    """), {"id": maquina_id}))

    mantenimientos = _rows(db.execute(text("""
        SELECT mm.*
        FROM machine_maintenance mm
        WHERE mm."machineId" = :id
        ORDER BY mm."maintenanceDate" DESC
        LIMIT 20
    """), {"id": maquina_id}))

    return {
        "cola":          [dict(r) for r in cola],
        "historial":     [dict(r) for r in historial],
        "mantenimientos":[dict(r) for r in mantenimientos],
    }


# ─────────────────────────────────────────────────────────────────────────────
# MOLDES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/moldes")
def listar_moldes(
    estado: Optional[str] = None,
    area_id: Optional[int] = None,
    buscar: Optional[str] = None,
    db: Session = Depends(get_prod_db),
):
    filters = ["md.\"isActive\" = true"]
    params: dict[str, Any] = {}

    if estado:
        filters.append("md.status = :estado")
        params["estado"] = estado
    if area_id:
        filters.append('md."areaId" = :area_id')
        params["area_id"] = area_id
    if buscar:
        filters.append("(md.name ILIKE :buscar OR md.code ILIKE :buscar)")
        params["buscar"] = f"%{buscar}%"

    where = " AND ".join(filters)

    rows = _rows(db.execute(text(f"""
        SELECT
            md.*,
            a.name AS area_nombre,
            p.name AS product_name, p.sku,
            (SELECT COUNT(*) FROM mold_machine_compatibility mmc WHERE mmc."moldId" = md.id) AS maquinas_compatibles,
            (SELECT name FROM machine WHERE id = (
                SELECT po.machine_id FROM production_order po
                JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
                JOIN product pp ON pp.id = sop.product_id
                WHERE pp."moldId" = md.id AND po.status = 'en_proceso' AND po."isActive" = true
                LIMIT 1
            )) AS maquina_actual
        FROM mold md
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN product p ON p."moldId" = md.id AND p."isActive" = true
        WHERE {where}
        ORDER BY md."areaId", md.name
    """), params))
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# MATERIAS PRIMAS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/materias-primas")
def listar_materias_primas(
    tipo: Optional[str] = None,
    bajo_stock: bool = False,
    buscar: Optional[str] = None,
    db: Session = Depends(get_prod_db),
):
    filters = ["rm.\"isActive\" = true"]
    params: dict[str, Any] = {}

    if tipo:
        filters.append("rm.type = :tipo")
        params["tipo"] = tipo
    if buscar:
        filters.append("(rm.name ILIKE :buscar OR rm.color ILIKE :buscar)")
        params["buscar"] = f"%{buscar}%"
    if bajo_stock:
        filters.append('(SELECT COALESCE(SUM(b."availableQuantity"),0) FROM raw_material_batch b WHERE b.raw_material_id = rm.id) <= rm."minimumStock"')

    where = " AND ".join(filters)

    rows = _rows(db.execute(text(f"""
        SELECT
            rm.*,
            COALESCE(SUM(b."availableQuantity"), 0) AS stock_actual,
            COUNT(b.id) AS lotes_activos,
            (COALESCE(SUM(b."availableQuantity"), 0) <= rm."minimumStock") AS bajo_stock
        FROM raw_material rm
        LEFT JOIN raw_material_batch b ON b.raw_material_id = rm.id
          AND b."availableQuantity" > 0
        WHERE {where}
        GROUP BY rm.id
        ORDER BY bajo_stock DESC, rm.type, rm.name
    """), params))
    return [dict(r) for r in rows]


@router.get("/materias-primas/{rm_id}/movimientos")
def movimientos_materia_prima(
    rm_id: str,
    db: Session = Depends(get_prod_db),
):
    rows = _rows(db.execute(text("""
        SELECT
            rmm.*,
            s.name AS supplier_name,
            b.supplier_batch_code AS batch_code
        FROM raw_material_movement rmm
        LEFT JOIN supplier s ON s.id = rmm.supplier_id
        LEFT JOIN raw_material_batch b ON b.id = rmm.batch_id
        WHERE rmm.raw_material_id = :id
        ORDER BY rmm.movement_date DESC
        LIMIT 100
    """), {"id": rm_id}))
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# CONTROL DE CALIDAD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/calidad")
def listar_calidad(
    orden_id: Optional[str] = None,
    tipo_muestra: Optional[str] = None,
    estado: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    db: Session = Depends(get_prod_db),
):
    filters = ['qc."isActive" = true']
    params: dict[str, Any] = {}

    if orden_id:
        filters.append("qc.production_order_id = :orden_id")
        params["orden_id"] = orden_id
    if tipo_muestra:
        filters.append("qc.sample_type = :tipo_muestra")
        params["tipo_muestra"] = tipo_muestra
    if estado:
        filters.append("qc.status = :estado")
        params["estado"] = estado
    if fecha_desde:
        filters.append("qc.inspection_date::date >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        filters.append("qc.inspection_date::date <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta

    where = " AND ".join(filters)

    rows = _rows(db.execute(text(f"""
        SELECT
            qc.*,
            po.order_number,
            p.name AS product_name, p.sku,
            u.username AS responsible_name
        FROM quality_control qc
        JOIN production_order po ON po.id = qc.production_order_id
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN "user" u ON u.id = qc.responsible_id
        WHERE {where}
        ORDER BY qc.inspection_date DESC
        LIMIT 200
    """), params))
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# PAROS DE MÁQUINA — análisis
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/paros")
def listar_paros(
    activos: bool = False,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    maquina_id: Optional[str] = None,
    db: Session = Depends(get_prod_db),
):
    filters = ["1=1"]
    params: dict[str, Any] = {}

    if activos:
        filters.append("msr.end_time IS NULL")
    if fecha_desde:
        filters.append("msr.start_time::date >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta:
        filters.append("msr.start_time::date <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta
    if maquina_id:
        filters.append("po.machine_id = :maquina_id")
        params["maquina_id"] = maquina_id

    where = " AND ".join(filters)

    rows = _rows(db.execute(text(f"""
        SELECT
            msr.id, msr.stop_reason, msr.detailed_description,
            msr.start_time, msr.end_time, msr.is_planned, msr.category,
            EXTRACT(EPOCH FROM (COALESCE(msr.end_time, NOW()) - msr.start_time))/60 AS minutos_paro,
            cs.name AS categoria_nombre, cs.type AS categoria_tipo,
            m.name AS machine_name, m.type AS machine_type,
            po.order_number,
            p.name AS product_name,
            e1."firstNames" || ' ' || e1."paternalLastName" AS reportado_por,
            e2."firstNames" || ' ' || e2."paternalLastName" AS resuelto_por
        FROM machine_stop_records msr
        JOIN production_run pr ON pr.id = msr.production_run_id
        JOIN production_order po ON po.id = pr.production_order_id
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN category_stop cs ON cs.name = msr.category
        LEFT JOIN employee e1 ON e1.id = msr.reported_by_id::integer
        LEFT JOIN employee e2 ON e2.id = msr.resolved_by_id::integer
        WHERE {where}
        ORDER BY msr.start_time DESC
        LIMIT 200
    """), params))

    # Resumen por categoría
    resumen = _rows(db.execute(text(f"""
        SELECT
            COALESCE(msr.category, 'Sin categoría') AS categoria,
            COUNT(*) AS cantidad,
            ROUND(SUM(EXTRACT(EPOCH FROM (COALESCE(msr.end_time, NOW()) - msr.start_time))/60)::numeric, 1) AS minutos_total,
            msr.is_planned
        FROM machine_stop_records msr
        JOIN production_run pr ON pr.id = msr.production_run_id
        JOIN production_order po ON po.id = pr.production_order_id
        LEFT JOIN machine m ON m.id = po.machine_id
        WHERE {where}
        GROUP BY msr.category, msr.is_planned
        ORDER BY minutos_total DESC
    """), params))

    return {
        "paros": [dict(r) for r in rows],
        "resumen_categorias": [dict(r) for r in resumen],
    }


# ─────────────────────────────────────────────────────────────────────────────
# TURNOS Y EQUIPOS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/turnos")
def listar_turnos(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    area_id: Optional[int] = None,
    db: Session = Depends(get_prod_db),
):
    if not fecha_desde:
        fecha_desde = date.today()
    if not fecha_hasta:
        fecha_hasta = date.today() + timedelta(days=7)

    params: dict[str, Any] = {"desde": fecha_desde, "hasta": fecha_hasta}
    area_filter = ""
    if area_id:
        area_filter = 'AND s."areaId" = :area_id'
        params["area_id"] = area_id

    rows = _rows(db.execute(text(f"""
        SELECT
            s.id, s."startDate", s."endDate", s.status, s.notes,
            sc.name AS turno_nombre, sc."startTime", sc."endTime", sc."durationMinutes",
            a.name AS area_nombre,
            t.name AS equipo_nombre,
            e_sup."firstNames" || ' ' || e_sup."paternalLastName" AS supervisor_nombre,
            COUNT(DISTINCT op."operatorId") AS num_operarios
        FROM shift s
        JOIN shift_category sc ON sc.id = s."shiftCategoryId"
        JOIN area a ON a.id = s."areaId"
        LEFT JOIN team t ON t.id = s."teamId"
        LEFT JOIN employee e_sup ON e_sup.id = s."supervisorId"
        LEFT JOIN operator_shift op ON op."shiftId" = s.id
        WHERE s."startDate" <= :hasta
          AND s."endDate" >= :desde
          AND s."isActive" = true
          {area_filter}
        GROUP BY s.id, sc.name, sc."startTime", sc."endTime", sc."durationMinutes",
                 a.name, t.name, e_sup."firstNames", e_sup."paternalLastName"
        ORDER BY s."startDate", a.name, sc."startTime"
    """), params))
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# REPORTES DE PRODUCCIÓN
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/reportes/resumen-diario")
def reporte_diario(
    fecha: Optional[date] = None,
    db: Session = Depends(get_prod_db),
):
    """Resumen de órdenes terminadas en la fecha indicada (actual_end_date)."""
    if not fecha:
        fecha = date.today()

    por_maquina = _rows(db.execute(text("""
        SELECT
            m.name AS maquina, m.type AS tipo,
            COUNT(po.id) AS corridas,
            SUM(po.quantity_produced) AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            NULL AS ciclo_promedio,
            NULL AS horas_corrida,
            0 AS total_paros,
            0 AS minutos_paro
        FROM production_order po
        LEFT JOIN machine m ON m.id = po.machine_id
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date = :fecha
        GROUP BY m.name, m.type
        ORDER BY producidas DESC
    """), {"fecha": fecha}))

    por_area = _rows(db.execute(text("""
        SELECT
            a.name AS area,
            SUM(po.quantity_produced) AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            ROUND(
                CASE WHEN SUM(po.quantity_produced) > 0
                THEN (1 - SUM(po.quantity_defective)::numeric / NULLIF(SUM(po.quantity_produced),0)) * 100
                ELSE 0 END, 2
            ) AS calidad_pct
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        JOIN mold md ON md.id = p."moldId"
        JOIN area a ON a.id = md."areaId"
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date = :fecha
        GROUP BY a.name
        ORDER BY producidas DESC
    """), {"fecha": fecha}))

    # Turno: sin corridas no hay datos de turno; omitimos por ahora
    return {
        "fecha": str(fecha),
        "por_maquina": [dict(r) for r in por_maquina],
        "por_area": [dict(r) for r in por_area],
        "por_turno": [],
    }


@router.get("/reportes/oee")
def reporte_oee(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    maquina_id: Optional[str] = None,
    db: Session = Depends(get_prod_db),
):
    """Rendimiento por máquina basado en órdenes terminadas (actual_end_date)."""
    if not fecha_desde:
        fecha_desde = date.today() - timedelta(days=30)
    if not fecha_hasta:
        fecha_hasta = date.today()

    params: dict[str, Any] = {"desde": fecha_desde, "hasta": fecha_hasta}
    maq_filter = ""
    if maquina_id:
        maq_filter = "AND po.machine_id = :maquina_id"
        params["maquina_id"] = maquina_id

    rows = _rows(db.execute(text(f"""
        SELECT
            m.name AS maquina, m.type AS tipo,
            COALESCE(m."hoursPerDay", 8) AS hoursPerDay,
            COUNT(po.id) AS corridas,
            SUM(po.quantity_produced) AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            NULL AS ciclo_promedio_seg,
            NULL AS tiempo_produccion_seg,
            0 AS tiempo_paros_seg,
            ROUND(
                CASE WHEN SUM(po.quantity_to_produce) > 0
                THEN (SUM(po.quantity_produced)::numeric / NULLIF(SUM(po.quantity_to_produce), 0)) * 100
                ELSE 0 END::numeric, 2
            ) AS disponibilidad_pct,
            ROUND(
                CASE WHEN SUM(po.quantity_produced) > 0
                THEN (1 - SUM(po.quantity_defective)::numeric / NULLIF(SUM(po.quantity_produced), 0)) * 100
                ELSE 0 END::numeric, 2
            ) AS calidad_pct
        FROM production_order po
        LEFT JOIN machine m ON m.id = po.machine_id
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter}
        GROUP BY m.id, m.name, m.type, m."hoursPerDay"
        HAVING SUM(po.quantity_produced) > 0
        ORDER BY producidas DESC
    """), params))
    return [dict(r) for r in rows]


@router.get("/reportes/tiempos-referencia")
def reporte_tiempos_referencia(db: Session = Depends(get_prod_db)):
    """Tiempo real por pieza desde que la orden pasa a en_proceso hasta que queda terminada.
    Fuente: production_order.actual_start_date → actual_end_date / quantity_produced.
    También incluye tiempo de ciclo de máquina (production_run) como referencia técnica.
    """
    rows = _rows(db.execute(text("""
        WITH orden_tiempos AS (
            -- Tiempo real por orden: desde en_proceso hasta terminada
            SELECT
                sop.product_id,
                po.machine_id,
                po.quantity_produced,
                -- Seg reales por pieza (tiempo total de la orden / unidades)
                EXTRACT(EPOCH FROM (po.actual_end_date - po.actual_start_date))
                    / NULLIF(po.quantity_produced, 0)       AS seg_real_por_pieza,
                EXTRACT(EPOCH FROM (po.actual_end_date - po.actual_start_date)) / 3600.0
                                                            AS horas_reales,
                EXTRACT(EPOCH FROM (po.actual_end_date - po.actual_start_date)) / 86400.0
                                                            AS dias_reales,
                po.actual_end_date
            FROM production_order po
            JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
            WHERE po."isActive" = true
              AND po.status = 'terminada'
              AND po.actual_start_date IS NOT NULL
              AND po.actual_end_date IS NOT NULL
              AND po.quantity_produced > 0
              AND po.actual_end_date > po.actual_start_date
        ),
        ciclo_maquina AS (
            -- Ciclo puro de máquina (production_run) por producto
            SELECT
                sop.product_id,
                AVG(pr.avg_cycle_time / NULLIF(pr.real_cavities, 0)) AS seg_ciclo,
                AVG(pr.real_cavities)                                  AS cavidades
            FROM production_run pr
            JOIN production_order po ON po.id = pr.production_order_id
            JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
            WHERE pr.end_time IS NOT NULL AND pr.real_cavities > 0 AND pr.avg_cycle_time > 0
            GROUP BY sop.product_id
        )
        SELECT
            p.id::text                                         AS product_id,
            p.name                                             AS producto,
            p.sku,
            p.color,
            m.name                                             AS maquina_habitual,
            m.type                                             AS tipo_maquina,
            COUNT(*)                                           AS total_ordenes,
            SUM(ot.quantity_produced)                          AS total_producido,
            -- ── Tiempo REAL (en_proceso → terminada) ───────────────────────
            ROUND(AVG(ot.seg_real_por_pieza)::numeric, 3)     AS seg_por_pieza_avg,
            ROUND(MIN(ot.seg_real_por_pieza)::numeric, 3)     AS seg_por_pieza_min,
            ROUND(MAX(ot.seg_real_por_pieza)::numeric, 3)     AS seg_por_pieza_max,
            ROUND(STDDEV(ot.seg_real_por_pieza)::numeric, 3)  AS seg_por_pieza_stddev,
            -- UPH real (unidades que salen por hora real de producción)
            ROUND(
                3600.0 / NULLIF(AVG(ot.seg_real_por_pieza), 0)
            ::numeric, 0)                                      AS uph_real,
            -- Horas y días reales promedio por orden
            ROUND(AVG(ot.horas_reales)::numeric, 1)           AS horas_reales_avg,
            ROUND(AVG(ot.dias_reales)::numeric, 2)            AS dias_reales_avg,
            -- ── Ciclo de máquina (referencia técnica) ──────────────────────
            ROUND(cm.seg_ciclo::numeric, 3)                   AS seg_ciclo_maquina,
            ROUND(cm.cavidades::numeric, 1)                   AS cavidades_avg,
            ROUND(
                3600.0 / NULLIF(cm.seg_ciclo, 0)
            ::numeric, 0)                                      AS uph_maquina,
            -- Última producción
            MAX(ot.actual_end_date)::date::text               AS ultima_produccion
        FROM orden_tiempos ot
        JOIN product p ON p.id = ot.product_id
        LEFT JOIN machine m ON m.id = ot.machine_id
        LEFT JOIN ciclo_maquina cm ON cm.product_id = ot.product_id
        GROUP BY p.id, p.name, p.sku, p.color, m.name, m.type, cm.seg_ciclo, cm.cavidades
        HAVING COUNT(*) >= 1
        ORDER BY total_producido DESC
    """)))
    return [dict(r) for r in rows]


@router.get("/reportes/carga-maquinas")
def reporte_carga_maquinas(db: Session = Depends(get_prod_db)):
    """Por cada máquina: órdenes pendientes con días estimados.
    Usa tiempo real histórico (actual_end_date - actual_start_date) / quantity_produced
    por referencia. Fallback a promedio de máquina, luego a ciclo de producción_run.
    """
    from datetime import datetime

    # 1. Tiempo real promedio (seg/pieza) por producto
    tiempos = _rows(db.execute(text("""
        SELECT
            sop.product_id::text,
            ROUND(AVG(
                EXTRACT(EPOCH FROM (po.actual_end_date - po.actual_start_date))
                / NULLIF(po.quantity_produced, 0)
            )::numeric, 4) AS seg_por_pieza
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_start_date IS NOT NULL
          AND po.actual_end_date IS NOT NULL
          AND po.quantity_produced > 0
          AND po.actual_end_date > po.actual_start_date
        GROUP BY sop.product_id
    """)))
    tiempo_map: dict[str, float] = {
        str(r["product_id"]): float(r["seg_por_pieza"])
        for r in tiempos
        if r["seg_por_pieza"]
    }

    # 2. Promedio real por máquina (fallback cuando no hay historial por producto)
    vel_maq = _rows(db.execute(text("""
        SELECT
            po.machine_id::text,
            ROUND(AVG(
                EXTRACT(EPOCH FROM (po.actual_end_date - po.actual_start_date))
                / NULLIF(po.quantity_produced, 0)
            )::numeric, 4) AS seg_por_pieza
        FROM production_order po
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_start_date IS NOT NULL
          AND po.actual_end_date IS NOT NULL
          AND po.quantity_produced > 0
          AND po.actual_end_date > po.actual_start_date
          AND po.machine_id IS NOT NULL
        GROUP BY po.machine_id
    """)))
    vel_maq_map: dict[str, float] = {
        str(r["machine_id"]): float(r["seg_por_pieza"])
        for r in vel_maq
        if r["seg_por_pieza"]
    }

    # 3. Órdenes pendientes con detalle
    ordenes = _rows(db.execute(text("""
        SELECT
            po.id::text,
            po.order_number,
            po.status,
            po.priority,
            po.quantity_to_produce,
            po.quantity_produced,
            (po.quantity_to_produce - po.quantity_produced) AS pendiente,
            ROUND(
                CASE WHEN po.quantity_to_produce > 0
                THEN (po.quantity_produced::numeric / po.quantity_to_produce) * 100
                ELSE 0 END, 1
            ) AS avance_pct,
            po.machine_id::text,
            m.name AS machine_name,
            m.type AS machine_type,
            COALESCE(m."hoursPerDay", 8) AS hours_per_day,
            p.id::text AS product_id,
            p.name AS product_name,
            p.sku AS product_sku,
            so.delivery_date::text AS delivery_date,
            so.order_number AS sales_order_number,
            c."businessName" AS customer_name
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE po."isActive" = true
          AND po.status IN ('programada', 'en_proceso', 'pausada')
        ORDER BY
            po.priority ASC NULLS LAST,
            so.delivery_date NULLS LAST
    """)))

    # 4. Calcular días estimados por orden
    hoy = datetime.utcnow().date()
    resultado = []
    for o in ordenes:
        pid = str(o["product_id"])
        mid = str(o["machine_id"] or "")
        pendiente = max(int(o["pendiente"] or 0), 0)
        spd = tiempo_map.get(pid) or vel_maq_map.get(mid) or 10.0  # fallback 10s/pieza
        hours_per_day = float(o["hours_per_day"] or 8)

        horas_estimadas = (pendiente * spd) / 3600.0
        dias_estimados = horas_estimadas / hours_per_day if hours_per_day > 0 else 0

        delivery_date = None
        dias_margen = None
        if o["delivery_date"]:
            try:
                from datetime import date as date_type
                delivery_date = str(o["delivery_date"])[:10]
                dd = date_type.fromisoformat(delivery_date)
                dias_margen = (dd - hoy).days - round(dias_estimados)
            except Exception:
                pass

        resultado.append({
            **dict(o),
            "seg_por_pieza": round(spd, 3),
            "fuente_tiempo": "referencia" if pid in tiempo_map else ("maquina" if mid in vel_maq_map else "defecto"),
            "horas_estimadas": round(horas_estimadas, 1),
            "dias_estimados": round(dias_estimados, 1),
            "delivery_date": delivery_date,
            "dias_margen": dias_margen,
        })

    # 5. Agrupar por máquina
    maquinas: dict[str, dict] = {}
    for r in resultado:
        mid = str(r["machine_id"] or "sin_maquina")
        if mid not in maquinas:
            maquinas[mid] = {
                "machine_id": mid,
                "machine_name": r["machine_name"] or "Sin máquina",
                "machine_type": r["machine_type"],
                "hours_per_day": r["hours_per_day"],
                "ordenes": [],
                "total_horas": 0.0,
                "total_dias": 0.0,
            }
        maquinas[mid]["ordenes"].append(r)
        maquinas[mid]["total_horas"] = round(maquinas[mid]["total_horas"] + r["horas_estimadas"], 1)
        maquinas[mid]["total_dias"] = round(maquinas[mid]["total_horas"] / float(r["hours_per_day"] or 8), 1)

    return {
        "maquinas": list(maquinas.values()),
        "total_ordenes": len(resultado),
        "calculado_en": datetime.utcnow().isoformat()[:16],
    }


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD GERENCIAL — KPIs + gráficas con filtros
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/gerencial")
def dashboard_gerencial(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    area_id: Optional[int] = None,
    machine_id: Optional[str] = None,
    db: Session = Depends(get_prod_db),
):
    """Dashboard ejecutivo usando production_order.actual_end_date como fuente de verdad.
    production_run.start_time solo llega hasta abril 2026; production_order tiene datos actuales.
    """
    if not fecha_desde:
        fecha_desde = date.today() - timedelta(days=29)
    if not fecha_hasta:
        fecha_hasta = date.today()

    params: dict[str, Any] = {"desde": fecha_desde, "hasta": fecha_hasta}

    area_filter = ""
    maq_filter = ""
    if area_id:
        area_filter = """
            AND EXISTS (
                SELECT 1 FROM sales_order_product sop2
                JOIN product p2 ON p2.id = sop2.product_id
                JOIN mold md2 ON md2.id = p2."moldId"
                WHERE sop2.id = po.sales_order_product_id
                  AND md2."areaId" = :area_id
            )"""
        params["area_id"] = area_id
    if machine_id:
        maq_filter = "AND po.machine_id = :machine_id"
        params["machine_id"] = machine_id

    # ── KPIs globales: órdenes terminadas en el período ───────────────────────
    kpis = _row(db.execute(text(f"""
        SELECT
            COALESCE(SUM(po.quantity_produced), 0)  AS producidas,
            COALESCE(SUM(po.quantity_defective), 0) AS defectuosas,
            ROUND(
                CASE WHEN COALESCE(SUM(po.quantity_produced), 0) > 0
                THEN (1 - COALESCE(SUM(po.quantity_defective), 0)::numeric
                         / NULLIF(SUM(po.quantity_produced), 0)) * 100
                ELSE 0 END, 2
            ) AS calidad_pct,
            COUNT(po.id) AS ordenes_terminadas,
            COUNT(DISTINCT po.machine_id) AS maquinas_activas
        FROM production_order po
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter} {area_filter}
    """), params))

    # Órdenes por estado (snapshot actual, no filtrado por período)
    ordenes_estado = _rows(db.execute(text(f"""
        SELECT po.status, COUNT(*) AS total, COALESCE(SUM(po.quantity_produced), 0) AS unidades
        FROM production_order po
        WHERE po."isActive" = true
          {maq_filter} {area_filter}
        GROUP BY po.status
        ORDER BY total DESC
    """), params))

    # ── Tendencia diaria por actual_end_date ──────────────────────────────────
    tendencia = _rows(db.execute(text(f"""
        SELECT
            po.actual_end_date::date AS fecha,
            SUM(po.quantity_produced)  AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            COUNT(po.id) AS ordenes
        FROM production_order po
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter} {area_filter}
        GROUP BY po.actual_end_date::date
        ORDER BY fecha
    """), params))

    # ── Producción por máquina en el período ──────────────────────────────────
    oee = _rows(db.execute(text(f"""
        SELECT
            m.id AS machine_id,
            m.name AS maquina,
            m.type AS tipo,
            COUNT(po.id) AS ordenes_terminadas,
            SUM(po.quantity_produced)  AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            ROUND(
                CASE WHEN SUM(po.quantity_produced) > 0
                THEN (1 - SUM(po.quantity_defective)::numeric / NULLIF(SUM(po.quantity_produced), 0)) * 100
                ELSE 0 END::numeric, 2
            ) AS calidad_pct
        FROM production_order po
        JOIN machine m ON m.id = po.machine_id
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter} {area_filter}
        GROUP BY m.id, m.name, m.type
        ORDER BY producidas DESC
        LIMIT 12
    """), params))

    # ── Producción por área ────────────────────────────────────────────────────
    por_area = _rows(db.execute(text(f"""
        SELECT
            a.name AS area,
            SUM(po.quantity_produced)  AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            ROUND(
                CASE WHEN SUM(po.quantity_produced) > 0
                THEN (1 - SUM(po.quantity_defective)::numeric / NULLIF(SUM(po.quantity_produced), 0)) * 100
                ELSE 0 END, 2
            ) AS calidad_pct,
            COUNT(po.id) AS ordenes
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        JOIN mold md ON md.id = p."moldId"
        JOIN area a ON a.id = md."areaId"
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter}
        GROUP BY a.name
        ORDER BY producidas DESC
    """), params))

    # ── Top productos del período ──────────────────────────────────────────────
    top_prod = _rows(db.execute(text(f"""
        SELECT
            p.name AS producto, p.sku, p.color,
            SUM(po.quantity_produced)  AS producidas,
            SUM(po.quantity_defective) AS defectuosas,
            COUNT(po.id) AS ordenes
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        WHERE po."isActive" = true
          AND po.status = 'terminada'
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter} {area_filter}
        GROUP BY p.id, p.name, p.sku, p.color
        ORDER BY producidas DESC
        LIMIT 10
    """), params))

    # ── Cumplimiento de entregas ───────────────────────────────────────────────
    cumplimiento = _rows(db.execute(text(f"""
        SELECT
            CASE
                WHEN po.status = 'terminada'
                     AND (po.actual_end_date IS NULL OR po.actual_end_date::date <= so.delivery_date::date)
                THEN 'a_tiempo'
                WHEN po.status = 'terminada' THEN 'tardio'
                WHEN po.status = 'cancelada' THEN 'cancelada'
                ELSE 'pendiente'
            END AS estado_entrega,
            COUNT(*) AS total
        FROM production_order po
        LEFT JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        WHERE po."isActive" = true
          AND po.actual_end_date::date BETWEEN :desde AND :hasta
          {maq_filter} {area_filter}
        GROUP BY estado_entrega
    """), params))

    return {
        "periodo": {"desde": str(fecha_desde), "hasta": str(fecha_hasta)},
        "kpis": dict(kpis) if kpis else {},
        "ordenes_estado": [dict(r) for r in ordenes_estado],
        "paros_resumen": {"total_paros": 0, "paros_activos": 0, "minutos_paro": 0},
        "tendencia_diaria": [dict(r) for r in tendencia],
        "oee_maquinas": [dict(r) for r in oee],
        "paros_por_categoria": [],
        "produccion_por_area": [dict(r) for r in por_area],
        "top_productos": [dict(r) for r in top_prod],
        "cumplimiento_entregas": [dict(r) for r in cumplimiento],
    }


# ─────────────────────────────────────────────────────────────────────────────
# CATÁLOGOS (para filtros y selects del frontend)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/catalogos/areas")
def areas(db: Session = Depends(get_prod_db)):
    rows = _rows(db.execute(text('SELECT id, name FROM area WHERE "isActive" = true ORDER BY name')))
    return [dict(r) for r in rows]


@router.get("/catalogos/maquinas")
def maquinas_catalogo(db: Session = Depends(get_prod_db)):
    rows = _rows(db.execute(text('SELECT id, name, type, "currentStatus" FROM machine WHERE "isActive" = true ORDER BY type, name')))
    return [dict(r) for r in rows]


@router.get("/catalogos/turnos-categoria")
def turnos_categoria(db: Session = Depends(get_prod_db)):
    rows = _rows(db.execute(text('SELECT id, name, "startTime", "endTime" FROM shift_category WHERE "isActive" = true ORDER BY "startTime"')))
    return [dict(r) for r in rows]


@router.get("/catalogos/tipos-materia-prima")
def tipos_mp(db: Session = Depends(get_prod_db)):
    rows = _rows(db.execute(text('SELECT DISTINCT type FROM raw_material WHERE "isActive" = true ORDER BY type')))
    return [r["type"] for r in rows]


@router.get("/catalogos/rango-datos")
def rango_datos(db: Session = Depends(get_prod_db)):
    """Retorna rangos de fechas reales:
    - fecha_min/max: rango de production_run.start_time (para gráficas de tendencia)
    - ordenes_fecha_max/min: rango de production_order.updated_at (para el tab Órdenes)
    """
    corridas = _row(db.execute(text("""
        SELECT MIN(actual_end_date::date) AS fecha_min,
               MAX(actual_end_date::date) AS fecha_max,
               COUNT(*) AS total_corridas
        FROM production_order
        WHERE "isActive" = true AND actual_end_date IS NOT NULL AND status = 'terminada'
    """)))
    ordenes = _row(db.execute(text("""
        SELECT MAX(updated_at::date) AS ordenes_fecha_max,
               MIN(updated_at::date) AS ordenes_fecha_min
        FROM production_order WHERE "isActive" = true
    """)))
    return {
        "fecha_min": corridas["fecha_min"] if corridas else None,
        "fecha_max": corridas["fecha_max"] if corridas else None,
        "total_corridas": corridas["total_corridas"] if corridas else 0,
        "ordenes_fecha_max": ordenes["ordenes_fecha_max"] if ordenes else None,
        "ordenes_fecha_min": ordenes["ordenes_fecha_min"] if ordenes else None,
    }


_ARTICULOS_SQL = text("""
WITH ordenes_agg AS (
    SELECT
        sop.product_id,
        COUNT(DISTINCT po.id)         AS ordenes_terminadas,
        SUM(po.quantity_produced)     AS uds_totales,
        SUM(po.quantity_defective)    AS uds_defectuosas,
        MAX(po.actual_end_date)::date AS ultima_produccion
    FROM production_order po
    JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
    WHERE po.status = 'terminada' AND po."isActive" = true
    GROUP BY sop.product_id
),
runs_agg AS (
    SELECT
        sop.product_id,
        ROUND(AVG(
            CASE WHEN pr.real_cavities > 0 THEN pr.avg_cycle_time / pr.real_cavities END
        )::numeric, 2) AS seg_real_por_pieza,
        COUNT(DISTINCT pr.id) AS total_corridas
    FROM production_run pr
    JOIN production_order po ON po.id = pr.production_order_id
    JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
    WHERE po.status = 'terminada' AND po."isActive" = true
      AND pr.avg_cycle_time > 0
    GROUP BY sop.product_id
),
mat_agg AS (
    SELECT
        sop.product_id,
        ROUND((SUM(mri.quantity) FILTER (WHERE LOWER(rm.type) LIKE '%resina%')
               / NULLIF(SUM(po.quantity_produced), 0) * 1000)::numeric, 2) AS g_resina_por_pieza,
        ROUND((SUM(mri.quantity) FILTER (WHERE LOWER(rm.type) LIKE '%master%' OR LOWER(rm.type) LIKE '%color%')
               / NULLIF(SUM(po.quantity_produced), 0) * 1000)::numeric, 3) AS g_master_por_pieza
    FROM production_order po
    JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
    JOIN material_request mr     ON mr."productionOrderId" = po.id
    JOIN material_request_item mri ON mri."materialRequestId" = mr.id
    JOIN raw_material rm          ON rm.id = mri."rawMaterialId"
    WHERE po.status = 'terminada' AND po."isActive" = true
      AND mr.status = 'aprobada'
    GROUP BY sop.product_id
)
SELECT
    p.id,
    p.name                              AS product_name,
    p.sku,
    p.color,
    p.weight                            AS peso_nominal,
    p."theoreticalCycle"                AS ciclo_teorico,
    oa.ordenes_terminadas,
    oa.uds_totales,
    oa.uds_defectuosas,
    ROUND(100.0 * oa.uds_defectuosas / NULLIF(oa.uds_totales, 0), 2) AS tasa_defecto_pct,
    oa.ultima_produccion,
    ra.seg_real_por_pieza,
    ra.total_corridas,
    CASE WHEN ra.seg_real_por_pieza > 0 AND p."theoreticalCycle" IS NOT NULL
         THEN ROUND(100.0 * p."theoreticalCycle" / ra.seg_real_por_pieza, 1)
    END                                 AS eficiencia_ciclo_pct,
    ma.g_resina_por_pieza,
    ma.g_master_por_pieza,
    CASE WHEN p.weight > 0 AND ma.g_resina_por_pieza IS NOT NULL
         THEN ROUND(100.0 * (ma.g_resina_por_pieza - p.weight) / p.weight, 1)
    END                                 AS delta_material_pct
FROM product p
JOIN ordenes_agg oa ON oa.product_id = p.id
LEFT JOIN runs_agg ra ON ra.product_id = p.id
LEFT JOIN mat_agg  ma ON ma.product_id = p.id
ORDER BY oa.uds_totales DESC
LIMIT 500
""")


@router.get("/articulos")
def articulos(db: Session = Depends(get_prod_db)):
    rows = _rows(db.execute(_ARTICULOS_SQL))
    return [dict(r) for r in rows]


@router.post("/articulos/sync")
def articulos_sync(db: Session = Depends(get_prod_db)):
    """Extrae estadisticas de DATHA y las guarda en produccion_stats.db (SQLite local)."""
    import time
    from app.db_articulos import upsert_rows, last_sync
    t0 = time.time()
    rows = [dict(r) for r in _rows(db.execute(_ARTICULOS_SQL))]
    upsert_rows(rows, time.time() - t0)
    return {"ok": True, "filas": len(rows), "ultimo_sync": last_sync()}


@router.get("/articulos/sync/status")
def articulos_sync_status():
    from app.db_articulos import last_sync
    return last_sync() or {"mensaje": "Sin sincronizacion aun"}


@router.get("/articulos/export/csv")
def articulos_csv(db: Session = Depends(get_prod_db)):
    """Descarga CSV con todos los articulos y sus estadisticas."""
    import csv, io
    from fastapi.responses import StreamingResponse
    rows = [dict(r) for r in _rows(db.execute(_ARTICULOS_SQL))]
    cols = [
        "id", "product_name", "sku", "color",
        "peso_nominal", "ciclo_teorico",
        "ordenes_terminadas", "uds_totales", "uds_defectuosas", "tasa_defecto_pct",
        "ultima_produccion",
        "seg_real_por_pieza", "total_corridas", "eficiencia_ciclo_pct",
        "g_resina_por_pieza", "g_master_por_pieza", "delta_material_pct",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=articulos_stats.csv"},
    )


@router.get("/catalogos/categorias-paro")
def categorias_paro(db: Session = Depends(get_prod_db)):
    rows = _rows(db.execute(text('SELECT id, name, type, "isActive" FROM category_stop ORDER BY name')))
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTACIÓN PARA SYNC (IndexedDB del browser)
# Devuelve todos los registros sin paginación para guardar en el cliente
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/export/ordenes")
def export_ordenes(db: Session = Depends(get_prod_db)):
    """Todas las órdenes activas para sync en IndexedDB del browser."""
    rows = _rows(db.execute(text("""
        SELECT
            po.id::text, po.order_number, po.status, po.priority,
            po.quantity_to_produce, po.quantity_produced, po.quantity_defective,
            po.actual_start_date::text, po.actual_end_date::text,
            po.created_at::text, po.updated_at::text, po.notes, po.batch_code,
            p.id::text AS product_id, p.name AS product_name, p.sku AS product_sku,
            m.id::text AS machine_id, m.name AS machine_name,
            a.name AS area_name,
            so.order_number AS sales_order_number,
            c."businessName" AS customer_name,
            ROUND(
                CASE WHEN po.quantity_to_produce > 0
                THEN (po.quantity_produced::numeric / po.quantity_to_produce) * 100
                ELSE 0 END, 1
            ) AS avance_pct
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN mold md ON md.id = p."moldId"
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE po."isActive" = true
        ORDER BY po.updated_at DESC
    """)))
    return [dict(r) for r in rows]


@router.get("/proyeccion-entregas")
def proyeccion_entregas(db: Session = Depends(get_prod_db)):
    """
    Proyección de entregas usando teoría de colas (M/D/1 simplificada).

    Por cada máquina activa:
      - Velocidad = unidades/hora promedio de corridas históricas (últimos 90 días)
      - Cola de órdenes = pendientes asignadas a esa máquina, ordenadas por prioridad y delivery_date
      - Tiempo de servicio Ts = piezas_restantes / velocidad
      - Factor de disponibilidad = 1 - (tasa de paro histórica)
      - Fecha estimada = NOW + sum(Ts_anteriores_en_cola) + Ts_propia / disponibilidad
    """
    # 1. Velocidad histórica por máquina (últimas 90 días, excluyendo runs con paro)
    velocidades = _rows(db.execute(text("""
        SELECT
            po.machine_id::text,
            m.name AS machine_name,
            COUNT(pr.id) AS total_runs,
            ROUND(AVG(
                CASE
                    WHEN EXTRACT(EPOCH FROM (pr.end_time - pr.start_time)) > 0
                    THEN po.quantity_produced /
                         (EXTRACT(EPOCH FROM (pr.end_time - pr.start_time)) / 3600.0)
                    ELSE NULL
                END
            ), 1) AS unidades_por_hora,
            -- Disponibilidad: horas trabajadas vs horas de paro
            ROUND(
                1.0 - COALESCE(
                    SUM(
                        COALESCE(
                            EXTRACT(EPOCH FROM (msr_agg.total_paro)) / 3600.0, 0
                        )
                    ) / NULLIF(
                        SUM(EXTRACT(EPOCH FROM (pr.end_time - pr.start_time)) / 3600.0), 0
                    ), 0
                ), 4
            ) AS disponibilidad
        FROM production_run pr
        JOIN production_order po ON po.id = pr.production_order_id
        JOIN machine m ON m.id = po.machine_id
        LEFT JOIN (
            SELECT
                msr.production_run_id,
                SUM(msr.end_time - msr.start_time) AS total_paro
            FROM machine_stop_records msr
            WHERE msr.end_time IS NOT NULL
            GROUP BY msr.production_run_id
        ) msr_agg ON msr_agg.production_run_id = pr.id
        WHERE pr.start_time >= NOW() - INTERVAL '90 days'
          AND pr.end_time IS NOT NULL
          AND po.quantity_produced > 0
          AND m."isActive" = true
        GROUP BY po.machine_id, m.name
        HAVING COUNT(pr.id) >= 3
    """)))

    vel_map = {}
    for v in velocidades:
        vel_map[str(v["machine_id"])] = {
            "machine_name": v["machine_name"],
            "uph": float(v["unidades_por_hora"] or 50),
            "disponibilidad": float(v["disponibilidad"] or 0.85),
        }

    # 2. Órdenes activas pendientes de entrega
    ordenes = _rows(db.execute(text("""
        SELECT
            po.id::text,
            po.order_number,
            po.status,
            po.priority,
            po.quantity_to_produce,
            po.quantity_produced,
            po.quantity_defective,
            (po.quantity_to_produce - po.quantity_produced) AS pendiente,
            po.actual_start_date::text,
            po.machine_id::text,
            m.name AS machine_name,
            p.name AS product_name,
            p.sku AS product_sku,
            so.order_number AS sales_order_number,
            so.delivery_date::text AS delivery_date,
            c."businessName" AS customer_name,
            c.id::text AS customer_id,
            ROUND(
                CASE WHEN po.quantity_to_produce > 0
                THEN (po.quantity_produced::numeric / po.quantity_to_produce) * 100
                ELSE 0 END, 1
            ) AS avance_pct
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE po."isActive" = true
          AND po.status IN ('programada', 'en_proceso', 'pausada')
        ORDER BY
            po.priority ASC NULLS LAST,
            so.delivery_date NULLS LAST,
            po.created_at
    """)))

    # 3. Simulación de cola por máquina
    from datetime import datetime, timedelta
    import math

    ahora = datetime.utcnow()

    # reloj por máquina: cuándo quedará libre
    machine_clock: dict[str, datetime] = {}

    resultados = []
    for o in ordenes:
        mid = str(o["machine_id"] or "sin_maquina")
        pendiente = max(float(o["pendiente"] or o["quantity_to_produce"] or 1), 1)

        vel_info = vel_map.get(mid, {"uph": 50.0, "disponibilidad": 0.85, "machine_name": o["machine_name"] or "?"})
        uph = max(vel_info["uph"], 1.0)
        disp = max(min(vel_info["disponibilidad"], 1.0), 0.5)

        # Ts ajustado por disponibilidad (tiempo de servicio real en horas)
        ts_horas = (pendiente / uph) / disp

        # Inicio de procesamiento = max(ahora, cuando termine la anterior en esta máquina)
        inicio = machine_clock.get(mid, ahora)
        fin_estimado = inicio + timedelta(hours=ts_horas)
        machine_clock[mid] = fin_estimado

        delivery_date = None
        dias_margen = None
        semaforo = "gris"
        if o["delivery_date"]:
            try:
                delivery_date = datetime.strptime(str(o["delivery_date"])[:10], "%Y-%m-%d")
                dias_margen = (delivery_date - fin_estimado).days
                if dias_margen >= 3:
                    semaforo = "verde"
                elif dias_margen >= 0:
                    semaforo = "amarillo"
                else:
                    semaforo = "rojo"
            except Exception:
                pass

        resultados.append({
            **dict(o),
            "uph_maquina": round(uph, 1),
            "disponibilidad_maquina": round(disp * 100, 1),
            "ts_horas": round(ts_horas, 2),
            "inicio_estimado": inicio.isoformat()[:16],
            "fin_estimado": fin_estimado.isoformat()[:16],
            "delivery_date": o["delivery_date"],
            "dias_margen": dias_margen,
            "semaforo": semaforo,
        })

    # 4. Resumen por cliente
    clientes: dict[str, dict] = {}
    for r in resultados:
        cid = r["customer_id"] or "sin_cliente"
        cname = r["customer_name"] or "Sin cliente"
        if cid not in clientes:
            clientes[cid] = {
                "customer_id": cid,
                "customer_name": cname,
                "ordenes": 0,
                "en_riesgo": 0,
                "en_advertencia": 0,
                "a_tiempo": 0,
                "min_margen": None,
            }
        clientes[cid]["ordenes"] += 1
        if r["semaforo"] == "rojo":
            clientes[cid]["en_riesgo"] += 1
        elif r["semaforo"] == "amarillo":
            clientes[cid]["en_advertencia"] += 1
        elif r["semaforo"] == "verde":
            clientes[cid]["a_tiempo"] += 1
        if r["dias_margen"] is not None:
            if clientes[cid]["min_margen"] is None or r["dias_margen"] < clientes[cid]["min_margen"]:
                clientes[cid]["min_margen"] = r["dias_margen"]

    return {
        "calculado_en": ahora.isoformat()[:16],
        "ordenes": resultados,
        "resumen_clientes": list(clientes.values()),
        "meta": {
            "maquinas_con_velocidad": len(vel_map),
            "ordenes_en_cola": len(resultados),
        }
    }


@router.get("/export/paros")
def export_paros(db: Session = Depends(get_prod_db)):
    """Todos los paros (últimos 90 días) para sync en IndexedDB del browser."""
    rows = _rows(db.execute(text("""
        SELECT
            msr.id::text,
            msr.production_run_id::text,
            m.id::text AS machine_id,
            m.name AS machine_name,
            a.name AS area_name,
            cs.name AS categoria_nombre,
            cs.type AS categoria_tipo,
            msr.start_time::text,
            msr.end_time::text,
            msr.description,
            msr.solution,
            CASE
                WHEN msr.end_time IS NOT NULL
                THEN ROUND(EXTRACT(EPOCH FROM (msr.end_time - msr.start_time))/60::numeric, 1)
                ELSE NULL
            END AS minutos_paro
        FROM machine_stop_records msr
        LEFT JOIN production_run pr ON pr.id = msr.production_run_id
        LEFT JOIN production_order po ON po.id = pr.production_order_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN mold md ON md.id = (
            SELECT "moldId" FROM product WHERE id = (
                SELECT product_id FROM sales_order_product WHERE id = po.sales_order_product_id
            )
        )
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN category_stop cs ON cs.name = msr.category
        WHERE msr.start_time >= NOW() - INTERVAL '90 days'
        ORDER BY msr.start_time DESC
    """)))
    return [dict(r) for r in rows]
