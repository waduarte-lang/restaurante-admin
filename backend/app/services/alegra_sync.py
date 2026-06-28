"""
Servicio de sincronización automática con Alegra via REST API.
Credenciales en backend/.env:
  ALEGRA_EMAIL=gerentecomercial@plasticasath.com
  ALEGRA_TOKEN=<token>
"""
import os, base64, time, json, threading, logging
from datetime import datetime, date
from decimal import Decimal
import requests

log = logging.getLogger("alegra_sync")

ALEGRA_BASE = "https://api.alegra.com/api/v1"

_sync_state = {
    "running":       False,
    "last_sync":     None,
    "last_error":    None,
    "facturas_sync": 0,
    "pagos_sync":    0,
    "cartera_total": 0,
    "cartera_monto": 0,
}
_lock = threading.Lock()


def get_status() -> dict:
    with _lock:
        s = dict(_sync_state)
    s["last_sync"] = s["last_sync"].isoformat() if s["last_sync"] else None
    email = os.getenv("ALEGRA_EMAIL", "").strip()
    token = os.getenv("ALEGRA_TOKEN", "").strip()
    s["credentials_ok"] = bool(email and token and token != "AQUI_VA_EL_TOKEN_DE_ALEGRA")
    s["sync_mode"] = "api"
    return s


def _headers() -> dict | None:
    email = os.getenv("ALEGRA_EMAIL", "").strip()
    token = os.getenv("ALEGRA_TOKEN", "").strip()
    if not email or not token or token == "AQUI_VA_EL_TOKEN_DE_ALEGRA":
        return None
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Accept": "application/json"}


