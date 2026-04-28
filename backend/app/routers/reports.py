from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date, datetime, timedelta
from typing import Optional
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.expense import Expense
from app.models.inventory import Ingredient, Recipe
from app.models.menu import MenuItem
from app.auth.dependencies import require_roles

router = APIRouter(prefix="/api/reports", tags=["reports"])


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

    start = datetime.combine(fecha_inicio, datetime.min.time())
    end = datetime.combine(fecha_fin, datetime.max.time())

    payments = db.query(Payment).filter(Payment.created_at.between(start, end)).all()
    total = sum(p.monto for p in payments)
    por_metodo = {}
    for p in payments:
        por_metodo[p.metodo] = por_metodo.get(p.metodo, 0) + p.monto

    orders_count = db.query(func.count(Order.id)).filter(
        Order.estado == "pagado",
        Order.updated_at.between(start, end)
    ).scalar()

    return {
        "fecha_inicio": str(fecha_inicio),
        "fecha_fin": str(fecha_fin),
        "total_ventas": round(total, 2),
        "cantidad_pedidos": orders_count or 0,
        "por_metodo_pago": {k: round(v, 2) for k, v in por_metodo.items()},
        "ticket_promedio": round(total / len(payments), 2) if payments else 0,
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

    start = datetime.combine(fecha_inicio, datetime.min.time())
    end = datetime.combine(fecha_fin, datetime.max.time())

    results = (
        db.query(MenuItem.nombre, func.sum(OrderItem.cantidad).label("total_vendido"),
                 func.sum(OrderItem.cantidad * OrderItem.precio_unitario).label("ingresos"))
        .join(OrderItem, MenuItem.id == OrderItem.item_id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.estado == "pagado", Order.created_at.between(start, end))
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
