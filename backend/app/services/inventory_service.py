"""
Servicio de descuento automático de inventario.

Se llama cuando una orden pasa a estado 'pagado'.
- Busca la receta de cada ítem vendido
- Descuenta stock_actual del ingrediente × cantidad vendida
- Crea un StockMovement de tipo 'salida' por cada ingrediente
- NO bloquea la venta si el stock queda negativo (el negativo es señal de alerta)
- Usa la bandera order.stock_descontado para no descontar dos veces
"""
from sqlalchemy.orm import Session
from app.models.order import Order, OrderItem
from app.models.inventory import Ingredient, Recipe, StockMovement


def descontar_inventario(db: Session, order: Order) -> dict:
    """
    Descuenta los ingredientes consumidos por una orden pagada.

    Retorna un dict con:
        ok          : bool
        descontados : list de {ingrediente, cantidad, unidad}
        sin_receta  : list de nombres de platos sin receta configurada
        bajo_stock  : list de ingredientes que quedaron bajo el mínimo
    """
    if order.stock_descontado:
        return {"ok": True, "ya_descontado": True}

    # Cargar ítems con sus recetas
    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .all()
    )

    descontados = []
    sin_receta  = []
    bajo_stock  = []

    # Acumular cantidades por ingrediente (un plato puede repetirse)
    consumo: dict[int, float] = {}   # ingredient_id → cantidad total a descontar

    for oi in items:
        recetas = (
            db.query(Recipe)
            .filter(Recipe.item_id == oi.item_id)
            .all()
        )

        if not recetas:
            # Plato sin receta configurada — no se puede descontar
            if oi.item and oi.item.nombre not in sin_receta:
                sin_receta.append(oi.item.nombre)
            continue

        for r in recetas:
            consumo[r.ingredient_id] = (
                consumo.get(r.ingredient_id, 0.0) + r.cantidad * oi.cantidad
            )

    # Aplicar descuentos y crear movimientos
    for ingredient_id, cantidad_total in consumo.items():
        ing = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
        if not ing:
            continue

        ing.stock_actual = (ing.stock_actual or 0.0) - cantidad_total

        mov = StockMovement(
            ingredient_id=ingredient_id,
            tipo="salida",
            cantidad=cantidad_total,
            motivo=f"Venta comanda #{order.comanda_numero}",
            usuario_id=None,
        )
        db.add(mov)

        descontados.append({
            "ingrediente": ing.nombre,
            "cantidad":    round(cantidad_total, 4),
            "unidad":      ing.unidad,
            "stock_nuevo": round(ing.stock_actual, 4),
        })

        if ing.stock_actual < ing.stock_minimo:
            bajo_stock.append(ing.nombre)

    # Marcar la orden como descontada (evita duplicados)
    order.stock_descontado = True

    return {
        "ok":          True,
        "descontados": descontados,
        "sin_receta":  sin_receta,
        "bajo_stock":  bajo_stock,
    }