def _get(path: str, headers: dict, params: dict, retries: int = 3):
    url = f"{ALEGRA_BASE}/{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            log.warning(f"Alegra {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            log.warning(f"Request error intento {attempt+1}: {e}")
            time.sleep(1)
    return None


def _fetch_all_open(headers: dict) -> list:
    items, start, limit = [], 0, 10
    while True:
        data = _get("invoices", headers, {
            "start": start, "limit": limit,
            "status": "open",
            "order_field": "date", "order_direction": "ASC",
        })
        if not data:
            break
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        items.extend(batch)
        log.info(f"  open invoices start={start}: {len(batch)}")
        if len(batch) < limit:
            break
        start += limit
        time.sleep(0.35)
    return items


def _fetch_month(headers: dict, year: int, month: int) -> list:
    import calendar
    d_start = f"{year}-{month:02d}-01"
    d_end   = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    items, start, limit = [], 0, 10
    while True:
        data = _get("invoices", headers, {
            "start": start, "limit": limit,
            "date-start": d_start, "date-end": d_end,
            "order_field": "date", "order_direction": "ASC",
        })
        if not data:
            break
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < limit:
            break
        start += limit
        time.sleep(0.35)
    return items


def _fetch_payments(headers: dict, start_date: str) -> list:
    items, start, limit = [], 0, 10
    while True:
        data = _get("payments", headers, {
            "start": start, "limit": limit,
            "type": "in", "date-start": start_date,
        })
        if not data:
            break
        batch = data if isinstance(data, list) else data.get("data", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < limit:
            break
        start += limit
        time.sleep(0.35)
    return items


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

def _norm(name):
    if not name:
        return None
    return NORM_VENDEDOR.get(name.strip().lower(), name.strip().upper())


def _upsert_invoice(db, inv: dict) -> str:
    from app.models.alegra_factura import AlegraFactura
    alegra_id   = str(inv.get("id", ""))
    num_tmpl    = inv.get("numberTemplate") or {}
    num_factura = num_tmpl.get("fullNumber") or num_tmpl.get("number") or alegra_id
    try:    fecha = datetime.strptime(inv["date"], "%Y-%m-%d").date()
    except: fecha = None
    try:    vcto  = datetime.strptime(inv["dueDate"], "%Y-%m-%d").date()
    except: vcto  = fecha
    client  = inv.get("client") or {}
    total   = float(inv.get("total", 0) or 0)
    balance = float(inv.get("balance", 0) or 0)
    status  = "open" if inv.get("status") == "open" else "paid"
    seller  = _norm((inv.get("seller") or {}).get("name"))

    ex = db.query(AlegraFactura).filter(AlegraFactura.alegra_id == alegra_id).first()
    if ex:
        ex.status = status; ex.saldo = balance; ex.total_pagado = total - balance
        if fecha: ex.fecha_factura = fecha
        if seller: ex.vendedor = seller
        return "updated"
    db.add(AlegraFactura(
        alegra_id=alegra_id, num_factura=num_factura,
        fecha_factura=fecha, fecha_vencimiento=vcto,
        status=status, termino_pago=inv.get("term") or "De contado",
        alegra_cliente_id=str(client.get("id", "")),
        nit=str(client.get("identification", "")),
        nombre_cliente=client.get("name", ""),
        total=total, saldo=balance, total_pagado=total - balance,
        vendedor=seller,
    ))
    return "new"


def _upsert_payment(db, pago: dict) -> str:
    from app.models.alegra_pago import AlegraPago
    alegra_id  = str(pago.get("id", ""))
    num_tmpl   = pago.get("numberTemplate") or {}
    num_recibo = num_tmpl.get("fullNumber") or num_tmpl.get("number") or alegra_id
    try:    fecha = datetime.strptime(pago["date"], "%Y-%m-%d").date()
    except: fecha = None
    client = pago.get("client") or {}
    monto  = float(pago.get("amount", 0) or 0)
    facturas_raw  = pago.get("invoices") or []
    facturas_json = json.dumps([
        {"num": (i.get("numberTemplate") or {}).get("fullNumber") or str(i.get("id","")),
         "monto": i.get("amount", 0), "saldo": i.get("balance", 0)}
        for i in facturas_raw
    ])
    cuenta = pago.get("account") or {}
    ex = db.query(AlegraPago).filter(AlegraPago.alegra_id == alegra_id).first()
    if ex:
        ex.monto = monto; ex.facturas_aplicadas = facturas_json
        return "updated"
    db.add(AlegraPago(
        alegra_id=alegra_id, num_recibo=num_recibo, fecha_pago=fecha,
        tipo=pago.get("type", "in"),
        metodo_pago=pago.get("paymentMethod") or pago.get("method") or "",
        monto=monto,
        anotacion=str(pago.get("observations") or "")[:200],
        banco=cuenta.get("name", "") if isinstance(cuenta, dict) else "",
        alegra_cliente_id=str(client.get("id", "")),
        nit=str(client.get("identification", "")),
        nombre_cliente=client.get("name", ""),
        facturas_aplicadas=facturas_json,
        es_anticipo=not bool(facturas_raw),
    ))
    return "new"


def _reconcile(db) -> tuple[int, int]:
    from app.models.cartera import CarteraFactura
    from app.models.alegra_factura import AlegraFactura
    from sqlalchemy import func
    cobradas = actualizadas = nuevas = 0
    af_map = {a.num_factura: a for a in db.query(AlegraFactura).all()}
    for cf in db.query(CarteraFactura).filter(CarteraFactura.activo == True).all():
        af = af_map.get(cf.num_factura)
        if not af: continue
        if af.status == "paid" and float(af.saldo or 0) == 0:
            cf.activo = False; cobradas += 1
        elif af.saldo is not None and abs(float(af.saldo) - float(cf.valor_pendiente or 0)) > 1:
            cf.valor_pendiente = float(af.saldo); actualizadas += 1
    cf_nums = {cf.num_factura for cf in db.query(CarteraFactura).all()}
    for af in af_map.values():
        if af.status == "open" and float(af.saldo or 0) > 0 and af.num_factura not in cf_nums:
            db.add(CarteraFactura(
                nit=af.nit, nombre_cliente=af.nombre_cliente,
                vendedor=af.vendedor or "SIN ASESOR",
                num_factura=af.num_factura,
                fecha_factura=af.fecha_factura,
                fecha_vencimiento=af.fecha_vencimiento,
                valor_pendiente=float(af.saldo), activo=True,
            ))
            nuevas += 1
    db.commit()
    total_f = db.query(CarteraFactura).filter(CarteraFactura.activo == True).count()
    total_m = db.query(func.sum(CarteraFactura.valor_pendiente)).filter(CarteraFactura.activo == True).scalar() or 0
    log.info(f"  Cartera: {cobradas} cobradas, {actualizadas} saldos, {nuevas} nuevas | Total: {total_f} / ${int(total_m):,}")
    return total_f, int(total_m)


def run_sync(force: bool = False) -> dict:
    with _lock:
        if _sync_state["running"] and not force:
            return {"ok": False, "msg": "Sync ya en progreso"}
        _sync_state["running"] = True
        _sync_state["last_error"] = None

    try:
        from app.database import SessionLocal
        headers = _headers()
        if not headers:
            msg = "Faltan credenciales ALEGRA_EMAIL / ALEGRA_TOKEN"
            log.error(msg)
            with _lock:
                _sync_state["last_error"] = msg
                _sync_state["running"] = False
            return {"ok": False, "msg": msg}

        log.info("=== Alegra sync iniciando ===")
        db = SessionLocal()
        try:
            # 1. Facturas open
            log.info("Trayendo facturas open...")
            open_invs = _fetch_all_open(headers)
            n, u = 0, 0
            for inv in open_invs:
                r = _upsert_invoice(db, inv)
                if r == "new": n += 1
                else: u += 1
            db.commit()

            # 2. Mes actual (cobradas recientes)
            today = date.today()
            log.info(f"Trayendo mes {today.year}-{today.month:02d}...")
            for inv in _fetch_month(headers, today.year, today.month):
                _upsert_invoice(db, inv)
            db.commit()

            total_inv = n + u
            log.info(f"  Facturas: {n} nuevas, {u} actualizadas")

            # 3. Pagos del mes
            log.info("Trayendo pagos...")
            pay_start = f"{today.year}-{today.month:02d}-01"
            np, up = 0, 0
            for p in _fetch_payments(headers, pay_start):
                r = _upsert_payment(db, p)
                if r == "new": np += 1
                else: up += 1
            db.commit()
            log.info(f"  Pagos: {np} nuevos, {up} actualizados")

            # 4. Reconciliar cartera
            log.info("Reconciliando cartera...")
            total_f, total_m = _reconcile(db)

            now = datetime.now()
            with _lock:
                _sync_state.update({
                    "last_sync": now, "running": False,
                    "facturas_sync": total_inv, "pagos_sync": np + up,
                    "cartera_total": total_f, "cartera_monto": total_m,
                })
            log.info("=== Alegra sync completado ===")
            return {"ok": True, "facturas": total_inv, "pagos": np + up,
                    "cartera_facturas": total_f, "cartera_monto": total_m,
                    "timestamp": now.isoformat()}
        finally:
            db.close()

    except Exception as e:
        log.exception("Error en sync Alegra")
        with _lock:
            _sync_state["last_error"] = str(e)
            _sync_state["running"] = False
        return {"ok": False, "msg": str(e)}
