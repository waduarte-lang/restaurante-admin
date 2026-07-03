"""CRM - Pedidos: lee órdenes de producción de DATHA filtradas por cliente CRM."""
from __future__ import annotations

import decimal
import io
from datetime import date, datetime, time, timedelta
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.database_produccion import get_prod_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.crm_cliente import CRMCliente

router = APIRouter(prefix="/api/crm/pedidos", tags=["CRM - Pedidos"])

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


def _row(result) -> dict | None:
    keys = list(result.keys())
    row = result.fetchone()
    return {k: _serialize(v) for k, v in zip(keys, row)} if row else None


def _get_customer_filter(db: Session, current_user: User, cliente_id: Optional[int]):
    """Devuelve (datha_ids, names) para filtrar production_order en DATHA."""
    query = db.query(CRMCliente).filter(CRMCliente.activo == True)
    if current_user.rol == "asesor":
        query = query.filter(CRMCliente.asesor_id == current_user.id)
    if cliente_id:
        query = query.filter(CRMCliente.id == cliente_id)
    clientes = query.all()
    datha_ids = [c.datha_customer_id for c in clientes if c.datha_customer_id]
    names = [c.nombre for c in clientes if c.nombre and not c.datha_customer_id]
    return datha_ids, names


def _build_filter_params(
    db: Session,
    current_user: User,
    cliente_id: Optional[int],
    estado: Optional[str],
    q: Optional[str],
) -> tuple:
    datha_ids, names = _get_customer_filter(db, current_user, cliente_id)
    filters = ['po."isActive" = true']
    params: dict[str, Any] = {}

    customer_conditions = []
    if datha_ids:
        placeholders = ", ".join(f":cid_{i}" for i in range(len(datha_ids)))
        customer_conditions.append(f'c.id IN ({placeholders})')
        for i, cid in enumerate(datha_ids):
            params[f"cid_{i}"] = cid
    if names:
        placeholders = ", ".join(f":name_{i}" for i in range(len(names)))
        customer_conditions.append(f'c."businessName" IN ({placeholders})')
        for i, n in enumerate(names):
            params[f"name_{i}"] = n
    if customer_conditions:
        filters.append(f'({" OR ".join(customer_conditions)})')

    if estado:
        filters.append("po.status = :estado")
        params["estado"] = estado

    if q:
        filters.append('(c."businessName" ILIKE :q_pattern OR p.name ILIKE :q_pattern)')
        params["q_pattern"] = f"%{q}%"

    return " AND ".join(filters), params, datha_ids, names


def _build_pedidos_pdf(items: list[dict]) -> io.BytesIO:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    _MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

    def fmt_date(s):
        if not s:
            return '—'
        try:
            d = str(s)[:10].split('-')
            return f"{int(d[2])} {_MESES[int(d[1])-1]} {d[0]}"
        except Exception:
            return str(s)[:10]

    STATUS_ES = {
        'en_proceso': 'En Proceso', 'programada': 'Programada',
        'pausada': 'Pausada', 'terminada': 'Terminada', 'cancelada': 'Cancelada',
    }
    STATUS_BG = {
        'en_proceso': colors.HexColor('#DBEAFE'),
        'programada': colors.HexColor('#FEF9C3'),
        'pausada':    colors.HexColor('#FFEDD5'),
        'terminada':  colors.HexColor('#DCFCE7'),
        'cancelada':  colors.HexColor('#FEE2E2'),
    }

    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('t', parent=styles['Normal'],
                                 fontSize=14, fontName='Helvetica-Bold',
                                 alignment=TA_CENTER, spaceAfter=4)
    sub_style = ParagraphStyle('s', parent=styles['Normal'],
                               fontSize=9, alignment=TA_CENTER, spaceAfter=14,
                               textColor=colors.HexColor('#6B7280'))

    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    headers = ['OP', 'Cliente', 'Producto', 'SKU', 'Estado', 'A Producir', 'Producido', 'Avance', 'Entrega']
    col_widths = [2.5*cm, 5.5*cm, 6*cm, 2.5*cm, 2.5*cm, 2.2*cm, 2.2*cm, 1.8*cm, 2.5*cm]

    data = [headers]
    row_statuses = []
    for p in items:
        status = p.get('status') or ''
        row_statuses.append(status)
        avance = p.get('avance_pct')
        data.append([
            p.get('order_number') or f"OP-{p.get('id','')}",
            p.get('customer_name') or '—',
            p.get('product_name') or '—',
            p.get('product_sku') or '—',
            STATUS_ES.get(status, status) or '—',
            str(p.get('quantity_to_produce') or '—'),
            str(p.get('quantity_produced') or '—'),
            f"{avance}%" if avance is not None else '—',
            fmt_date(p.get('sales_order_delivery_date')),
        ])

    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1D4ED8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    for i, status in enumerate(row_statuses, start=1):
        bg = STATUS_BG.get(status)
        if bg:
            ts.append(('BACKGROUND', (4, i), (4, i), bg))

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(ts))

    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    doc.build([
        Paragraph("Órdenes de Producción", title_style),
        Paragraph(f"Generado el {now}", sub_style),
        table,
    ])
    buf.seek(0)
    return buf


