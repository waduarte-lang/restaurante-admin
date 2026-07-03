"""
Endpoints para Lista de Precios y Cotizaciones ATH.
  POST /api/crm/precios/upload      → admin sube CSV con lista de precios
  GET  /api/crm/precios/productos   → búsqueda de productos
  GET  /api/crm/precios/categorias  → categorías disponibles
  POST /api/crm/cotizaciones        → crear cotización
  GET  /api/crm/cotizaciones        → listar cotizaciones del asesor
  GET  /api/crm/cotizaciones/{id}/pdf → descargar PDF
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.lista_precio import Cotizacion, CotizacionItem, ListaPrecioProducto
from app.models.user import User

router = APIRouter(tags=["crm-precios"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class ItemIn(BaseModel):
    codigo:          Optional[str] = None
    descripcion:     str
    unidad:          str = "UND"
    cantidad:        float = 1
    precio_unitario: float


class CotizacionIn(BaseModel):
    cliente_nombre:   str
    cliente_nit:      Optional[str] = None
    cliente_email:    Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_ciudad:   Optional[str] = None
    notas:            Optional[str] = None
    iva_pct:          float = 0
    items:            list[ItemIn]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_consecutivo(db: Session) -> str:
    year = datetime.now().year
    last = (
        db.query(Cotizacion)
        .filter(Cotizacion.consecutivo.like(f"COT-{year}-%"))
        .order_by(Cotizacion.id.desc())
        .first()
    )
    if last:
        try:
            seq = int(last.consecutivo.rsplit("-", 1)[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"COT-{year}-{seq:04d}"


def _fmt(n) -> str:
    """Formato colombiano: $1.234.567"""
    try:
        v = float(n or 0)
        return f"${v:,.0f}".replace(",", ".")
    except Exception:
        return "$0"


def _generate_pdf(cot: Cotizacion) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    AZUL   = colors.HexColor("#1D4ED8")
    AZUL_L = colors.HexColor("#EFF6FF")
    GRIS   = colors.HexColor("#6B7280")
    NEGRO  = colors.black
    BLANCO = colors.white

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = "Helvetica"
    normal.fontSize = 9

    body: list = []

    # ── Encabezado ──────────────────────────────────────────────────────────
    header_data = [[
        Paragraph(
            "<font color='white' size='18'><b>ATH COTIZACIÓN</b></font><br/>"
            "<font color='#BFDBFE' size='9'>Plasticos ATH S.A.S.</font>",
            ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=18, textColor=BLANCO, leading=22),
        ),
        Paragraph(
            f"<font color='#BFDBFE' size='8'>Cotización No.</font><br/>"
            f"<font color='white' size='14'><b>{cot.consecutivo}</b></font><br/>"
            f"<font color='#BFDBFE' size='8'>{cot.created_at.strftime('%d/%m/%Y') if cot.created_at else ''}</font>",
            ParagraphStyle("r", fontName="Helvetica", fontSize=9, textColor=BLANCO, alignment=2, leading=16),
        ),
    ]]
    header_tbl = Table(header_data, colWidths=[10 * cm, 7.5 * cm])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), AZUL),
        ("TOPPADDING",  (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (0, 0),  14),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    body.append(header_tbl)
    body.append(Spacer(1, 0.5 * cm))

    # ── Info cliente ────────────────────────────────────────────────────────
    asesor_nombre = cot.asesor.nombre if cot.asesor else "—"
    cliente_lines = [
        ("Cliente:", cot.cliente_nombre or "—"),
        ("NIT:",     cot.cliente_nit or "—"),
    ]
    if cot.cliente_ciudad:
        cliente_lines.append(("Ciudad:", cot.cliente_ciudad))
    if cot.cliente_telefono:
        cliente_lines.append(("Teléfono:", cot.cliente_telefono))
    if cot.cliente_email:
        cliente_lines.append(("Correo:", cot.cliente_email))
    cliente_lines.append(("Asesor:", asesor_nombre))

    info_data = []
    for label, val in cliente_lines:
        info_data.append([
            Paragraph(f"<b>{label}</b>", ParagraphStyle("lbl", fontName="Helvetica-Bold", fontSize=8.5, textColor=GRIS)),
            Paragraph(val, ParagraphStyle("val", fontName="Helvetica", fontSize=8.5)),
        ])

    info_tbl = Table(info_data, colWidths=[3 * cm, 14.5 * cm])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_L),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#DBEAFE")),
    ]))
    body.append(info_tbl)
    body.append(Spacer(1, 0.5 * cm))

    # ── Tabla de productos ──────────────────────────────────────────────────
    th_style = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, textColor=BLANCO)
    td_style = ParagraphStyle("td", fontName="Helvetica", fontSize=8.5)
    td_r     = ParagraphStyle("tdr", fontName="Helvetica", fontSize=8.5, alignment=2)
    td_rb    = ParagraphStyle("tdrb", fontName="Helvetica-Bold", fontSize=8.5, alignment=2)

    rows = [
        [
            Paragraph("#",           th_style),
            Paragraph("Código",      th_style),
            Paragraph("Descripción", th_style),
            Paragraph("Ud.",         th_style),
            Paragraph("Cant.",       th_style),
            Paragraph("P. Unit.",    th_style),
            Paragraph("Total",       th_style),
        ]
    ]
    for i, it in enumerate(cot.items, 1):
        rows.append([
            Paragraph(str(i), td_style),
            Paragraph(it.codigo or "", td_style),
            Paragraph(it.descripcion or "", td_style),
            Paragraph(it.unidad or "UND", td_style),
            Paragraph(f"{float(it.cantidad or 1):,.0f}", td_r),
            Paragraph(_fmt(it.precio_unitario), td_r),
            Paragraph(_fmt(it.total), td_rb),
        ])

    prod_tbl = Table(rows, colWidths=[0.6 * cm, 1.8 * cm, 6.5 * cm, 1.2 * cm, 1.2 * cm, 2.5 * cm, 3.7 * cm])
    ts = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),   AZUL),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),  [BLANCO, AZUL_L]),
        ("TOPPADDING",    (0, 0), (-1, -1),  4),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  4),
        ("LEFTPADDING",   (0, 0), (-1, -1),  5),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  5),
        ("GRID",          (0, 0), (-1, -1),  0.3, colors.HexColor("#E5E7EB")),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
    ])
    prod_tbl.setStyle(ts)
    body.append(prod_tbl)
    body.append(Spacer(1, 0.4 * cm))

    # ── Totales ──────────────────────────────────────────────────────────────
    subtotal = float(cot.subtotal or 0)
    iva_pct  = float(cot.iva_pct or 0)
    iva_val  = float(cot.iva or 0)
    total    = float(cot.total or 0)

    totals = [[Paragraph("Subtotal", td_style), Paragraph(_fmt(subtotal), td_rb)]]
    if iva_pct:
        totals.append([Paragraph(f"IVA ({iva_pct:.0f}%)", td_style), Paragraph(_fmt(iva_val), td_rb)])
    totals.append([
        Paragraph("<b>TOTAL</b>", ParagraphStyle("ttl", fontName="Helvetica-Bold", fontSize=10, textColor=AZUL)),
        Paragraph(f"<b>{_fmt(total)}</b>", ParagraphStyle("ttlr", fontName="Helvetica-Bold", fontSize=10, textColor=AZUL, alignment=2)),
    ])

    totals_tbl = Table(totals, colWidths=[13.5 * cm, 4 * cm])
    totals_tbl.setStyle(TableStyle([
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("LINEABOVE",     (0, -1), (-1, -1), 0.8, AZUL),
    ]))
    body.append(totals_tbl)

    # ── Notas ────────────────────────────────────────────────────────────────
    if cot.notas:
        body.append(Spacer(1, 0.4 * cm))
        body.append(Paragraph(
            f"<b>Notas:</b> {cot.notas}",
            ParagraphStyle("notas", fontName="Helvetica", fontSize=8, textColor=GRIS),
        ))

    # ── Footer ────────────────────────────────────────────────────────────────
    body.append(Spacer(1, 0.6 * cm))
    body.append(Paragraph(
        "<font color='#9CA3AF' size='7.5'>Plasticos ATH S.A.S. — Esta cotización tiene validez de 15 días hábiles.</font>",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7.5, textColor=GRIS, alignment=1),
    ))

    doc.build(body)
    return buf.getvalue()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/crm/precios/upload")
def upload_lista_precios(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "gerente")),
):
    """Reemplaza la lista de precios completa desde un archivo CSV."""
    import unicodedata

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Se requiere un archivo CSV")

    content = file.file.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    def _norm(s: str) -> str:
        """Minúsculas sin tildes para comparación flexible."""
        return "".join(
            c for c in unicodedata.normalize("NFD", s.lower().strip())
            if unicodedata.category(c) != "Mn"
        )

    reader = csv.DictReader(io.StringIO(text))
    raw_headers = list(reader.fieldnames or [])
    if not raw_headers:
        raise HTTPException(status_code=400, detail="CSV sin encabezados")

    norm_headers = [_norm(h) for h in raw_headers]

    def _find_col(row: dict, *keywords: str) -> str:
        """Busca el primer header que contenga alguna de las palabras clave (sin tildes)."""
        for kw in keywords:
            for raw_h, norm_h in zip(raw_headers, norm_headers):
                if kw in norm_h:
                    return str(row.get(raw_h, "") or "").strip()
        return ""

    def _find_price_col(row: dict) -> str:
        """Detecta columna de precio: primero por nombre estándar, luego por patrón 'P. …'."""
        # Nombres estándar
        val = _find_col(row, "precio", "price", "valor", "unitario")
        if val:
            return val
        # Patrón ATH: columnas que empiezan con "p. " (ej. "P. 3K-20K")
        for raw_h, norm_h in zip(raw_headers, norm_headers):
            if norm_h.startswith("p. ") or norm_h.startswith("p."):
                v = str(row.get(raw_h, "") or "").strip()
                if v:
                    return v
        return ""

    def _categoria_from_codigo(codigo: str, fallback: str) -> str:
        """Deriva categoría del prefijo del código: PEAD/PET/INY."""
        if fallback:
            return fallback
        if not codigo:
            return "General"
        prefix = codigo.split("-")[0].upper()
        return {"PEAD": "Envases PEAD", "PET": "Envases PET", "INY": "Inyección / Tapas"}.get(prefix, prefix or "General")

    rows_raw = list(reader)
    if not rows_raw:
        raise HTTPException(status_code=400, detail="CSV vacío o sin filas de datos")

    productos: list[ListaPrecioProducto] = []
    errores = 0
    for row in rows_raw:
        desc      = _find_col(row, "producto", "descripcion", "description", "nombre", "articulo")
        precio_raw = _find_price_col(row)
        codigo    = _find_col(row, "codigo", "code", "ref", "referencia")
        unidad    = _find_col(row, "unidad", "unit", "und", "medida") or "UND"
        cat_raw   = _find_col(row, "categoria", "category", "linea", "grupo")
        categoria = _categoria_from_codigo(codigo, cat_raw)

        if not desc or not precio_raw:
            errores += 1
            continue

        precio_str = precio_raw.replace("$", "").replace("\xa0", "").strip()
        # Formato colombiano: separador miles = punto, decimal = coma
        if "," in precio_str and "." in precio_str:
            precio_str = precio_str.replace(".", "").replace(",", ".")
        elif "," in precio_str:
            precio_str = precio_str.replace(",", ".")
        else:
            precio_str = precio_str.replace(".", "")

        try:
            precio = float(precio_str)
            if precio <= 0:
                raise ValueError
        except ValueError:
            errores += 1
            continue

        productos.append(ListaPrecioProducto(
            codigo          = codigo or None,
            descripcion     = desc,
            precio_unitario = Decimal(str(precio)),
            unidad          = unidad,
            categoria       = categoria,
            activo          = True,
            updated_at      = datetime.now(),
        ))

    if not productos:
        raise HTTPException(status_code=400, detail=f"No se encontraron productos válidos. Columnas detectadas: {raw_headers}. Errores: {errores}")

    db.query(ListaPrecioProducto).delete()
    db.bulk_save_objects(productos)
    db.commit()

    return {
        "ok":       True,
        "cargados": len(productos),
        "errores":  errores,
        "mensaje":  f"Lista actualizada: {len(productos)} productos cargados",
    }


@router.get("/api/crm/precios/categorias")
def get_categorias(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "gerente", "asesor")),
):
    rows = (
        db.query(ListaPrecioProducto.categoria)
        .filter(ListaPrecioProducto.activo == True, ListaPrecioProducto.categoria.isnot(None))
        .distinct()
        .order_by(ListaPrecioProducto.categoria)
        .all()
    )
    return [r.categoria for r in rows]


@router.get("/api/crm/precios/productos")
def search_productos(
    q:         str = Query("", max_length=200),
    categoria: str = Query("", max_length=100),
    skip:      int = Query(0, ge=0),
    limit:     int = Query(60, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "gerente", "asesor")),
):
    qr = db.query(ListaPrecioProducto).filter(ListaPrecioProducto.activo == True)
    if q:
        term = f"%{q}%"
        qr = qr.filter(
            ListaPrecioProducto.descripcion.ilike(term) |
            ListaPrecioProducto.codigo.ilike(term)
        )
    if categoria:
        qr = qr.filter(ListaPrecioProducto.categoria == categoria)
    total = qr.count()
    items = qr.order_by(ListaPrecioProducto.descripcion).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id":               p.id,
                "codigo":           p.codigo,
                "descripcion":      p.descripcion,
                "precio_unitario":  float(p.precio_unitario),
                "unidad":           p.unidad,
                "categoria":        p.categoria,
            }
            for p in items
        ],
    }


@router.post("/api/crm/cotizaciones")
def crear_cotizacion(
    body: CotizacionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "gerente", "asesor")),
):
    if not body.items:
        raise HTTPException(status_code=400, detail="La cotización debe tener al menos un producto")

    subtotal = sum(it.precio_unitario * it.cantidad for it in body.items)
    iva_val  = subtotal * (body.iva_pct / 100)
    total    = subtotal + iva_val

    cot = Cotizacion(
        consecutivo      = _next_consecutivo(db),
        asesor_id        = user.id,
        cliente_nombre   = body.cliente_nombre,
        cliente_nit      = body.cliente_nit,
        cliente_email    = body.cliente_email,
        cliente_telefono = body.cliente_telefono,
        cliente_ciudad   = body.cliente_ciudad,
        notas            = body.notas,
        subtotal         = Decimal(str(subtotal)),
        iva_pct          = Decimal(str(body.iva_pct)),
        iva              = Decimal(str(iva_val)),
        total            = Decimal(str(total)),
        created_at       = datetime.now(),
    )
    db.add(cot)
    db.flush()

    for it in body.items:
        item_total = it.precio_unitario * it.cantidad
        db.add(CotizacionItem(
            cotizacion_id   = cot.id,
            codigo          = it.codigo,
            descripcion     = it.descripcion,
            unidad          = it.unidad,
            cantidad        = Decimal(str(it.cantidad)),
            precio_unitario = Decimal(str(it.precio_unitario)),
            total           = Decimal(str(item_total)),
        ))

    db.commit()
    db.refresh(cot)

    return {
        "id":          cot.id,
        "consecutivo": cot.consecutivo,
        "subtotal":    float(cot.subtotal),
        "iva":         float(cot.iva),
        "total":       float(cot.total),
    }


@router.get("/api/crm/cotizaciones")
def listar_cotizaciones(
    skip:  int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "gerente", "asesor")),
):
    qr = db.query(Cotizacion)
    if user.rol == "asesor":
        qr = qr.filter(Cotizacion.asesor_id == user.id)
    rows = qr.order_by(Cotizacion.id.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id":             c.id,
            "consecutivo":    c.consecutivo,
            "cliente_nombre": c.cliente_nombre,
            "cliente_nit":    c.cliente_nit,
            "subtotal":       float(c.subtotal),
            "total":          float(c.total),
            "asesor":         c.asesor.nombre if c.asesor else "—",
            "created_at":     c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.get("/api/crm/cotizaciones/{cot_id}/pdf")
def download_pdf(
    cot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "gerente", "asesor")),
):
    cot = db.query(Cotizacion).filter(Cotizacion.id == cot_id).first()
    if not cot:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if user.rol == "asesor" and cot.asesor_id != user.id:
        raise HTTPException(status_code=403, detail="Sin acceso a esta cotización")

    pdf_bytes = _generate_pdf(cot)
    filename  = f"ATH_Cotizacion_{cot.consecutivo}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
