from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
import io

from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.cartera import CarteraFactura

router = APIRouter(prefix="/api/crm/cartera", tags=["crm-cartera"])
_ROLES = ("admin", "gerente", "asesor")

HOY = date.today


def _bucket(fecha_vcto: date | None) -> str:
    if not fecha_vcto:
        return "sin_fecha"
    dias = (date.today() - fecha_vcto).days
    if dias <= 0:
        return "vigente"
    if dias <= 30:
        return "d30"
    if dias <= 60:
        return "d60"
    if dias <= 90:
        return "d90"
    return "d90_mas"


# ─── Resumen de cartera por bucket ───────────────────────────────────────────

@router.get("/resumen")
def resumen_cartera(
    vendedor: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    q = db.query(CarteraFactura).filter(CarteraFactura.activo == True)
    if vendedor:
        q = q.filter(CarteraFactura.vendedor.ilike(f"%{vendedor}%"))
    facturas = q.all()

    buckets: dict[str, Decimal] = {"vigente": Decimal(0), "d30": Decimal(0), "d60": Decimal(0), "d90": Decimal(0), "d90_mas": Decimal(0)}
    total = Decimal(0)
    clientes = set()
    for f in facturas:
        b = _bucket(f.fecha_vencimiento)
        v = f.valor_pendiente or Decimal(0)
        if b in buckets:
            buckets[b] += v
        total += v
        clientes.add(f.nit)

    return {
        "total": float(total),
        "num_clientes": len(clientes),
        "num_facturas": len(facturas),
        "buckets": {k: float(v) for k, v in buckets.items()},
    }


# ─── Lista de facturas ────────────────────────────────────────────────────────

@router.get("/facturas")
def listar_facturas(
    q: Optional[str] = None,
    nit: Optional[str] = None,
    vendedor: Optional[str] = None,
    bucket: Optional[str] = None,
    page: int = 1,
    per_page: int = 500,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    query = db.query(CarteraFactura).filter(CarteraFactura.activo == True)
    if nit:
        clean = nit.replace(".", "").replace("-", "").strip()
        query = query.filter(
            CarteraFactura.nit.ilike(f"%{clean}%") | CarteraFactura.nit.ilike(f"%{nit}%")
        )
    if q:
        query = query.filter(
            CarteraFactura.nombre_cliente.ilike(f"%{q}%")
            | CarteraFactura.nit.ilike(f"%{q}%")
            | CarteraFactura.num_factura.ilike(f"%{q}%")
        )
    if vendedor:
        query = query.filter(CarteraFactura.vendedor.ilike(f"%{vendedor}%"))
    query = query.order_by(CarteraFactura.nombre_cliente, CarteraFactura.fecha_factura)

    all_rows = query.all()

    # filter by bucket after calculation
    if bucket:
        all_rows = [f for f in all_rows if _bucket(f.fecha_vencimiento) == bucket]

    total = len(all_rows)
    total_valor = sum(float(f.valor_pendiente or 0) for f in all_rows)
    rows = all_rows[(page - 1) * per_page: page * per_page]

    def to_dict(f: CarteraFactura):
        b = _bucket(f.fecha_vencimiento)
        dias = (date.today() - f.fecha_vencimiento).days if f.fecha_vencimiento else None
        return {
            "id": f.id,
            "nit": f.nit,
            "nombre_cliente": f.nombre_cliente,
            "vendedor": f.vendedor,
            "num_factura": f.num_factura,
            "fecha_factura": f.fecha_factura.isoformat() if f.fecha_factura else None,
            "fecha_vencimiento": f.fecha_vencimiento.isoformat() if f.fecha_vencimiento else None,
            "valor_pendiente": float(f.valor_pendiente or 0),
            "bucket": b,
            "dias_vencido": dias,
        }

    return {"total": total, "total_valor": total_valor, "page": page, "per_page": per_page, "items": [to_dict(r) for r in rows]}


# ─── Resumen por vendedor ─────────────────────────────────────────────────────

@router.get("/resumen-vendedores")
def resumen_por_vendedor(
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    """Devuelve total de cartera pendiente agrupado por vendedor."""
    facturas = db.query(CarteraFactura).filter(CarteraFactura.activo == True).all()
    resultado: dict[str, dict] = {}
    for f in facturas:
        v = (f.vendedor or "Sin vendedor").upper().strip()
        if v not in resultado:
            resultado[v] = {"vendedor": v, "total": 0.0, "num_facturas": 0,
                            "vigente": 0.0, "d30": 0.0, "d60": 0.0, "d90": 0.0, "d90_mas": 0.0}
        val = float(f.valor_pendiente or 0)
        b = _bucket(f.fecha_vencimiento)
        resultado[v]["total"] += val
        resultado[v]["num_facturas"] += 1
        if b in resultado[v]:
            resultado[v][b] += val
    return list(resultado.values())


# ─── Generación PDF ───────────────────────────────────────────────────────────

def _fmt_cop(v: float) -> str:
    if v == 0:
        return "-"
    return f"${v:,.0f}".replace(",", ".")


def _generar_pdf(facturas: list[CarteraFactura], titulo_extra: str = "") -> io.BytesIO:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    azul = colors.HexColor("#1D4ED8")
    azul_claro = colors.HexColor("#EFF6FF")
    gris = colors.HexColor("#F3F4F6")
    rojo = colors.HexColor("#DC2626")
    naranja = colors.HexColor("#D97706")
    amarillo = colors.HexColor("#F59E0B")
    verde = colors.HexColor("#059669")

    hdr_style = ParagraphStyle("hdr", parent=styles["Normal"], fontSize=18, textColor=azul,
                                fontName="Helvetica-Bold", alignment=TA_LEFT)
    empresa_style = ParagraphStyle("empresa", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#1E3A8A"),
                                fontName="Helvetica-Bold", alignment=TA_LEFT, spaceBefore=2)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=8, textColor=colors.grey,
                                fontName="Helvetica", alignment=TA_LEFT, spaceBefore=1)
    cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, fontName="Helvetica",
                                leading=9, wordWrap="CJK")

    hoy = date.today()

    # Agrupar por cliente
    from collections import defaultdict
    clientes: dict = defaultdict(list)
    for f in facturas:
        clientes[f.nit].append(f)

    story = []
    story.append(Paragraph("REPORTE DE CARTERA", hdr_style))
    story.append(Paragraph("INDUSTRIAS PLÁSTICAS ATH S.A.S  ·  NIT 900.525.204-4", empresa_style))
    if titulo_extra:
        story.append(Paragraph(titulo_extra, ParagraphStyle(
            "cliente_hdr", parent=styles["Normal"], fontSize=9,
            textColor=colors.HexColor("#1E3A8A"), fontName="Helvetica-Bold",
            alignment=TA_LEFT, spaceBefore=3
        )))
    story.append(Paragraph(f"Corte: {hoy.strftime('%d de %B de %Y')}", sub_style))
    story.append(Spacer(1, 0.4 * cm))

    # Tabla encabezado
    COLS = ["Cliente / Factura", "NIT", "F. Emisión", "F. Vencimiento", "0–30 días", "31–60 días", "61–90 días", ">90 días", "Total"]
    WIDTHS = [5.5*cm, 2.5*cm, 2.2*cm, 2.2*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.4*cm]

    data = [COLS]

    grand = {"d30": 0.0, "d60": 0.0, "d90": 0.0, "d90_mas": 0.0, "total": 0.0}

    for nit, rows in sorted(clientes.items(), key=lambda x: x[1][0].nombre_cliente):
        cli_nombre = rows[0].nombre_cliente
        cli_totals = {"d30": 0.0, "d60": 0.0, "d90": 0.0, "d90_mas": 0.0, "total": 0.0}

        for f in sorted(rows, key=lambda x: x.fecha_factura or date(2000, 1, 1)):
            b = _bucket(f.fecha_vencimiento)
            v = float(f.valor_pendiente or 0)
            fe = f.fecha_factura.strftime("%d/%m/%Y") if f.fecha_factura else "—"
            fv = f.fecha_vencimiento.strftime("%d/%m/%Y") if f.fecha_vencimiento else "—"

            row = [
                Paragraph(f.num_factura, cell_style),
                Paragraph(nit, cell_style),
                fe, fv,
                _fmt_cop(v) if b == "d30" else "-",
                _fmt_cop(v) if b == "d60" else "-",
                _fmt_cop(v) if b == "d90" else "-",
                _fmt_cop(v) if b == "d90_mas" else "-",
                _fmt_cop(v),
            ]
            data.append(row)
            bucket_key = b if b in cli_totals else "d90_mas"
            if b in cli_totals:
                cli_totals[b] += v
            cli_totals["total"] += v

        # Fila subtotal cliente
        sub_row = [
            Paragraph(f"<b>{cli_nombre[:35]}</b>", cell_style),
            Paragraph(f"<b>{nit}</b>", cell_style),
            "", "",
            _fmt_cop(cli_totals["d30"]) if cli_totals["d30"] else "-",
            _fmt_cop(cli_totals["d60"]) if cli_totals["d60"] else "-",
            _fmt_cop(cli_totals["d90"]) if cli_totals["d90"] else "-",
            _fmt_cop(cli_totals["d90_mas"]) if cli_totals["d90_mas"] else "-",
            _fmt_cop(cli_totals["total"]),
        ]
        data.append(sub_row)

        for k in grand:
            grand[k] += cli_totals.get(k, 0.0)

    # Fila TOTAL
    data.append([
        Paragraph("<b>TOTAL GENERAL</b>", cell_style), "",
        "", "",
        _fmt_cop(grand["d30"]), _fmt_cop(grand["d60"]),
        _fmt_cop(grand["d90"]), _fmt_cop(grand["d90_mas"]),
        _fmt_cop(grand["total"]),
    ])

    tbl = Table(data, colWidths=WIDTHS, repeatRows=1)

    # Identificar filas de subtotal (las que tienen texto bold cliente)
    # Construir estilos fila por fila
    ts = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, gris]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, azul),
        # Última fila TOTAL
        ("BACKGROUND", (0, -1), (-1, -1), azul),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 8),
        ("SPAN", (0, -1), (3, -1)),
    ]

    # Colorear columnas de aging en el header
    ts.append(("BACKGROUND", (4, 0), (4, 0), verde))
    ts.append(("BACKGROUND", (5, 0), (5, 0), amarillo))
    ts.append(("BACKGROUND", (6, 0), (6, 0), naranja))
    ts.append(("BACKGROUND", (7, 0), (7, 0), rojo))

    tbl.setStyle(TableStyle(ts))
    story.append(tbl)
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        f"<font size='7' color='grey'>Generado el {hoy.strftime('%d/%m/%Y')} · Plasticos ATH CRM · "
        f"{len(facturas)} facturas · {len(clientes)} clientes</font>",
        ParagraphStyle("footer", parent=styles["Normal"], alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf


@router.get("/pdf")
def pdf_cartera(
    vendedor: Optional[str] = None,
    nit: Optional[str] = None,
    q: Optional[str] = None,
    bucket: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles(*_ROLES)),
):
    query = db.query(CarteraFactura).filter(CarteraFactura.activo == True)
    if nit:
        query = query.filter(CarteraFactura.nit == nit)
    if vendedor:
        query = query.filter(CarteraFactura.vendedor.ilike(f"%{vendedor}%"))
    if q:
        query = query.filter(
            CarteraFactura.nombre_cliente.ilike(f"%{q}%")
            | CarteraFactura.nit.ilike(f"%{q}%")
            | CarteraFactura.num_factura.ilike(f"%{q}%")
        )
    query = query.order_by(CarteraFactura.nombre_cliente, CarteraFactura.fecha_factura)
    facturas = query.all()

    if bucket:
        facturas = [f for f in facturas if _bucket(f.fecha_vencimiento) == bucket]

    partes = []
    if nit and facturas:
        partes.append(f"Cliente: {facturas[0].nombre_cliente}  ·  NIT {facturas[0].nit}")
    if vendedor: partes.append(f"Asesor: {vendedor}")
    if q: partes.append(f'Búsqueda: "{q}"')
    if bucket:
        etiquetas = {"vigente": "Vigente", "d30": "0–30 días", "d60": "31–60 días", "d90": "61–90 días", "d90_mas": ">90 días"}
        partes.append(etiquetas.get(bucket, bucket))
    titulo = " · ".join(partes) if partes else ""
    buf = _generar_pdf(facturas, titulo)

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="cartera_ath_{date.today().isoformat()}.pdf"'},
    )