@router.get("/pdf")
def pedidos_pdf(
    q: Optional[str] = None,
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    where, params, datha_ids, names = _build_filter_params(db, current_user, cliente_id, estado, q)
    if not datha_ids and not names and current_user.rol == "asesor":
        buf = _build_pedidos_pdf([])
        return StreamingResponse(buf, media_type='application/pdf',
                                 headers={'Content-Disposition': 'attachment; filename="pedidos.pdf"'})

    sql = text(f"""
        SELECT
            po.id, po.order_number, po.status,
            po.quantity_to_produce, po.quantity_produced,
            po.created_at,
            p.name AS product_name, p.sku AS product_sku,
            so.delivery_date AS sales_order_delivery_date,
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
                ELSE 4
            END,
            po.created_at DESC
        LIMIT 500
    """)
    items = _rows(prod_db.execute(sql, params))
    buf = _build_pedidos_pdf(items)
    return StreamingResponse(buf, media_type='application/pdf',
                             headers={'Content-Disposition': 'attachment; filename="pedidos.pdf"'})


@router.get("/")
def listar_pedidos(
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 30,
    db: Session = Depends(get_db),
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    datha_ids, names = _get_customer_filter(db, current_user, cliente_id)
    if not datha_ids and not names and current_user.rol == "asesor":
        return {"items": [], "total": 0, "page": page, "per_page": per_page}

    where, params, _, _ = _build_filter_params(db, current_user, cliente_id, estado, q)
    count_params = dict(params)
    params["limit"] = per_page
    params["offset"] = (page - 1) * per_page

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
            p.name AS product_name,
            p.sku  AS product_sku,
            p.color AS product_color,
            m.name AS machine_name,
            a.name AS area_name,
            so.order_number AS sales_order_number,
            so.delivery_date AS sales_order_delivery_date,
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
                ELSE 4
            END,
            po.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    items = _rows(prod_db.execute(sql, params))

    count_sql = text(f"""
        SELECT COUNT(*) FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE {where}
    """)
    total = prod_db.execute(count_sql, count_params).scalar() or 0

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/{orden_id}")
def detalle_pedido(
    orden_id: str,
    prod_db: Session = Depends(get_prod_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    sql = text("""
        SELECT
            po.id, po.order_number, po.status, po.priority,
            po.quantity_to_produce, po.quantity_produced, po.quantity_defective,
            po.actual_start_date, po.actual_end_date, po.created_at, po.notes,
            po.batch_code, po.estimated_production_time,
            p.name AS product_name, p.sku AS product_sku, p.color AS product_color,
            p.weight AS product_weight,
            m.name AS machine_name, m.type AS machine_type,
            md.name AS mold_name, md.cavities AS mold_cavities,
            a.name AS area_name,
            so.order_number AS sales_order_number,
            so.delivery_date AS sales_order_delivery_date,
            c."businessName" AS customer_name,
            c.city AS customer_city
        FROM production_order po
        JOIN sales_order_product sop ON sop.id = po.sales_order_product_id
        JOIN product p ON p.id = sop.product_id
        LEFT JOIN machine m ON m.id = po.machine_id
        LEFT JOIN mold md ON md.id = p."moldId"
        LEFT JOIN area a ON a.id = md."areaId"
        LEFT JOIN sales_order so ON so.id = sop.sales_order_id
        LEFT JOIN customer c ON c.id = so.customer_id
        WHERE po.id = :id
    """)
    row = _row(prod_db.execute(sql, {"id": orden_id}))
    if not row:
        raise HTTPException(404, "Pedido no encontrado")
    return row
