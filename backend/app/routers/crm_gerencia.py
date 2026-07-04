"""CRM Gerencia — panel consolidado para gerente y admin.

Permite ver métricas de todos los asesores, clientes DATHA y órdenes de producción.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc, text
from typing import Optional, Any
from datetime import datetime, date, time, timedelta
from calendar import monthrange
import decimal
from uuid import UUID

from app.database import get_db
from app.database_produccion import get_prod_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.crm_cliente import CRMCliente
from app.models.visita import Visita
from app.models.tarea import Tarea
from app.models.calendario_evento import CalendarioEvento

router = APIRouter(prefix="/api/crm/gerencia", tags=["CRM - Gerencia"])

_ROLES = ("admin", "gerente")
_ALL_CRM = ("admin", "gerente", "asesor")

ETAPAS = ["prospecto", "contactado", "visita_agendada", "propuesta", "negociacion", "cumplido"]

ESTADOS_PRODUCCION = [
    "pendiente", "en_proceso", "programada", "pausada", "terminada", "cancelada"
]

# ── Serialización DATHA ───────────────────────────────────────────────────────

def _s(v: Any) -> Any:
    if isinstance(v, decimal.Decimal): return float(v)
    if isinstance(v, (datetime, date)): return v.isoformat()
    if isinstance(v, time): return v.strftime("%H:%M:%S")
    if isinstance(v, UUID): return str(v)
    if isinstance(v, timedelta): return v.total_seconds()
    return v

def _rows(result) -> list[dict]:
    keys = list(result.keys())
    return [{k: _s(v) for k, v in zip(keys, row)} for row in result.fetchall()]

def _row(result) -> dict | None:
    keys = list(result.keys())
    row = result.fetchone()
    return {k: _s(v) for k, v in zip(keys, row)} if row else None


# ── Helpers métricas asesor ───────────────────────────────────────────────────

def _metricas_asesor(db: Session, asesor_id: int, hoy: date) -> dict:
    inicio_mes = hoy.replace(day=1)
    days_in_month = monthrange(hoy.year, hoy.month)[1]
    fin_mes = inicio_mes.replace(day=days_in_month)

    clientes = db.query(sqlfunc.count(CRMCliente.id)).filter(
        CRMCliente.asesor_id == asesor_id, CRMCliente.activo == True
    ).scalar() or 0

    visitas_mes = db.query(sqlfunc.count(Visita.id)).filter(
        Visita.asesor_id == asesor_id,
        Visita.fecha_visita >= inicio_mes,
        Visita.fecha_visita <= fin_mes,
    ).scalar() or 0

    tareas_rows = (
        db.query(Tarea.etapa, sqlfunc.count(Tarea.id))
        .filter(Tarea.asesor_id == asesor_id)
        .group_by(Tarea.etapa)
        .all()
    )
    tareas_por_etapa = {e: 0 for e in ETAPAS}
    for etapa, count in tareas_rows:
        if etapa in tareas_por_etapa:
            tareas_por_etapa[etapa] = count

    tareas_ejecutadas = db.query(sqlfunc.count(Tarea.id)).filter(
        Tarea.asesor_id == asesor_id, Tarea.ejecutado == True
    ).scalar() or 0

    proxima = (
        db.query(CalendarioEvento.fecha_inicio)
        .filter(
            CalendarioEvento.asesor_id == asesor_id,
            CalendarioEvento.tipo == "visita",
            CalendarioEvento.completado == False,
            CalendarioEvento.fecha_inicio >= datetime.now(),
        )
        .order_by(CalendarioEvento.fecha_inicio)
        .first()
    )

    return {
        "clientes_activos": clientes,
        "visitas_mes": visitas_mes,
        "tareas_por_etapa": tareas_por_etapa,
        "tareas_ejecutadas": tareas_ejecutadas,
        "proxima_visita": proxima[0].isoformat() if proxima else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/resumen")
def resumen_gerencia(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Dashboard: métricas de todos los asesores + totales consolidados."""
    hoy = date.today()

    asesores = db.query(User).filter(
        User.rol == "asesor", User.activo == True
    ).order_by(User.nombre).all()

    resultado = []
    totales = {
        "clientes_activos": 0,
        "visitas_mes": 0,
        "tareas_ejecutadas": 0,
        "tareas_por_etapa": {e: 0 for e in ETAPAS},
    }

    for a in asesores:
        m = _metricas_asesor(db, a.id, hoy)
        resultado.append({"id": a.id, "nombre": a.nombre, "username": a.username, **m})
        totales["clientes_activos"]  += m["clientes_activos"]
        totales["visitas_mes"]       += m["visitas_mes"]
        totales["tareas_ejecutadas"] += m["tareas_ejecutadas"]
        for e in ETAPAS:
            totales["tareas_por_etapa"][e] += m["tareas_por_etapa"][e]

    return {"asesores": resultado, "totales": totales}


