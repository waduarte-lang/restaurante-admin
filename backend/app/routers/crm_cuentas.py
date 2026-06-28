"""CRM - Cuentas: facturas (sales_orders) y pagos de DATHA por cliente CRM."""
from __future__ import annotations

import decimal
from datetime import date, datetime, time, timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.database_produccion import get_prod_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.crm_cliente import CRMCliente

router = APIRouter(prefix="/api/crm/cuentas", tags=["CRM - Cuentas"])

_ROLES = ("admin", "asesor", "gerente")


def _serialize(v: Any) -> Any:
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


def _check_access(db: Session, current_user: User, cliente_id: int) -> CRMCliente:
    c = db.query(CRMCliente).filter(CRMCliente.id == cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    if current_user.rol == "asesor" and c.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    return c


@router.get("/cliente/{cliente_id}/facturas")
def facturas_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    cliente = _check_access(db, current_user, cliente_id)

    if cliente.datha_customer_id:
        where = 'so.customer_id = :cid AND so."isActive" = true'
        params = {"cid": cliente.datha_customer_id}
    else:
        where = 'c."businessName" ILIKE :nombre AND so."isActive" = true'
        params = {"nombre": cliente.nombre}

    sql = text(f"""
        SELECT
            so.id,
            so.order_number AS numero,
            so.created_at   AS fecha,
            so.delivery_date AS fecha_entrega,
            so.status,
            so.comments AS notes,
            c."businessName" AS customer_name,
            COALESCE(so.total, 0) AS total
        FROM sales_order so
        JOIN customer c ON c.id = so.customer_id
        WHERE {where}
        ORDER BY so.created_at DESC
        LIMIT 100
    """)
    rows = _rows(prod_db.execute(sql, params))
    return rows


@router.get("/cliente/{cliente_id}/pagos")
def pagos_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    cliente = _check_access(db, current_user, cliente_id)

    # Intentar leer tabla de pagos si existe en DATHA
    try:
        sql = text("""
            SELECT
                pay.id,
                pay.payment_date AS fecha,
                pay.amount       AS monto,
                pay.method       AS metodo,
                pay.reference    AS referencia,
                pay.notes        AS notas,
                so.order_number  AS factura_numero,
                c."businessName" AS customer_name
            FROM payment pay
            JOIN sales_order so ON so.id = pay.sales_order_id
            JOIN customer c ON c.id = so.customer_id
            WHERE c."businessName" = :nombre
            ORDER BY pay.payment_date DESC
            LIMIT 100
        """)
        rows = _rows(prod_db.execute(sql, {"nombre": cliente.nombre}))
        return rows
    except Exception:
        # Si la tabla payment no existe en DATHA, devuelve lista vacía
        return []


@router.get("/cliente/{cliente_id}/cartera")
def cartera_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Órdenes en cartera (cuentas por cobrar) del cliente en DATHA."""
    cliente = _check_access(db, current_user, cliente_id)

    if cliente.datha_customer_id:
        where = "so.customer_id = :cid AND so.status = 'ordenes_cartera' AND so.\"isActive\" = true"
        params: dict[str, Any] = {"cid": cliente.datha_customer_id}
    elif cliente.nit:
        where = "c.nit = :nit AND so.status = 'ordenes_cartera' AND so.\"isActive\" = true"
        params = {"nit": cliente.nit}
    else:
        where = "c.\"businessName\" ILIKE :nombre AND so.status = 'ordenes_cartera' AND so.\"isActive\" = true"
        params = {"nombre": cliente.nombre}

    sql = text(f"""
        SELECT
            so.id,
            so.order_number AS numero,
            so.created_at   AS fecha,
            so.delivery_date AS fecha_vencimiento,
            COALESCE(so.total, 0) AS total,
            so.comments AS notas,
            c."businessName" AS customer_name
        FROM sales_order so
        JOIN customer c ON c.id = so.customer_id
        WHERE {where}
        ORDER BY so.delivery_date ASC
    """)
    return _rows(prod_db.execute(sql, params))


@router.get("/cliente/{cliente_id}/resumen")
def resumen_cuenta(
    cliente_id: int,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Resumen rápido: total pedidos activos, última factura, próxima entrega."""
    cliente = _check_access(db, current_user, cliente_id)

    if cliente.datha_customer_id:
        where = 'so.customer_id = :cid AND po."isActive" = true AND po.status NOT IN (\'terminada\', \'cancelada\')'
        params = {"cid": cliente.datha_customer_id}
    else:
        where = 'c."businessName" ILIKE :nombre AND po."isActive" = true AND po.status NOT IN (\'terminada\', \'cancelada\')'
        params = {"nombre": cliente.nombre}

    sql = text(f"""
        SELECT
            COUNT(po.id) AS pedidos_activos,
            MAX(so.created_at) AS ultima_factura,
            MIN(so.delivery_date) AS proxima_entrega
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN sales_order so ON so.id = sop.sales_order_id
        JOIN customer c ON c.id = so.customer_id
        WHERE {where}
    """)
    row = prod_db.execute(sql, params).fetchone()
    return {
        "pedidos_activos": row[0] if row else 0,
        "ultima_factura": _serialize(row[1]) if row else None,
        "proxima_entrega": _serialize(row[2]) if row else None,
    }
