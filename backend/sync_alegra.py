"""
Sincroniza facturas + cobranzas de Alegra y reconcilia cartera.

Uso:
  python sync_alegra.py              # sincroniza mes actual
  python sync_alegra.py 2026-06      # sincroniza un mes específico
  python sync_alegra.py 2026-06 2026-07  # rango de meses
  python sync_alegra.py --pagos-only # solo cobranzas (sin filtro de mes)

Credenciales (variables de entorno o archivo .env):
  ALEGRA_EMAIL=tu@email.com
  ALEGRA_TOKEN=tu_token_alegra     <- Alegra > Configuración > API > Token

Obtener token: https://app.alegra.com/configuration/tabs/api
"""
import sys
import os
import json
import time
import base64
import requests
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL", "sqlite:///./restaurante.db")

from app.database import SessionLocal, Base, engine
from app.models.alegra_factura import AlegraFactura
from app.models.alegra_pago import AlegraPago
from app.models.cartera import CarteraFactura
from app.models.crm_cliente import CRMCliente
from sqlalchemy.orm import joinedload
from sqlalchemy import func as sqlfunc

Base.metadata.create_all(bind=engine)

ALEGRA_BASE = "https://app.alegra.com/api/v1"

NORM_VENDEDOR = {
    "johanna cardenas atencia": "JOHANA CARDENAS",
    "johana cardenas atencia": "JOHANA CARDENAS",
    "johanna cardenas": "JOHANA CARDENAS",
    "johana cardenas": "JOHANA CARDENAS",
    "wilfer hernando hoyos vanegas": "WILFER HOYOS",
    "wilfer hoyos": "WILFER HOYOS",
    "hernan dario atehortua lopera": "HERNAN ATEHORTUA",
    "hernan atehortua": "HERNAN ATEHORTUA",
    "diana milena osorio zapata": "DIANA OSORIO",
    "diana osorio": "DIANA OSORIO",
    "leidy jaramillo": "LEIDY JARAMILLO",
}


def _norm(name: str | None) -> str | None:
    if not name:
        return None
    return NORM_VENDEDOR.get(name.strip().lower(), name.strip().upper())


def _build_headers(email: str, token: str) -> dict:
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Accept": "application/json"}


