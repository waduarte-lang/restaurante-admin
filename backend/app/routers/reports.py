from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Optional
import json
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.expense import Expense
from app.models.inventory import Ingredient, Recipe
from app.models.menu import MenuItem
from app.models.cash_register import CashRegister
from app.models.cash_count import CashCount
from app.models.menu import MenuCategory
from app.models.inventory import Ingredient, Recipe
from app.auth.dependencies import require_roles

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ── KPIs consolidados para Dashboard ─────────────────────────────────────────

@router.get("/dashboard-kpis")
def dashboard_kpis(
    fecha_inicio: date = Query(default=None),
    fecha_fin:    date = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    """
    Retorna todos los KPIs relevantes del restaurante en una sola llamada.
    Incluye comparación con el período anterior de igual duración.
    """
    if not fecha_inicio:
        fecha_inicio = date.today()
    if not fecha_fin:
        fecha_fin = date.today()

    delta = (fecha_fin - fecha_inicio).days + 1
    prev_fin    = fecha_inicio - timedelta(days=1)
    prev_inicio = prev_fin    - timedelta(days=delta - 1)

    # ── Helper: pagos de un período ───────────────────────────────────────────
    def period_payments(fi, ff):
        return (
            db.query(Payment)
            .join(Order, Payment.order_id == Order.id)
            .filter(Order.comanda_fecha.between(fi, ff))
            .all()
        )

    # ── Período actual ────────────────────────────────────────────────────────
    pays_act  = period_payments(fecha_inicio, fecha_fin)
    total_act = sum(p.monto for p in pays_act)

    por_metodo: dict = {}
    for p in pays_act:
        por_metodo[p.metodo] = round(por_metodo.get(p.metodo, 0) + p.monto, 2)

    pagados = db.query(func.count(Order.id)).filter(
        Order.estado == "pagado",
        Order.comanda_fecha.between(fecha_inicio, fecha_fin),
    ).scalar() or 0

    cancelados = db.query(func.count(Order.id)).filter(
        Order.estado == "cancelado",
        Order.comanda_fecha.between(fecha_inicio, fecha_fin),
    ).scalar() or 0

    # ── Período anterior ──────────────────────────────────────────────────────
    pays_ant   = period_payments(prev_inicio, prev_fin)
    total_ant  = sum(p.monto for p in pays_ant)
    pagados_ant = db.query(func.count(Order.id)).filter(
        Order.estado == "pagado",
        Order.comanda_fecha.between(prev_inicio, prev_fin),
    ).scalar() or 0

    # ── Split salón / domicilio ───────────────────────────────────────────────
    def tipo_total(tipo, fi=fecha_inicio, ff=fecha_fin):
        return (
            db.query(func.sum(Payment.monto))
            .join(Order, Payment.order_id == Order.id)
            .filter(Order.comanda_fecha.between(fi, ff), Order.tipo == tipo)
            .scalar()
        ) or 0

    def tipo_count(tipo, fi=fecha_inicio, ff=fecha_fin):
        return db.query(func.count(Order.id)).filter(
            Order.estado == "pagado", Order.tipo == tipo,
            Order.comanda_fecha.between(fi, ff),
        ).scalar() or 0

    mesa_total = round(tipo_total("mesa"), 2)
    dom_total  = round(tipo_total("domicilio"), 2)
    mesa_count = tipo_count("mesa")
    dom_count  = tipo_count("domicilio")

    dom_fee = (
        db.query(func.sum(Order.valor_domicilio))
        .filter(
            Order.estado == "pagado", Order.tipo == "domicilio",
            Order.comanda_fecha.between(fecha_inicio, fecha_fin),
        )
        .scalar()
    ) or 0

    # Comparación canal vs período anterior
    mesa_ant = round(tipo_total("mesa", prev_inicio, prev_fin), 2)
    dom_ant  = round(tipo_total("domicilio", prev_inicio, prev_fin), 2)

    # ── Hora pico (distribución por hora del día) ─────────────────────────────
    hora_rows = (
        db.query(
            func.strftime("%H", Order.created_at).label("hora"),
            func.count(Order.id).label("cnt"),
        )
        .filter(
            Order.estado == "pagado",
            Order.comanda_fecha.between(fecha_inicio, fecha_fin),
        )
        .group_by("hora")
        .order_by("hora")
        .all()
    )
    hora_dict = {r.hora: r.cnt for r in hora_rows if r.hora}
    # Rango 6 – 22 h; horas vacías = 0
    hora_pico = [
        {"hora": h, "label": f"{h}:00", "pedidos": hora_dict.get(f"{h:02d}", 0)}
        for h in range(6, 23)
    ]

    # ── Cálculos derivados ────────────────────────────────────────────────────
    ticket_act = round(total_act / pagados, 2) if pagados else 0
    ticket_ant = round(total_ant / pagados_ant, 2) if pagados_ant else 0

    def pct(nuevo, viejo):
        if not viejo:
            return None
        return round((nuevo - viejo) / viejo * 100, 1)

    return {
        "fecha_inicio": str(fecha_inicio),
        "fecha_fin":    str(fecha_fin),
        # Ventas
        "total_ventas":          round(total_act, 2),
        "total_ventas_anterior": round(total_ant, 2),
        "ventas_pct_cambio":     pct(total_act, total_ant),
        # Ticket
        "ticket_promedio":          ticket_act,
        "ticket_promedio_anterior": ticket_ant,
        "ticket_pct_cambio":        pct(ticket_act, ticket_ant),
        # Pedidos
        "pedidos_pagados":   pagados,
        "pedidos_cancelados": cancelados,
        "tasa_cancelacion":  round(cancelados / (pagados + cancelados) * 100, 1)
                             if (pagados + cancelados) else 0,
        # Canal
        "mesa_total":    mesa_total,
        "mesa_count":    mesa_count,
        "mesa_anterior": mesa_ant,
        "dom_total":     dom_total,
        "dom_count":     dom_count,
        "dom_anterior":  dom_ant,
        "dom_fee_total": round(dom_fee, 2),
        # Métodos
        "por_metodo_pago": por_metodo,
        # Distribución horaria
        "hora_pico": hora_pico,
    }


@router.get("/sales")
def sales_report(
    fecha_inicio: date = Query(default=None),
    fecha_fin: date = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero"))
):
    if not fecha_inicio:
        fecha_inicio = date.today()
    if not fecha_fin:
        fecha_fin = date.today()

    # Filtrar por fecha del PAGO (created_at del Payment), no por fecha de la comanda.
    # Esto garantiza que comandas de crédito cobradas hoy aparezcan en el reporte de hoy.
    payments = (
        db.query(Payment)
        .filter(func.date(Payment.created_at).between(fecha_inicio, fecha_fin))
        .all()
    )
    total = sum(p.monto for p in payments)
    por_metodo: dict = {}
    for p in payments:
        por_metodo[p.metodo] = por_metodo.get(p.metodo, 0) + p.monto

    # Contar comandas únicas cuyo pago cayó en este rango de fechas
    orders_count = (
        db.query(func.count(func.distinct(Payment.order_id)))
        .filter(func.date(Payment.created_at).between(fecha_inicio, fecha_fin))
        .scalar()
    )

    return {
        "fecha_inicio": str(fecha_inicio),
        "fecha_fin": str(fecha_fin),
        "total_ventas": round(total, 2),
        "cantidad_pedidos": orders_count or 0,
        "por_metodo_pago": {k: round(v, 2) for k, v in por_metodo.items()},
        "ticket_promedio": round(total / orders_count, 2) if orders_count else 0,
    }


@router.get("/top-items")
def top_items(
    fecha_inicio: date = Query(default=None),
    fecha_fin: date = Query(default=None),
    limit: int = 10,
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero"))
):
    if not fecha_inicio:
        fecha_inicio = date.today() - timedelta(days=30)
    if not fecha_fin:
        fecha_fin = date.today()

    results = (
        db.query(MenuItem.nombre, func.sum(OrderItem.cantidad).label("total_vendido"),
                 func.sum(OrderItem.cantidad * OrderItem.precio_unitario).label("ingresos"))
        .join(OrderItem, MenuItem.id == OrderItem.item_id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.estado == "pagado", Order.comanda_fecha.between(fecha_inicio, fecha_fin))
        .group_by(MenuItem.id, MenuItem.nombre)
        .order_by(func.sum(OrderItem.cantidad).desc())
        .limit(limit)
        .all()
    )
    return [{"nombre": r.nombre, "total_vendido": r.total_vendido, "ingresos": round(r.ingresos, 2)} for r in results]


@router.get("/financial")
def financial_statement(
    year: int = Query(default=None),
    month: int = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin"))
):
    today = date.today()
    year = year or today.year
    month = month or today.month

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(seconds=1)

    ingresos = db.query(func.sum(Payment.monto)).filter(Payment.created_at.between(start, end)).scalar() or 0
    gastos = db.query(func.sum(Expense.monto)).filter(
        Expense.fecha.between(start.date(), end.date())
    ).scalar() or 0

    costo_ventas_raw = (
        db.query(func.sum(OrderItem.cantidad * Recipe.cantidad * Ingredient.costo_unitario))
        .join(Recipe, OrderItem.item_id == Recipe.item_id)
        .join(Ingredient, Recipe.ingredient_id == Ingredient.id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.estado == "pagado", Order.created_at.between(start, end))
        .scalar()
    ) or 0

    utilidad_bruta = ingresos - costo_ventas_raw
    utilidad_neta = utilidad_bruta - gastos

    return {
        "periodo": f"{year}-{str(month).zfill(2)}",
        "ingresos": round(ingresos, 2),
        "costo_ventas": round(costo_ventas_raw, 2),
        "utilidad_bruta": round(utilidad_bruta, 2),
        "gastos_operativos": round(gastos, 2),
        "utilidad_neta": round(utilidad_neta, 2),
        "margen_bruto_pct": round((utilidad_bruta / ingresos * 100) if ingresos else 0, 1),
        "margen_neto_pct": round((utilidad_neta / ingresos * 100) if ingresos else 0, 1),
    }


@router.get("/costs")
def item_costs(db: Session = Depends(get_db), _=Depends(require_roles("admin"))):
    items = db.query(MenuItem).filter(MenuItem.activo == True).all()
    result = []
    for item in items:
        costo = sum(r.cantidad * (r.ingrediente.costo_unitario or 0) for r in item.recetas if r.ingrediente)
        margen = item.precio - costo
        margen_pct = (margen / item.precio * 100) if item.precio else 0
        result.append({
            "id": item.id,
            "nombre": item.nombre,
            "precio": item.precio,
            "costo": round(costo, 2),
            "margen": round(margen, 2),
            "margen_pct": round(margen_pct, 1),
        })
    return sorted(result, key=lambda x: x["margen_pct"])


# ── Historial por día ─────────────────────────────────────────────────────────

def _build_order_row(o: Order, payment_map: dict) -> dict:
    return {
        "id": o.id,
        "comanda_numero": o.comanda_numero,
        "tipo": o.tipo,
        "mesa": o.mesa.numero if o.mesa else None,
        "cliente_nombre": o.cliente_nombre,
        "estado": o.estado,
        "total": o.total,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "items": [
            {
                "nombre": oi.item.nombre if oi.item else "?",
                "cantidad": oi.cantidad,
                "precio_unitario": oi.precio_unitario,
            }
            for oi in o.items
        ],
        "pagos": payment_map.get(o.id, []),
    }


@router.get("/daily")
def daily_report(
    fecha: date = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    if not fecha:
        fecha = date.today()

    start = datetime.combine(fecha, datetime.min.time())
    end   = datetime.combine(fecha, datetime.max.time())

    # Pagos del día
    payments = db.query(Payment).filter(Payment.created_at.between(start, end)).all()
    ventas_efectivo      = sum(p.monto for p in payments if p.metodo == "efectivo")
    ventas_tarjeta       = sum(p.monto for p in payments if p.metodo == "tarjeta")
    ventas_transferencia = sum(p.monto for p in payments if p.metodo == "transferencia")
    total_ventas         = ventas_efectivo + ventas_tarjeta + ventas_transferencia

    payment_map: dict = {}
    for p in payments:
        payment_map.setdefault(p.order_id, []).append({"metodo": p.metodo, "monto": p.monto})

    # Comandas del día
    orders = db.query(Order).filter(Order.comanda_fecha == fecha).order_by(Order.id).all()

    # Gastos del día
    gastos_q = db.query(Expense).filter(Expense.fecha == fecha).all()
    total_gastos = sum(g.monto for g in gastos_q)

    # Caja del día
    caja = db.query(CashRegister).filter(
        func.date(CashRegister.apertura) == fecha
    ).order_by(CashRegister.id.desc()).first()

    # Cuadres del día
    cuadres = []
    if caja:
        for c in db.query(CashCount).filter(CashCount.caja_id == caja.id).order_by(CashCount.created_at.desc()).all():
            cuadres.append({
                "id": c.id,
                "total_contado": c.total_contado,
                "total_esperado": c.total_esperado,
                "diferencia": c.diferencia,
                "observaciones": c.observaciones,
                "denominaciones": json.loads(c.denominaciones or "{}"),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })

    return {
        "fecha": str(fecha),
        "resumen": {
            "total_ventas": round(total_ventas, 2),
            "ventas_efectivo": round(ventas_efectivo, 2),
            "ventas_tarjeta": round(ventas_tarjeta, 2),
            "ventas_transferencia": round(ventas_transferencia, 2),
            "total_gastos": round(total_gastos, 2),
            "utilidad": round(total_ventas - total_gastos, 2),
            "total_pedidos": len(orders),
            "pedidos_pagados": sum(1 for o in orders if o.estado == "pagado"),
            "ticket_promedio": round(total_ventas / len(payments), 2) if payments else 0,
        },
        "caja": {
            "id": caja.id,
            "cajero": caja.cajero.nombre if caja.cajero else "—",
            "fondo_inicial": caja.fondo_inicial,
            "total_final": caja.total_final,
            "estado": caja.estado,
            "apertura": caja.apertura.isoformat() if caja.apertura else None,
            "cierre": caja.cierre.isoformat() if caja.cierre else None,
        } if caja else None,
        "gastos": [
            {"id": g.id, "concepto": g.concepto, "monto": g.monto, "categoria": g.categoria}
            for g in gastos_q
        ],
        "cuadres": cuadres,
        "comandas": [_build_order_row(o, payment_map) for o in orders],
    }


@router.get("/weekly")
def weekly_report(
    fecha: date = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    if not fecha:
        fecha = date.today()

    monday = fecha - timedelta(days=fecha.weekday())
    DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

    dias = []
    for i in range(7):
        d = monday + timedelta(days=i)
        start = datetime.combine(d, datetime.min.time())
        end   = datetime.combine(d, datetime.max.time())

        payments = (
            db.query(Payment).join(Order, Payment.order_id == Order.id)
            .filter(Order.comanda_fecha == d).all()
        )
        total_ventas         = sum(p.monto for p in payments)
        ventas_efectivo      = sum(p.monto for p in payments if p.metodo == "efectivo")
        ventas_tarjeta       = sum(p.monto for p in payments if p.metodo == "tarjeta")
        ventas_transferencia = sum(p.monto for p in payments if p.metodo == "transferencia")
        total_gastos  = db.query(func.sum(Expense.monto)).filter(Expense.fecha == d).scalar() or 0
        total_pedidos = db.query(func.count(Order.id)).filter(Order.comanda_fecha == d, Order.estado == "pagado").scalar() or 0

        dias.append({
            "fecha": str(d),
            "dia_nombre": DIAS[i],
            "total_ventas": round(total_ventas, 2),
            "ventas_efectivo": round(ventas_efectivo, 2),
            "ventas_tarjeta": round(ventas_tarjeta, 2),
            "ventas_transferencia": round(ventas_transferencia, 2),
            "total_gastos": round(float(total_gastos), 2),
            "utilidad": round(total_ventas - float(total_gastos), 2),
            "total_pedidos": total_pedidos,
        })

    return {
        "semana_inicio": str(monday),
        "semana_fin":    str(monday + timedelta(days=6)),
        "dias": dias,
        "totales": {
            "total_ventas": round(sum(d["total_ventas"] for d in dias), 2),
            "ventas_efectivo": round(sum(d["ventas_efectivo"] for d in dias), 2),
            "ventas_tarjeta": round(sum(d["ventas_tarjeta"] for d in dias), 2),
            "ventas_transferencia": round(sum(d["ventas_transferencia"] for d in dias), 2),
            "total_gastos": round(sum(d["total_gastos"] for d in dias), 2),
            "utilidad": round(sum(d["utilidad"] for d in dias), 2),
            "total_pedidos": sum(d["total_pedidos"] for d in dias),
        },
    }


@router.get("/monthly")
def monthly_report(
    year:  int = Query(default=None),
    month: int = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    today = date.today()
    year  = year  or today.year
    month = month or today.month

    _, days_in_month = monthrange(year, month)
    fecha_inicio = date(year, month, 1)
    fecha_fin    = min(date(year, month, days_in_month), today)

    # ── 1 query: ventas por día y método de pago ──────────────────────────────
    pay_rows = (
        db.query(
            Order.comanda_fecha,
            Payment.metodo,
            func.sum(Payment.monto).label("monto"),
        )
        .join(Payment, Payment.order_id == Order.id)
        .filter(Order.comanda_fecha.between(fecha_inicio, fecha_fin))
        .group_by(Order.comanda_fecha, Payment.metodo)
        .all()
    )

    # ── 1 query: gastos por día ───────────────────────────────────────────────
    gasto_rows = (
        db.query(Expense.fecha, func.sum(Expense.monto).label("total"))
        .filter(Expense.fecha.between(fecha_inicio, fecha_fin))
        .group_by(Expense.fecha)
        .all()
    )

    # ── 1 query: pedidos pagados por día ──────────────────────────────────────
    pedido_rows = (
        db.query(Order.comanda_fecha, func.count(Order.id).label("cnt"))
        .filter(Order.comanda_fecha.between(fecha_inicio, fecha_fin), Order.estado == "pagado")
        .group_by(Order.comanda_fecha)
        .all()
    )

    # Indexar resultados por fecha
    ventas: dict = {}
    for r in pay_rows:
        d = r.comanda_fecha
        if d not in ventas:
            ventas[d] = {"total": 0.0, "efectivo": 0.0, "tarjeta": 0.0, "transferencia": 0.0}
        ventas[d]["total"] += r.monto
        if r.metodo in ventas[d]:
            ventas[d][r.metodo] += r.monto

    gastos  = {r.fecha: float(r.total)  for r in gasto_rows}
    pedidos = {r.comanda_fecha: r.cnt   for r in pedido_rows}

    # Construir lista de días (solo hasta hoy)
    dias = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if d > today:
            break
        v = ventas.get(d, {"total": 0.0, "efectivo": 0.0, "tarjeta": 0.0, "transferencia": 0.0})
        g = gastos.get(d, 0.0)
        dias.append({
            "fecha": str(d),
            "dia": day,
            "total_ventas":         round(v["total"], 2),
            "ventas_efectivo":      round(v["efectivo"], 2),
            "ventas_tarjeta":       round(v["tarjeta"], 2),
            "ventas_transferencia": round(v["transferencia"], 2),
            "total_gastos":         round(g, 2),
            "utilidad":             round(v["total"] - g, 2),
            "total_pedidos":        pedidos.get(d, 0),
        })

    return {
        "anio": year,
        "mes": month,
        "dias": dias,
        "totales": {
            "total_ventas":         round(sum(d["total_ventas"]         for d in dias), 2),
            "ventas_efectivo":      round(sum(d["ventas_efectivo"]      for d in dias), 2),
            "ventas_tarjeta":       round(sum(d["ventas_tarjeta"]       for d in dias), 2),
            "ventas_transferencia": round(sum(d["ventas_transferencia"] for d in dias), 2),
            "total_gastos":         round(sum(d["total_gastos"]         for d in dias), 2),
            "utilidad":             round(sum(d["utilidad"]             for d in dias), 2),
            "total_pedidos":        sum(d["total_pedidos"]              for d in dias),
        },
    }


# ── Ventas detalladas por plato / categoría / tipo ───────────────────────────

@router.get("/items-detail")
def items_detail_report(
    fecha_inicio: date = Query(default=None),
    fecha_fin:    date = Query(default=None),
    categoria_id: Optional[int] = Query(default=None),
    tipo_plato:   Optional[str] = Query(default=None),
    item_id:      Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    """Ventas por plato con filtros por categoría, tipo de plato e ítem específico."""
    today = date.today()
    if not fecha_inicio:
        fecha_inicio = date(today.year, today.month, 1)
    if not fecha_fin:
        fecha_fin = today

    # Consulta base con JOIN
    q = (
        db.query(
            MenuItem.id.label("item_id"),
            MenuItem.nombre.label("item_nombre"),
            MenuItem.tipo_plato.label("tipo_plato"),
            MenuItem.precio.label("precio_base"),
            MenuCategory.id.label("categoria_id"),
            MenuCategory.nombre.label("categoria_nombre"),
            func.sum(OrderItem.cantidad).label("total_vendido"),
            func.sum(OrderItem.cantidad * OrderItem.precio_unitario).label("total_ingresos"),
            func.count(func.distinct(OrderItem.order_id)).label("num_pedidos"),
        )
        .join(OrderItem,    MenuItem.id             == OrderItem.item_id)
        .join(Order,        OrderItem.order_id      == Order.id)
        .join(MenuCategory, MenuItem.categoria_id   == MenuCategory.id)
        .filter(
            Order.estado     == "pagado",
            Order.comanda_fecha.between(fecha_inicio, fecha_fin),
        )
    )

    if categoria_id:
        q = q.filter(MenuItem.categoria_id == categoria_id)
    if tipo_plato:
        q = q.filter(MenuItem.tipo_plato == tipo_plato)
    if item_id:
        q = q.filter(MenuItem.id == item_id)

    rows = (
        q.group_by(
            MenuItem.id, MenuItem.nombre, MenuItem.tipo_plato,
            MenuItem.precio, MenuCategory.id, MenuCategory.nombre,
        )
        .order_by(func.sum(OrderItem.cantidad * OrderItem.precio_unitario).desc())
        .all()
    )

    grand_total = sum(r.total_ingresos or 0 for r in rows)
    grand_qty   = sum(r.total_vendido  or 0 for r in rows)

    items_list = []
    for r in rows:
        ing = round(r.total_ingresos or 0, 2)
        qty = r.total_vendido or 0
        items_list.append({
            "item_id":          r.item_id,
            "item_nombre":      r.item_nombre,
            "tipo_plato":       r.tipo_plato or "",
            "categoria_id":     r.categoria_id,
            "categoria_nombre": r.categoria_nombre,
            "precio_base":      r.precio_base,
            "total_vendido":    qty,
            "total_ingresos":   ing,
            "num_pedidos":      r.num_pedidos or 0,
            "pct_ingresos":     round(ing / grand_total * 100, 1) if grand_total else 0,
            "pct_cantidad":     round(qty / grand_qty   * 100, 1) if grand_qty   else 0,
        })

    # Agrupación por categoría
    by_cat: dict = {}
    for it in items_list:
        k = it["categoria_nombre"]
        e = by_cat.setdefault(k, {"nombre": k, "total_vendido": 0, "total_ingresos": 0.0, "items": []})
        e["total_vendido"]  += it["total_vendido"]
        e["total_ingresos"] += it["total_ingresos"]
        e["items"].append(it["item_nombre"])

    # Agrupación por tipo_plato
    by_tipo: dict = {}
    for it in items_list:
        k = it["tipo_plato"] or "Sin clasificar"
        e = by_tipo.setdefault(k, {"nombre": k, "total_vendido": 0, "total_ingresos": 0.0, "items": []})
        e["total_vendido"]  += it["total_vendido"]
        e["total_ingresos"] += it["total_ingresos"]
        e["items"].append(it["item_nombre"])

    # Opciones de filtro disponibles
    all_categories = db.query(MenuCategory).order_by(MenuCategory.nombre).all()
    tipo_rows = (
        db.query(MenuItem.tipo_plato)
        .filter(MenuItem.tipo_plato.isnot(None), MenuItem.tipo_plato != "")
        .distinct()
        .all()
    )
    all_tipos = sorted({r.tipo_plato for r in tipo_rows if r.tipo_plato})

    return {
        "fecha_inicio":  str(fecha_inicio),
        "fecha_fin":     str(fecha_fin),
        "grand_total":   round(grand_total, 2),
        "grand_qty":     grand_qty,
        "items":         items_list,
        "by_categoria":  sorted(by_cat.values(),  key=lambda x: x["total_ingresos"], reverse=True),
        "by_tipo_plato": sorted(by_tipo.values(), key=lambda x: x["total_ingresos"], reverse=True),
        "filters": {
            "categorias":   [{"id": c.id, "nombre": c.nombre} for c in all_categories],
            "tipos_plato":  all_tipos,
        },
    }


# ── Proyección de compras ─────────────────────────────────────────────────────

@router.get("/purchase-projection")
def purchase_projection(
    fecha_inicio:     date = Query(default=None),
    fecha_fin:        date = Query(default=None),
    dias_proyeccion:  int  = Query(default=7),
    categoria_id:     Optional[int] = Query(default=None),
    tipo_plato:       Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin")),
):
    """
    Proyecta cuánto ingrediente comprar basado en el promedio histórico de ventas.
    Fórmula: avg_diario_por_plato × dias_proyeccion × cantidad_en_receta
    """
    today = date.today()
    if not fecha_inicio:
        fecha_inicio = today - timedelta(days=29)   # últimos 30 días por defecto
    if not fecha_fin:
        fecha_fin = today

    # ── 1. Ventas históricas por plato ────────────────────────────────────────
    q = (
        db.query(
            MenuItem.id.label("item_id"),
            MenuItem.nombre.label("item_nombre"),
            MenuItem.tipo_plato.label("tipo_plato"),
            MenuCategory.nombre.label("categoria_nombre"),
            func.sum(OrderItem.cantidad).label("total_vendido"),
        )
        .join(OrderItem,    MenuItem.id           == OrderItem.item_id)
        .join(Order,        OrderItem.order_id    == Order.id)
        .join(MenuCategory, MenuItem.categoria_id == MenuCategory.id)
        .filter(Order.estado == "pagado", Order.comanda_fecha.between(fecha_inicio, fecha_fin))
    )
    if categoria_id:
        q = q.filter(MenuItem.categoria_id == categoria_id)
    if tipo_plato:
        q = q.filter(MenuItem.tipo_plato == tipo_plato)

    ventas_rows = q.group_by(
        MenuItem.id, MenuItem.nombre, MenuItem.tipo_plato, MenuCategory.nombre
    ).all()

    # Días del período con al menos una venta (días hábiles reales)
    dias_con_ventas = (
        db.query(func.count(func.distinct(Order.comanda_fecha)))
        .filter(Order.estado == "pagado", Order.comanda_fecha.between(fecha_inicio, fecha_fin))
        .scalar() or 1
    )
    dias_calendario = max((fecha_fin - fecha_inicio).days + 1, 1)

    # ── 2. Proyectar porciones por plato ─────────────────────────────────────
    platos_proyectados = []
    # item_id → porciones proyectadas
    proyeccion_map: dict[int, float] = {}

    for r in ventas_rows:
        avg_diario = (r.total_vendido or 0) / dias_con_ventas
        proyectado  = round(avg_diario * dias_proyeccion, 2)
        platos_proyectados.append({
            "item_id":           r.item_id,
            "item_nombre":       r.item_nombre,
            "tipo_plato":        r.tipo_plato or "",
            "categoria_nombre":  r.categoria_nombre,
            "total_historico":   r.total_vendido or 0,
            "avg_diario":        round(avg_diario, 2),
            "proyectado":        proyectado,
        })
        proyeccion_map[r.item_id] = proyectado

    # ── 3. Calcular necesidad de ingredientes ─────────────────────────────────
    # Cargar recetas de los platos relevantes
    if not proyeccion_map:
        ingredient_needs: dict = {}
    else:
        recipes = (
            db.query(Recipe)
            .filter(Recipe.item_id.in_(list(proyeccion_map.keys())))
            .all()
        )
        ingredient_ids = {r.ingredient_id for r in recipes}
        ingredients    = {
            ing.id: ing
            for ing in db.query(Ingredient).filter(Ingredient.id.in_(ingredient_ids)).all()
        }

        # Acumular necesidad por ingrediente
        ingredient_needs: dict = {}
        for rec in recipes:
            porciones = proyeccion_map.get(rec.item_id, 0)
            cantidad_necesaria = porciones * rec.cantidad
            ing = ingredients.get(rec.ingredient_id)
            if not ing:
                continue
            iid = rec.ingredient_id
            if iid not in ingredient_needs:
                ingredient_needs[iid] = {
                    "id":             ing.id,
                    "nombre":         ing.nombre,
                    "unidad":         rec.unidad or ing.unidad,
                    "stock_actual":   ing.stock_actual,
                    "stock_minimo":   ing.stock_minimo,
                    "costo_unitario": ing.costo_unitario,
                    "categoria":      ing.categoria,
                    "cantidad_necesaria": 0.0,
                    "platos_que_lo_usan": [],
                }
            ingredient_needs[iid]["cantidad_necesaria"] += cantidad_necesaria
            # Rastrear qué platos usan este ingrediente
            plato_nombre = next(
                (p["item_nombre"] for p in platos_proyectados if p["item_id"] == rec.item_id), "?"
            )
            if plato_nombre not in ingredient_needs[iid]["platos_que_lo_usan"]:
                ingredient_needs[iid]["platos_que_lo_usan"].append(plato_nombre)

    # ── 4. Calcular déficit y costo de compra ─────────────────────────────────
    lista_compras = []
    costo_total_proyectado = 0.0

    for v in ingredient_needs.values():
        necesario  = round(v["cantidad_necesaria"], 3)
        en_stock   = v["stock_actual"]
        deficit    = max(0.0, necesario - en_stock)
        costo      = round(deficit * v["costo_unitario"], 2)
        costo_total_proyectado += costo

        lista_compras.append({
            "id":                  v["id"],
            "nombre":              v["nombre"],
            "unidad":              v["unidad"],
            "categoria":           v["categoria"],
            "cantidad_necesaria":  necesario,
            "stock_actual":        en_stock,
            "stock_minimo":        v["stock_minimo"],
            "deficit":             round(deficit, 3),
            "costo_unitario":      v["costo_unitario"],
            "costo_compra":        costo,
            "platos_que_lo_usan":  v["platos_que_lo_usan"],
            "estado":              (
                "ok"       if deficit == 0 else
                "comprar"  if deficit > 0 else "ok"
            ),
        })

    # Ordenar: primero los que hay que comprar, luego por costo desc
    lista_compras.sort(key=lambda x: (-x["costo_compra"], x["nombre"]))

    # Filtros disponibles
    all_categories = db.query(MenuCategory).order_by(MenuCategory.nombre).all()
    tipo_rows = (
        db.query(MenuItem.tipo_plato)
        .filter(MenuItem.tipo_plato.isnot(None), MenuItem.tipo_plato != "")
        .distinct().all()
    )

    return {
        "fecha_inicio":            str(fecha_inicio),
        "fecha_fin":               str(fecha_fin),
        "dias_historico":          dias_con_ventas,
        "dias_calendario":         dias_calendario,
        "dias_proyeccion":         dias_proyeccion,
        "platos_analizados":       len(platos_proyectados),
        "costo_total_proyectado":  round(costo_total_proyectado, 2),
        "platos":                  sorted(platos_proyectados, key=lambda x: x["total_historico"], reverse=True),
        "lista_compras":           lista_compras,
        "ingredientes_ok":         sum(1 for i in lista_compras if i["deficit"] == 0),
        "ingredientes_comprar":    sum(1 for i in lista_compras if i["deficit"] > 0),
        "filters": {
            "categorias":  [{"id": c.id, "nombre": c.nombre} for c in all_categories],
            "tipos_plato": sorted({r.tipo_plato for r in tipo_rows if r.tipo_plato}),
        },
    }