@router.get("/asesores")
def listar_asesores(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Lista todos los usuarios con rol asesor."""
    asesores = db.query(User).filter(
        User.rol == "asesor", User.activo == True
    ).order_by(User.nombre).all()
    return [{"id": a.id, "nombre": a.nombre, "username": a.username} for a in asesores]


@router.get("/clientes-datha")
def clientes_datha(
    q: Optional[str] = None,
    asesor_id: Optional[int] = None,
    sin_asignar: bool = False,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """
    Todos los clientes de DATHA con su asesor asignado (si lo tiene en crm_clientes).
    Permite filtrar por nombre, asesor, o sin asignar.
    """
    # Traer todos los crm_clientes para hacer el join en memoria
    crm_map: dict[str, dict] = {}
    crm_q = db.query(CRMCliente).filter(CRMCliente.activo == True)
    if asesor_id:
        crm_q = crm_q.filter(CRMCliente.asesor_id == asesor_id)
    for c in crm_q.all():
        nombre_key = (c.nombre or "").strip().lower()
        asesor_info = None
        if c.asesor:
            asesor_info = {"id": c.asesor_id, "nombre": c.asesor.nombre}
        crm_map[nombre_key] = {
            "crm_id": c.id,
            "asesor": asesor_info,
            "nit_crm": c.nit,
        }

    # Consultar clientes de DATHA
    where_parts = ['c."isActive" = true']
    params: dict = {"limit": per_page, "offset": (page - 1) * per_page}

    if q:
        where_parts.append('(c."businessName" ILIKE :q OR c.nit ILIKE :q)')
        params["q"] = f"%{q}%"

    where = " AND ".join(where_parts)

    sql = text(f"""
        SELECT
            c.id,
            c."businessName"    AS nombre,
            c.nit               AS nit,
            c.city              AS ciudad,
            c.phone             AS telefono,
            c.email             AS email,
            c.created_at        AS created_at
        FROM customer c
        WHERE {where}
        ORDER BY c."businessName"
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"""
        SELECT COUNT(*) FROM customer c WHERE {where}
    """)
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    rows = _rows(prod_db.execute(sql, params))
    total = prod_db.execute(count_sql, count_params).scalar() or 0

    # Enriquecer con datos CRM
    resultado = []
    for r in rows:
        key = (r.get("nombre") or "").strip().lower()
        crm = crm_map.get(key, {})
        tiene_asesor = crm.get("asesor") is not None

        # Filtro sin_asignar
        if sin_asignar and tiene_asesor:
            continue
        # Filtro asesor_id (si se aplica y no está en crm_map, descartar)
        if asesor_id and not tiene_asesor:
            continue

        resultado.append({
            **r,
            "crm_id":   crm.get("crm_id"),
            "asesor":   crm.get("asesor"),
            "nit_crm":  crm.get("nit_crm"),
        })

    return {"items": resultado, "total": total, "page": page, "per_page": per_page}