def _fetch_invoices_paginated(headers: dict, extra_params: dict, label: str) -> list[dict]:
    """Descarga facturas paginando hasta agotar resultados."""
    all_items = []
    start = 0
    limit = 30  # máximo que acepta Alegra
    while True:
        params = {
            "start": start,
            "limit": limit,
            "metadata": "true",
            "fields": "id,date,dueDate,status,client,numberTemplate,total,totalPaid,balance,tax,subtotal,discount,seller,term,paymentMethod",
            **extra_params,
        }
        resp = requests.get(f"{ALEGRA_BASE}/invoices", headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  Error {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            items = data["data"]
            total = data.get("metadata", {}).get("total", len(items))
        else:
            items = data if isinstance(data, list) else []
            total = None  # desconocido — paramos cuando vengan menos de limit
        all_items.extend(items)
        print(f"  [{label}] start={start}: {len(items)} facturas{f' / {total} total' if total is not None else ''}")
        if len(items) < limit:
            break
        if total is not None and start + limit >= total:
            break
        start += limit
        time.sleep(0.3)
    return all_items


def _fetch_open_invoices(headers: dict) -> list[dict]:
    """Descarga TODAS las facturas con status=open (sin filtro de fecha)."""
    print("\nDescargando facturas OPEN...")
    items = _fetch_invoices_paginated(
        headers,
        {"status": "open", "order_field": "date", "order_direction": "ASC"},
        "OPEN",
    )
    print(f"  Total OPEN: {len(items)} facturas")
    return items


def _fetch_invoices(headers: dict, date_start: str, date_end: str) -> list[dict]:
    return _fetch_invoices_paginated(
        headers,
        {"date-start": date_start, "date-end": date_end,
         "order_field": "date", "order_direction": "ASC"},
        f"{date_start[:7]}",
    )


def _build_nit_asesor_map(db) -> dict[str, str]:
    clientes = db.query(CRMCliente).options(joinedload(CRMCliente.asesor)).all()
    m = {}
    for c in clientes:
        if c.nit and c.asesor:
            nombre = (c.asesor.nombre or c.asesor.username or "").strip().upper()
            if nombre:
                m[str(c.nit).strip()] = nombre
    return m


def _upsert_facturas(db, items: list[dict], nit_asesor: dict) -> tuple[int, int]:
    """Hace upsert de una lista de facturas Alegra. Devuelve (nuevas, actualizadas).

    Deduplication: si `alegra_id` empieza con 'CF-' y ya existe un registro con el mismo
    num_factura con ID numérico, actualiza ese registro en lugar de crear un duplicado.
    Los IDs tipo 'CF-FE9724' son vistas alternativas del mismo documento en Alegra.
    """
    nuevas = actualizadas = 0
    for inv in items:
        alegra_id = str(inv["id"])
        client = inv.get("client") or {}
        nit = str(client.get("identification") or "").strip()
        nombre_cliente = (client.get("name") or "").strip()
        alegra_cliente_id = str(client.get("id") or "")

        num_factura = (inv.get("numberTemplate") or {}).get("fullNumber") or ""
        seller = inv.get("seller") or {}
        vendedor_raw = (seller.get("name") or "").strip()
        vendedor = _norm(vendedor_raw) or nit_asesor.get(nit)

        fecha_str = inv.get("date") or ""
        vcto_str = inv.get("dueDate") or ""
        try:
            fecha_factura = date.fromisoformat(fecha_str) if fecha_str else None
        except Exception:
            fecha_factura = None
        try:
            fecha_vencimiento = date.fromisoformat(vcto_str) if vcto_str else None
        except Exception:
            fecha_vencimiento = None

        saldo_nuevo = float(inv.get("balance") or 0)

        existing = db.query(AlegraFactura).filter(AlegraFactura.alegra_id == alegra_id).first()
        if existing:
            existing.status = inv.get("status") or existing.status
            existing.saldo = saldo_nuevo
            existing.total_pagado = inv.get("totalPaid") or 0
            existing.fecha_vencimiento = fecha_vencimiento or existing.fecha_vencimiento
            existing.fecha_sync = datetime.now()
            actualizadas += 1
        else:
            # Si el ID es 'CF-...' buscar si ya existe el mismo num_factura con ID numérico
            if alegra_id.startswith("CF-") and num_factura:
                existing_by_num = (
                    db.query(AlegraFactura)
                    .filter(AlegraFactura.num_factura == num_factura)
                    .filter(~AlegraFactura.alegra_id.startswith("CF-"))
                    .first()
                )
                if existing_by_num:
                    # El documento CF- viene del query status=open → es el saldo actual real.
                    # Siempre actualizamos el registro numérico (cubre pagos parciales también).
                    existing_by_num.saldo = saldo_nuevo
                    existing_by_num.status = inv.get("status") or existing_by_num.status
                    existing_by_num.total_pagado = inv.get("totalPaid") or 0
                    existing_by_num.fecha_vencimiento = fecha_vencimiento or existing_by_num.fecha_vencimiento
                    existing_by_num.fecha_sync = datetime.now()
                    actualizadas += 1
                    continue  # no crear duplicado

            db.add(AlegraFactura(
                alegra_id=alegra_id,
                num_factura=num_factura,
                fecha_factura=fecha_factura,
                fecha_vencimiento=fecha_vencimiento,
                status=inv.get("status") or "open",
                termino_pago=inv.get("term") or "",
                alegra_cliente_id=alegra_cliente_id,
                nit=nit,
                nombre_cliente=nombre_cliente,
                subtotal=inv.get("subtotal") or 0,
                descuento=inv.get("discount") or 0,
                iva=inv.get("tax") or 0,
                total=inv.get("total") or 0,
                total_pagado=inv.get("totalPaid") or 0,
                saldo=saldo_nuevo,
                vendedor=vendedor,
                fecha_sync=datetime.now(),
            ))
            nuevas += 1
    return nuevas, actualizadas


def sync_open(email: str, token: str):
    """Descarga y persiste TODAS las facturas con status=open."""
    headers = _build_headers(email, token)
    items = _fetch_open_invoices(headers)
    db = SessionLocal()
    try:
        nit_asesor = _build_nit_asesor_map(db)
        nuevas, actualizadas = _upsert_facturas(db, items, nit_asesor)
        db.commit()
        print(f"  OPEN - Nuevas: {nuevas}  |  Actualizadas: {actualizadas}")
    finally:
        db.close()


def sync_mes(email: str, token: str, year: int, month: int):
    date_start = f"{year}-{month:02d}-01"
    date_end = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"

    print(f"\nSincronizando {year}-{month:02d} ({date_start} a {date_end})...")
    headers = _build_headers(email, token)
    items = _fetch_invoices(headers, date_start, date_end)
    print(f"  Total descargado: {len(items)} facturas")

    db = SessionLocal()
    try:
        nit_asesor = _build_nit_asesor_map(db)
        nuevas, actualizadas = _upsert_facturas(db, items, nit_asesor)
        db.commit()
        print(f"  Nuevas: {nuevas}  |  Actualizadas: {actualizadas}")
    finally:
        db.close()


def _fetch_payments(headers: dict) -> list[dict]:
    """Descarga todos los pagos de ingreso (type=in) desde Alegra."""
    all_items = []
    start = 0
    limit = 10
    while True:
        params = {
            "start": start,
            "limit": limit,
            "type": "in",
            "order_field": "date",
            "order_direction": "DESC",
        }
        resp = requests.get(f"{ALEGRA_BASE}/payments", headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  Error pagos {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        if isinstance(data, dict) and "data" in data:
            items = data["data"]
            total = data.get("metadata", {}).get("total", 0)
        else:
            items = data if isinstance(data, list) else []
            total = len(all_items) + len(items)
        if not items:
            break
        all_items.extend(items)
        print(f"  Pagos start={start}: {len(items)} (total: {total})")
        if len(items) < limit or start + limit >= total:
            break
        start += limit
        time.sleep(0.3)
    return all_items


def sync_pagos(email: str, token: str, mes_filtro: str | None = None):
    """Descarga cobranzas de Alegra y hace upsert en alegra_pagos."""
    print(f"\nSincronizando cobranzas Alegra{' (' + mes_filtro + ')' if mes_filtro else ''}...")
    headers = _build_headers(email, token)
    items = _fetch_payments(headers)
    print(f"  Total pagos descargados: {len(items)}")

    db = SessionLocal()
    try:
        nuevos = actualizados = 0
        for p in items:
            fecha_str = p.get("date") or ""
            try:
                fecha_pago = date.fromisoformat(fecha_str)
            except Exception:
                fecha_pago = None

            # Filtro de mes si se especificó
            if mes_filtro and fecha_pago:
                if fecha_pago.strftime("%Y-%m") != mes_filtro:
                    continue

            alegra_id = str(p["id"])
            client = p.get("client") or {}
            invoices = p.get("invoices") or []
            facturas_json = json.dumps([
                {"num": inv.get("number"), "monto": inv.get("amount"), "saldo": inv.get("balance")}
                for inv in invoices
            ])
            es_anticipo = bool(p.get("categories")) and not invoices
            template = p.get("numberTemplate") or {}
            num_recibo = template.get("fullNumber") or f"RC{alegra_id}"
            banco = (p.get("bankAccount") or {}).get("name") or ""

            existing = db.query(AlegraPago).filter(AlegraPago.alegra_id == alegra_id).first()
            if existing:
                existing.monto = p.get("amount") or 0
                existing.facturas_aplicadas = facturas_json
                actualizados += 1
            else:
                pago = AlegraPago(
                    alegra_id=alegra_id,
                    num_recibo=num_recibo,
                    fecha_pago=fecha_pago,
                    tipo=p.get("type") or "in",
                    metodo_pago=p.get("paymentMethod") or "",
                    monto=p.get("amount") or 0,
                    anotacion=(p.get("anotation") or "")[:200],
                    banco=banco,
                    alegra_cliente_id=str(client.get("id") or ""),
                    nit=str(client.get("identification") or "").strip(),
                    nombre_cliente=(client.get("name") or "").strip(),
                    facturas_aplicadas=facturas_json,
                    es_anticipo=es_anticipo,
                )
                db.add(pago)
                nuevos += 1

        db.commit()
        print(f"  Pagos nuevos: {nuevos}  |  Actualizados: {actualizados}")
    finally:
        db.close()


def reconciliar_cartera():
    """Actualiza cartera_facturas con saldos reales de alegra_facturas."""
    print("\nReconciliando cartera con Alegra...")
    db = SessionLocal()
    try:
        clientes_crm = db.query(CRMCliente).options(joinedload(CRMCliente.asesor)).all()
        nit_asesor = {
            str(c.nit).strip(): (c.asesor.nombre or c.asesor.username or "").strip().upper()
            for c in clientes_crm if c.nit and c.asesor
        }
        # Construir mapa deduplicado: por num_factura, quedarse con el de mayor saldo
        # (evita que registros CF- con saldo distinto sobrescriban los numéricos)
        alegra_all: dict = {}
        for f in db.query(AlegraFactura).all():
            existing = alegra_all.get(f.num_factura)
            if existing is None or float(f.saldo or 0) > float(existing.saldo or 0):
                alegra_all[f.num_factura] = f
        cartera_all = db.query(CarteraFactura).filter(CarteraFactura.activo == True).all()

        cobradas = parciales = 0
        for cf in cartera_all:
            af = alegra_all.get(cf.num_factura)
            if not af:
                continue
            saldo_alegra = float(af.saldo or 0)
            saldo_cartera = float(cf.valor_pendiente or 0)
            if saldo_alegra == 0 and saldo_cartera > 0:
                cf.activo = False
                cobradas += 1
            elif abs(saldo_alegra - saldo_cartera) > 1 and saldo_alegra < saldo_cartera:
                cf.valor_pendiente = Decimal(str(saldo_alegra))
                if af.fecha_vencimiento:
                    cf.fecha_vencimiento = af.fecha_vencimiento
                parciales += 1

        cartera_nums = {cf.num_factura for cf in db.query(CarteraFactura).all()}
        nuevas = 0
        for af in db.query(AlegraFactura).filter(AlegraFactura.saldo > 0).all():
            if af.num_factura in cartera_nums:
                continue
            vendedor = af.vendedor or nit_asesor.get(af.nit) or "SIN ASESOR"
            db.add(CarteraFactura(
                nit=af.nit,
                nombre_cliente=af.nombre_cliente,
                vendedor=vendedor,
                num_factura=af.num_factura,
                fecha_factura=af.fecha_factura,
                fecha_vencimiento=af.fecha_vencimiento,
                valor_pendiente=Decimal(str(float(af.saldo or 0))),
                activo=True,
            ))
            cartera_nums.add(af.num_factura)
            nuevas += 1

        db.commit()
        total = db.query(sqlfunc.sum(CarteraFactura.valor_pendiente)).filter(CarteraFactura.activo == True).scalar() or 0
        n = db.query(sqlfunc.count(CarteraFactura.id)).filter(CarteraFactura.activo == True).scalar()
        print(f"  Cobradas: {cobradas} | Parciales: {parciales} | Nuevas: {nuevas}")
        print(f"  Cartera final: {n} facturas | ${float(total):,.0f}")
    finally:
        db.close()


def main():
    email = os.getenv("ALEGRA_EMAIL", "")
    token = os.getenv("ALEGRA_TOKEN", "")

    if not email or not token:
        print("ERROR: define ALEGRA_EMAIL y ALEGRA_TOKEN como variables de entorno")
        print("  Ejemplo: set ALEGRA_EMAIL=tu@email.com && set ALEGRA_TOKEN=abc123")
        print("  Token en Alegra: Configuración > Integraciones > API")
        sys.exit(1)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    pagos_only = "--pagos-only" in flags

    if not pagos_only:
        # Siempre sincronizar facturas OPEN (todas las pendientes, sin importar fecha)
        sync_open(email, token)

        # Luego sincronizar el mes actual (o meses especificados) para detectar recién cobradas
        if not args:
            hoy = date.today()
            meses = [(hoy.year, hoy.month)]
        else:
            meses = []
            for a in args:
                year, month = map(int, a.split("-"))
                meses.append((year, month))

        for year, month in meses:
            sync_mes(email, token, year, month)

    # Sync pagos (todos, sin filtro de mes)
    sync_pagos(email, token)

    # Reconciliar cartera
    reconciliar_cartera()

    print("\nSync completado.")


if __name__ == "__main__":
    main()
