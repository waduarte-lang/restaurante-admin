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


_MESES_ES = {
    1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
    7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"
}

def _fecha_es(d: date) -> str:
    return f"{d.day} de {_MESES_ES[d.month]} de {d.year}"


def _generar_pdf(facturas: list[CarteraFactura], titulo_extra: str = "") -> io.BytesIO:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=1.2*cm, bottomMargin=1.2*cm,
    )

    styles   = getSampleStyleSheet()
    C_AZUL   = colors.HexColor("#1D4ED8")
    C_AZUL_D = colors.HexColor("#1E3A8A")
    C_GRIS   = colors.HexColor("#F3F4F6")
    C_GRIS_L = colors.HexColor("#F9FAFB")
    C_VERDE  = colors.HexColor("#059669")
    C_AMAR   = colors.HexColor("#D97706")
    C_NARA   = colors.HexColor("#EA580C")
    C_ROJO   = colors.HexColor("#DC2626")
    C_ROJO_D = colors.HexColor("#991B1B")

    P = lambda text, **kw: Paragraph(text, ParagraphStyle("_", parent=styles["Normal"], **kw))

    cell = ParagraphStyle("cell", parent=styles["Normal"],
                          fontSize=7, fontName="Helvetica", leading=8.5, wordWrap="CJK")
    cell_bold = ParagraphStyle("cellb", parent=styles["Normal"],
                               fontSize=7, fontName="Helvetica-Bold", leading=8.5, wordWrap="CJK")

    hoy = date.today()

    story = []
    story.append(P("REPORTE DE CARTERA",
                   fontSize=16, textColor=C_AZUL, fontName="Helvetica-Bold", alignment=TA_LEFT))
    story.append(P("INDUSTRIAS PLÁSTICAS ATH S.A.S  ·  NIT 900.525.204-4",
                   fontSize=9, textColor=C_AZUL_D, fontName="Helvetica-Bold", spaceBefore=2))
    if titulo_extra:
        story.append(P(titulo_extra,
                       fontSize=8, textColor=C_AZUL_D, fontName="Helvetica-Bold", spaceBefore=2))
    story.append(P(f"Corte: {_fecha_es(hoy)}",
                   fontSize=7.5, textColor=colors.grey, spaceBefore=1))
    story.append(Spacer(1, 0.35*cm))

    # ── columnas ──────────────────────────────────────────────────────────────
    # Cliente/Factura | NIT | F.Emis | F.Venc | Vigente | 1-30 | 31-60 | 61-90 | >90 | Total
    COLS   = ["Cliente / Factura", "NIT", "F. Emis.", "F. Venc.",
              "Vigente", "1–30d", "31–60d", "61–90d", ">90d", "Total"]
    WIDTHS = [5.2*cm, 2.6*cm, 1.9*cm, 1.9*cm,
              2.2*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.2*cm, 2.3*cm]
    # Total ≈ 24.9cm → cabe en 29.7 - 2*1.2 = 27.3cm ✓

    # colores de cada columna de aging (índice 4-8 + header)
    AGE_COLS = {
        "vigente":  (4, C_VERDE,  colors.HexColor("#D1FAE5")),
        "d30":      (5, C_AMAR,   colors.HexColor("#FEF3C7")),
        "d60":      (6, C_NARA,   colors.HexColor("#FFEDD5")),
        "d90":      (7, C_ROJO,   colors.HexColor("#FEE2E2")),
        "d90_mas":  (8, C_ROJO_D, colors.HexColor("#FCA5A5")),
    }

    from collections import defaultdict
    clientes: dict = defaultdict(list)
    for f in facturas:
        clientes[f.nit].append(f)

    data  = [COLS]
    # rastrear qué filas son "subtotal" y qué bucket tiene cada fila de detalle
    row_types: list[str] = ["header"]   # "header" | "detail:{bucket}" | "subtotal" | "total"

    grand = {k: 0.0 for k in ["vigente","d30","d60","d90","d90_mas","total"]}

    for nit, rows in sorted(clientes.items(), key=lambda x: x[1][0].nombre_cliente):
        cli_nombre  = rows[0].nombre_cliente
        cli_totals  = {k: 0.0 for k in ["vigente","d30","d60","d90","d90_mas","total"]}

        for f in sorted(rows, key=lambda x: x.fecha_factura or date(2000,1,1)):
            b  = _bucket(f.fecha_vencimiento)
            v  = float(f.valor_pendiente or 0)
            fe = f.fecha_factura.strftime("%d/%m/%y")    if f.fecha_factura    else "—"
            fv = f.fecha_vencimiento.strftime("%d/%m/%y") if f.fecha_vencimiento else "—"

            row = [
                Paragraph(f.num_factura, cell),
                Paragraph(nit, cell),
                fe, fv,
                _fmt_cop(v) if b == "vigente"  else "—",
                _fmt_cop(v) if b == "d30"      else "—",
                _fmt_cop(v) if b == "d60"      else "—",
                _fmt_cop(v) if b == "d90"      else "—",
                _fmt_cop(v) if b == "d90_mas"  else "—",
                _fmt_cop(v),
            ]
            data.append(row)
            row_types.append(f"detail:{b}")
            if b in cli_totals:
                cli_totals[b] += v
            cli_totals["total"] += v

        # fila subtotal cliente
        data.append([
            Paragraph(f"<b>{cli_nombre[:40]}</b>", cell_bold),
            Paragraph(f"<b>{nit}</b>", cell_bold),
            "", "",
            _fmt_cop(cli_totals["vigente"])  if cli_totals["vigente"]  else "—",
            _fmt_cop(cli_totals["d30"])      if cli_totals["d30"]      else "—",
            _fmt_cop(cli_totals["d60"])      if cli_totals["d60"]      else "—",
            _fmt_cop(cli_totals["d90"])      if cli_totals["d90"]      else "—",
            _fmt_cop(cli_totals["d90_mas"])  if cli_totals["d90_mas"]  else "—",
            _fmt_cop(cli_totals["total"]),
        ])
        row_types.append("subtotal")
        for k in grand:
            grand[k] += cli_totals.get(k, 0.0)

    # fila total general
    data.append([
        Paragraph("<b>TOTAL GENERAL</b>", cell_bold), "", "", "",
        _fmt_cop(grand["vigente"]),
        _fmt_cop(grand["d30"]),
        _fmt_cop(grand["d60"]),
        _fmt_cop(grand["d90"]),
        _fmt_cop(grand["d90_mas"]),
        _fmt_cop(grand["total"]),
    ])
    row_types.append("total")

    # ── estilos base ──────────────────────────────────────────────────────────
    ts = [
        # header row
        ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,0), 7.5),
        ("BACKGROUND",  (0,0), (-1,0), C_AZUL),
        ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("ALIGN",       (0,0), (1,-1),  "LEFT"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE",    (0,1), (-1,-1), 6.5),
        ("GRID",        (0,0), (-1,-1), 0.25, colors.HexColor("#D1D5DB")),
        ("TOPPADDING",  (0,0), (-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 2),
        # fila total (última)
        ("BACKGROUND",  (0,-1), (-1,-1), C_AZUL_D),
        ("TEXTCOLOR",   (0,-1), (-1,-1), colors.white),
        ("FONTNAME",    (0,-1), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",    (0,-1), (-1,-1), 7.5),
        ("SPAN",        (0,-1), (3,-1)),
    ]

    # Colores de aging en header
    for b_key, (col_idx, hdr_color, _) in AGE_COLS.items():
        ts.append(("BACKGROUND", (col_idx,0), (col_idx,0), hdr_color))

    # Colorear celdas individuales de aging + filas subtotal
    for ri, rt in enumerate(row_types):
        r = ri  # fila en la tabla (0 = header)
        if rt.startswith("detail:"):
            bucket = rt.split(":")[1]
            # fondo alternado suave
            bg = colors.white if ri % 2 == 0 else C_GRIS_L
            ts.append(("BACKGROUND", (0,r), (-1,r), bg))
            # resaltar la celda del bucket activo
            if bucket in AGE_COLS:
                col_idx, _, cell_bg = AGE_COLS[bucket]
                ts.append(("BACKGROUND", (col_idx,r), (col_idx,r), cell_bg))
                ts.append(("TEXTCOLOR",  (col_idx,r), (col_idx,r), AGE_COLS[bucket][1]))
                ts.append(("FONTNAME",   (col_idx,r), (col_idx,r), "Helvetica-Bold"))
        elif rt == "subtotal":
            ts.append(("BACKGROUND",  (0,r), (-1,r), C_GRIS))
            ts.append(("FONTNAME",    (0,r), (-1,r), "Helvetica-Bold"))
            ts.append(("LINEABOVE",   (0,r), (-1,r), 0.5, C_AZUL))
            ts.append(("LINEBELOW",   (0,r), (-1,r), 0.5, C_AZUL))

    tbl = Table(data, colWidths=WIDTHS, repeatRows=1)
    tbl.setStyle(TableStyle(ts))
    story.append(tbl)

    story.append(Spacer(1, 0.4*cm))
    story.append(P(
        f"Generado el {hoy.strftime('%d/%m/%Y')}  ·  Plasticos ATH CRM  ·  "
        f"{len(facturas)} factura{'s' if len(facturas)!=1 else ''}  ·  {len(clientes)} cliente{'s' if len(clientes)!=1 else ''}",
        fontSize=6.5, textColor=colors.grey, alignment=TA_CENTER
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