@router.post("/cliente-datha/asignar")
def asignar_asesor_a_cliente(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """
    Asigna (o reasigna) un asesor a un cliente de DATHA.
    Crea o actualiza el registro en crm_clientes.
    payload: { datha_customer_id, nombre, nit, ciudad, telefono, email, asesor_id }
    """
    nombre   = payload.get("nombre", "").strip()
    asesor_id = payload.get("asesor_id")
    datha_customer_id = payload.get("datha_customer_id")
    if not nombre:
        raise HTTPException(400, "nombre requerido")

    # Verificar asesor
    if asesor_id:
        asesor = db.query(User).filter(User.id == asesor_id, User.rol.in_(["asesor", "admin", "gerente"])).first()
        if not asesor:
            raise HTTPException(404, "Asesor no encontrado")

    # Buscar si ya existe por datha_customer_id (más preciso) o por nombre
    existente = None
    if datha_customer_id:
        existente = db.query(CRMCliente).filter(
            CRMCliente.datha_customer_id == datha_customer_id, CRMCliente.activo == True
        ).first()
    if not existente:
        existente = db.query(CRMCliente).filter(
            CRMCliente.nombre.ilike(nombre), CRMCliente.activo == True
        ).first()

    if existente:
        existente.asesor_id = asesor_id
        if datha_customer_id: existente.datha_customer_id = datha_customer_id
        if payload.get("nit"):    existente.nit    = payload["nit"]
        if payload.get("ciudad"): existente.ciudad = payload["ciudad"]
        if payload.get("telefono"): existente.telefono = payload["telefono"]
        if payload.get("email"):  existente.email  = payload["email"]
        db.commit()
        db.refresh(existente)
        crm = existente
    else:
        crm = CRMCliente(
            nombre=nombre,
            nit=payload.get("nit"),
            ciudad=payload.get("ciudad"),
            telefono=payload.get("telefono"),
            email=payload.get("email"),
            asesor_id=asesor_id,
            datha_customer_id=datha_customer_id,
        )
        db.add(crm)
        db.commit()
        db.refresh(crm)

    asesor_out = None
    if crm.asesor_id:
        a = db.query(User).filter(User.id == crm.asesor_id).first()
        if a:
            asesor_out = {"id": a.id, "nombre": a.nombre}

    from app.services.vendedor_sync import propagar_vendedor_por_nit
    propagar_vendedor_por_nit(db, crm.nit, asesor_out["nombre"] if asesor_out else None)

    return {"crm_id": crm.id, "nombre": crm.nombre, "asesor": asesor_out}


@router.get("/ordenes-resumen")
def ordenes_resumen(
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Resumen de órdenes de producción agrupadas por status.

    Incluye "pendiente": productos vendidos (sales_order_product) que aún
    no tienen production_order creada, es decir, aún no han entrado a producción.
    """
    sql = text("""
        SELECT
            po.status,
            COUNT(*)                        AS total,
            SUM(po.quantity_to_produce)     AS unidades_total,
            SUM(po.quantity_produced)       AS unidades_producidas,
            SUM(po.quantity_defective)      AS unidades_defectuosas,
            ROUND(
                CASE WHEN SUM(po.quantity_to_produce) > 0
                THEN (SUM(po.quantity_produced)::numeric / SUM(po.quantity_to_produce)) * 100
                ELSE 0 END, 1
            ) AS avance_pct
        FROM production_order po
        WHERE po."isActive" = true
        GROUP BY po.status
        ORDER BY
            CASE po.status
                WHEN 'en_proceso'  THEN 1
                WHEN 'programada'  THEN 2
                WHEN 'pausada'     THEN 3
                WHEN 'terminada'   THEN 4
                ELSE 5
            END
    """)
    rows = _rows(prod_db.execute(sql))

    pendiente_sql = text("""
        SELECT
            COUNT(*)             AS total,
            SUM(sop.quantity)    AS unidades_total
        FROM sales_order_product sop
        WHERE sop.status = 'pendiente'
    """)
    pendiente_row = _row(prod_db.execute(pendiente_sql)) or {}
    rows.insert(0, {
        "status": "pendiente",
        "total": pendiente_row.get("total") or 0,
        "unidades_total": pendiente_row.get("unidades_total") or 0,
        "unidades_producidas": 0,
        "unidades_defectuosas": 0,
        "avance_pct": 0,
    })

    # Resumen de clientes activos con órdenes
    clientes_sql = text("""
        SELECT COUNT(DISTINCT c.id) AS total_clientes
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN sales_order so ON so.id = sop.sales_order_id
        JOIN customer c ON c.id = so.customer_id
        WHERE po."isActive" = true AND po.status NOT IN ('terminada','cancelada')
    """)
    total_clientes = prod_db.execute(clientes_sql).scalar() or 0

    return {
        "por_status": rows,
        "total_clientes_activos": total_clientes,
    }


def _ordenes_pendientes(prod_db: Session, q: Optional[str], page: int, per_page: int) -> dict:
    """Productos vendidos sin production_order (aún no entran a producción)."""
    filters = ["sop.status = 'pendiente'"]
    params: dict = {"limit": per_page, "offset": (page - 1) * per_page}

    if q:
        filters.append('(COALESCE(c."businessName", \'\') ILIKE :q OR COALESCE(p.name, \'\') ILIKE :q OR COALESCE(so.order_number, \'\') ILIKE :q)')
        params["q"] = f"%{q}%"

    where = " AND ".join(filters)

    sql = text(f"""
        SELECT
            sop.id,
            so.order_number       AS order_number,
            'pendiente'            AS status,
            NULL::text             AS priority,
            sop.quantity           AS quantity_to_produce,
            0                      AS quantity_produced,
            0                      AS quantity_defective,
            NULL::timestamptz      AS actual_start_date,
            NULL::timestamptz      AS actual_end_date,
            so.created_at          AS created_at,
            sop.observations        AS notes,
            p.name                 AS product_name,
            p.sku                  AS product_sku,
            p.color                AS product_color,
            NULL::text             AS machine_name,
            NULL::text             AS area_name,
            so.order_number        AS sales_order_number,
            COALESCE(sop.delivery_date, so.delivery_date) AS delivery_date,
            c."businessName"       AS customer_name,
            0                      AS avance_pct
        FROM sales_order_product sop
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE {where}
        ORDER BY so.created_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM sales_order_product sop
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE {where}
    """)
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    items = _rows(prod_db.execute(sql, params))
    total = prod_db.execute(count_sql, count_params).scalar() or 0
    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/ordenes")
def ordenes_produccion(
    estado: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 40,
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Lista órdenes de producción de DATHA con filtros por status y cliente.

    estado="pendiente" es un caso especial: no existe en production_order,
    viene de sales_order_product.status = 'pendiente' (productos vendidos
    que aún no han entrado a producción).
    """
    if estado == "pendiente":
        return _ordenes_pendientes(prod_db, q, page, per_page)

    filters = ['po."isActive" = true']
    params: dict = {"limit": per_page, "offset": (page - 1) * per_page}

    if estado:
        filters.append("po.status = :estado")
        params["estado"] = estado

    if q:
        filters.append('(COALESCE(c."businessName", \'\') ILIKE :q OR COALESCE(p.name, \'\') ILIKE :q OR COALESCE(po.order_number, \'\') ILIKE :q)')
        params["q"] = f"%{q}%"

    where = " AND ".join(filters)

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
            p.name       AS product_name,
            p.sku        AS product_sku,
            p.color      AS product_color,
            m.name       AS machine_name,
            a.name       AS area_name,
            so.order_number AS sales_order_number,
            so.delivery_date AS delivery_date,
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
        WHERE {where}
        ORDER BY
            CASE po.status
                WHEN 'en_proceso' THEN 1
                WHEN 'programada' THEN 2
                WHEN 'pausada'    THEN 3
                WHEN 'terminada'  THEN 4
                ELSE 5
            END,
            po.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"""
        SELECT COUNT(*) FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE {where}
    """)
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    items = _rows(prod_db.execute(sql, params))
    total = prod_db.execute(count_sql, count_params).scalar() or 0

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/asesor/{asesor_id}/kanban")
def kanban_asesor(
    asesor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    asesor = db.query(User).filter(User.id == asesor_id, User.rol == "asesor").first()
    if not asesor:
        raise HTTPException(404, "Asesor no encontrado")

    import json
    tareas = db.query(Tarea).filter(Tarea.asesor_id == asesor_id).order_by(Tarea.created_at.desc()).all()

    def enrich(t: Tarea) -> dict:
        d = {col.name: getattr(t, col.name) for col in t.__table__.columns}
        if d["actividades"]:
            try:    d["actividades"] = json.loads(d["actividades"])
            except: d["actividades"] = [d["actividades"]]
        else:
            d["actividades"] = []
        d["cliente_nombre"] = t.cliente.nombre if t.cliente else None
        return d

    enriched = [enrich(t) for t in tareas]
    grouped = {etapa: [] for etapa in ETAPAS}
    for t in enriched:
        key = t["etapa"] if t["etapa"] in grouped else "prospecto"
        grouped[key].append(t)

    return {"asesor": {"id": asesor.id, "nombre": asesor.nombre}, "kanban": grouped}


@router.get("/asesor/{asesor_id}/clientes")
def clientes_asesor(
    asesor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    asesor = db.query(User).filter(User.id == asesor_id, User.rol == "asesor").first()
    if not asesor:
        raise HTTPException(404, "Asesor no encontrado")

    clientes = db.query(CRMCliente).filter(
        CRMCliente.asesor_id == asesor_id, CRMCliente.activo == True
    ).order_by(CRMCliente.nombre).all()

    resultado = []
    for c in clientes:
        ultima = (
            db.query(Visita.fecha_visita)
            .filter(Visita.cliente_id == c.id)
            .order_by(Visita.fecha_visita.desc())
            .first()
        )
        resultado.append({
            "id": c.id,
            "nombre": c.nombre,
            "nit": c.nit,
            "ciudad": c.ciudad,
            "telefono": c.telefono,
            "ultima_visita": ultima[0].isoformat() if ultima else None,
        })

    return {"asesor": {"id": asesor.id, "nombre": asesor.nombre}, "clientes": resultado}


# ══════════════════════════════════════════════════════════════════════════════
# Gestión de usuarios asesor (solo gerente/admin)
# ══════════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel
from app.auth.security import hash_password


class AsesorCreate(BaseModel):
    nombre: str
    username: str
    password: str


class AsesorUpdate(BaseModel):
    nombre: str | None = None
    username: str | None = None
    password: str | None = None


@router.get("/usuarios")
def listar_usuarios_asesor(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    users = (
        db.query(User)
        .filter(User.rol == "asesor")
        .order_by(User.nombre)
        .all()
    )
    return [
        {
            "id": u.id,
            "nombre": u.nombre,
            "username": u.username,
            "rol": u.rol,
            "activo": u.activo,
        }
        for u in users
    ]


@router.post("/usuarios", status_code=201)
def crear_usuario_asesor(
    data: AsesorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(400, "Nombre de usuario ya existe")
    u = User(
        nombre=data.nombre,
        username=data.username,
        password_hash=hash_password(data.password),
        rol="asesor",
        activo=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "nombre": u.nombre, "username": u.username, "rol": u.rol, "activo": u.activo}


@router.put("/usuarios/{user_id}")
def actualizar_usuario_asesor(
    user_id: int,
    data: AsesorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    u = db.query(User).filter(User.id == user_id, User.rol == "asesor").first()
    if not u:
        raise HTTPException(404, "Asesor no encontrado")
    if data.nombre is not None:
        u.nombre = data.nombre
    if data.username is not None:
        existing = db.query(User).filter(User.username == data.username, User.id != user_id).first()
        if existing:
            raise HTTPException(400, "Nombre de usuario ya existe")
        u.username = data.username
    if data.password is not None and data.password.strip():
        u.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "nombre": u.nombre, "username": u.username, "rol": u.rol, "activo": u.activo}


@router.patch("/usuarios/{user_id}/toggle")
def toggle_usuario_asesor(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    u = db.query(User).filter(User.id == user_id, User.rol == "asesor").first()
    if not u:
        raise HTTPException(404, "Asesor no encontrado")
    u.activo = not u.activo
    db.commit()
    return {"id": u.id, "activo": u.activo}
