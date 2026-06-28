"""
Upserta facturas (y opcionalmente pagos) en la BD desde datos JSON.
Llamado por el agente de sync después de obtener datos via conectores Alegra MCP.

Uso:
  python sync_from_json.py --facturas '[{...}, ...]'
  python sync_from_json.py --file /ruta/a/facturas.json
"""
import sys, os, json, argparse
from datetime import datetime, date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL", "sqlite:///./restaurante.db")

from app.database import SessionLocal, Base, engine
Base.metadata.create_all(bind=engine)

NORM_VENDEDOR = {
    "johanna cardenas atencia": "JOHANA CARDENAS",
    "johana cardenas atencia":  "JOHANA CARDENAS",
    "johanna cardenas":         "JOHANA CARDENAS",
    "johana cardenas":          "JOHANA CARDENAS",
    "wilfer hernando hoyos vanegas": "WILFER HOYOS",
    "wilfer hoyos":             "WILFER HOYOS",
    "hernan dario atehortua lopera": "HERNAN ATEHORTUA",
    "hernan atehortua":         "HERNAN ATEHORTUA",
    "diana milena osorio zapata": "DIANA OSORIO",
    "diana osorio":             "DIANA OSORIO",
    "leidy jaramillo":          "LEIDY JARAMILLO",
}

def _norm_vendedor(name):
    if not name:
        return None
    return NORM_VENDEDOR.get(name.strip().lower(), name.strip().upper())


def upsert_facturas(invoices: list) -> tuple[int, int]:
    """Inserta/actualiza facturas. Retorna (nuevas, actualizadas)."""
    from app.models.alegra_factura import AlegraFactura
    db = SessionLocal()
    n, u = 0, 0
    try:
        for inv in invoices:
            alegra_id = str(inv.get("id", ""))
            if not alegra_id:
                continue

            num_tmpl    = inv.get("numberTemplate") or {}
            num_factura = num_tmpl.get("fullNumber") or num_tmpl.get("number") or alegra_id

            try:
                fecha = datetime.strptime(inv["date"], "%Y-%m-%d").date()
            except Exception:
                fecha = None
            try:
                vcto = datetime.strptime(inv["dueDate"], "%Y-%m-%d").date()
            except Exception:
                vcto = fecha

            client  = inv.get("client") or {}
            nit     = str(client.get("identification", ""))
            nombre  = client.get("name", "")
            total   = float(inv.get("total", 0) or 0)
            balance = float(inv.get("balance", 0) or 0)
            paid    = total - balance
            status  = "open" if inv.get("status") == "open" else "paid"
            seller  = _norm_vendedor((inv.get("seller") or {}).get("name"))
            term    = inv.get("term") or "De contado"

            existing = db.query(AlegraFactura).filter(AlegraFactura.alegra_id == alegra_id).first()
            if existing:
                existing.status        = status
                existing.saldo         = balance
                existing.total_pagado  = paid
                if fecha:
                    existing.fecha_factura = fecha
                if seller:
                    existing.vendedor = seller
                u += 1
            else:
                db.add(AlegraFactura(
                    alegra_id         = alegra_id,
                    num_factura       = num_factura,
                    fecha_factura     = fecha,
                    fecha_vencimiento = vcto,
                    status            = status,
                    termino_pago      = term,
                    alegra_cliente_id = str(client.get("id", "")),
                    nit               = nit,
                    nombre_cliente    = nombre,
                    total             = total,
                    saldo             = balance,
                    total_pagado      = paid,
                    vendedor          = seller,
                ))
                n += 1
        db.commit()
    finally:
        db.close()
    return n, u


def upsert_pagos(pagos: list) -> tuple[int, int]:
    """Inserta/actualiza pagos. Retorna (nuevas, actualizadas)."""
    from app.models.alegra_pago import AlegraPago
    db = SessionLocal()
    n, u = 0, 0
    try:
        for pago in pagos:
            alegra_id = str(pago.get("id", ""))
            if not alegra_id:
                continue

            num_tmpl   = pago.get("numberTemplate") or {}
            num_recibo = num_tmpl.get("fullNumber") or num_tmpl.get("number") or alegra_id
            try:
                fecha = datetime.strptime(pago["date"], "%Y-%m-%d").date()
            except Exception:
                fecha = None

            client = pago.get("client") or {}
            monto  = float(pago.get("amount", 0) or 0)
            metodo = pago.get("paymentMethod") or pago.get("method") or ""
            nota   = str(pago.get("observations") or "")[:200]
            cuenta = pago.get("account") or {}
            banco  = cuenta.get("name", "") if isinstance(cuenta, dict) else ""

            facturas_raw = pago.get("invoices") or []
            facturas_json = json.dumps([
                {"num": (inv.get("numberTemplate") or {}).get("fullNumber") or str(inv.get("id", "")),
                 "monto": inv.get("amount", 0), "saldo": inv.get("balance", 0)}
                for inv in facturas_raw
            ])

            existing = db.query(AlegraPago).filter(AlegraPago.alegra_id == alegra_id).first()
            if existing:
                existing.monto             = monto
                existing.facturas_aplicadas = facturas_json
                u += 1
            else:
                db.add(AlegraPago(
                    alegra_id          = alegra_id,
                    num_recibo         = num_recibo,
                    fecha_pago         = fecha,
                    tipo               = pago.get("type", "in"),
                    metodo_pago        = metodo,
                    monto              = monto,
                    anotacion          = nota,
                    banco              = banco,
                    alegra_cliente_id  = str(client.get("id", "")),
                    nit                = str(client.get("identification", "")),
                    nombre_cliente     = client.get("name", ""),
                    facturas_aplicadas = facturas_json,
                    es_anticipo        = not bool(facturas_raw),
                ))
                n += 1
        db.commit()
    finally:
        db.close()
    return n, u


def reconcile() -> tuple[int, int]:
    """Actualiza cartera_facturas. Retorna (total_facturas, total_monto)."""
    from app.models.cartera import CarteraFactura
    from app.models.alegra_factura import AlegraFactura
    from sqlalchemy import func

    db = SessionLocal()
    cobradas = actualizadas = nuevas = 0
    try:
        af_rows = db.query(AlegraFactura).all()
        af_map  = {a.num_factura: a for a in af_rows}

        for cf in db.query(CarteraFactura).filter(CarteraFactura.activo == True).all():
            af = af_map.get(cf.num_factura)
            if not af:
                continue
            if af.status == "paid" and float(af.saldo or 0) == 0:
                cf.activo = False
                cobradas += 1
            elif af.saldo is not None and abs(float(af.saldo) - float(cf.valor_pendiente or 0)) > 1:
                cf.valor_pendiente = float(af.saldo)
                actualizadas += 1

        cf_nums = {cf.num_factura for cf in db.query(CarteraFactura).all()}
        for af in af_rows:
            if af.status == "open" and float(af.saldo or 0) > 0 and af.num_factura not in cf_nums:
                db.add(CarteraFactura(
                    nit               = af.nit,
                    nombre_cliente    = af.nombre_cliente,
                    vendedor          = af.vendedor or "SIN ASESOR",
                    num_factura       = af.num_factura,
                    fecha_factura     = af.fecha_factura,
                    fecha_vencimiento = af.fecha_vencimiento,
                    valor_pendiente   = float(af.saldo),
                    activo            = True,
                ))
                nuevas += 1

        db.commit()
        total_f = db.query(CarteraFactura).filter(CarteraFactura.activo == True).count()
        total_m = db.query(func.sum(CarteraFactura.valor_pendiente)).filter(CarteraFactura.activo == True).scalar() or 0
    finally:
        db.close()

    print(f"  Cartera: {cobradas} cobradas, {actualizadas} saldos, {nuevas} nuevas")
    return total_f, int(total_m)


def write_last_sync(result: dict):
    path = os.path.join(os.path.dirname(__file__), "last_sync.json")
    result["timestamp"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--facturas", help="JSON string con lista de facturas")
    parser.add_argument("--pagos",    help="JSON string con lista de pagos")
    parser.add_argument("--file",     help="Ruta a archivo JSON con keys 'facturas' y/o 'pagos'")
    args = parser.parse_args()

    facturas_data = []
    pagos_data    = []

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            blob = json.load(f)
        facturas_data = blob.get("facturas", [])
        pagos_data    = blob.get("pagos", [])
    if args.facturas:
        facturas_data = json.loads(args.facturas)
    if args.pagos:
        pagos_data = json.loads(args.pagos)

    if not facturas_data and not pagos_data:
        print("Nada que procesar. Usa --facturas, --pagos o --file.")
        sys.exit(0)

    n_f = u_f = n_p = u_p = 0

    if facturas_data:
        print(f"Upserting {len(facturas_data)} facturas...")
        n_f, u_f = upsert_facturas(facturas_data)
        print(f"  Nuevas: {n_f} | Actualizadas: {u_f}")

    if pagos_data:
        print(f"Upserting {len(pagos_data)} pagos...")
        n_p, u_p = upsert_pagos(pagos_data)
        print(f"  Nuevos: {n_p} | Actualizados: {u_p}")

    print("Reconciliando cartera...")
    total_f, total_m = reconcile()
    print(f"  Total cartera: {total_f} facturas | ${total_m:,.0f}")

    write_last_sync({
        "facturas_nuevas":    n_f,
        "facturas_actualizadas": u_f,
        "pagos_nuevos":       n_p,
        "pagos_actualizados": u_p,
        "cartera_total":      total_f,
        "cartera_monto":      total_m,
    })
    print("Sync completado. last_sync.json actualizado.")
