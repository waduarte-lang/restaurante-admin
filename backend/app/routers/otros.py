from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.menu import MenuItem
from app.models.inventory import Recipe, StockMovement, Ingredient
from app.models.daily_menu import DailyMenu, DailyMenuItem
from app.schemas.order import OtrosOrderCreate, OrderOut
from app.auth.dependencies import get_current_user
from datetime import date
from app.utils.date import colToday

router = APIRouter(prefix="/api/otros", tags=["otros"])


@router.post("/order", response_model=OrderOut)
def create_otros_order(
    body: OtrosOrderCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Crear orden con adicionales (proteínas, jugos, ensaladas).
    - Descuenta automáticamente del inventario según recetas
    - Precio manual para cada item
    """
    if not body.items:
        raise HTTPException(status_code=400, detail="La orden debe tener al menos un item")

    # Obtener siguiente número de comanda
    last_order = db.query(Order).order_by(Order.comanda_numero.desc()).first()
    comanda_numero = (last_order.comanda_numero if last_order else 0) + 1

    # Crear orden
    total = 0.0
    order = Order(
        comanda_numero=comanda_numero,
        comanda_fecha=date.fromisoformat(colToday()),
        tipo=body.tipo,
        mesa_id=body.mesa_id if body.tipo == "mesa" else None,
        mesero_id=user.id,
        estado="abierto",
        observaciones=body.observaciones,
        cliente_nombre=body.cliente_nombre if body.tipo == "domicilio" else None,
        cliente_telefono=body.cliente_telefono if body.tipo == "domicilio" else None,
        cliente_direccion=body.cliente_direccion if body.tipo == "domicilio" else None,
    )
    db.add(order)
    db.flush()

    # Agregar items y descontar inventario
    for item_data in body.items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item_data.menu_item_id).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Plato {item_data.menu_item_id} no encontrado")

        # Crear OrderItem como adicional
        order_item = OrderItem(
            order_id=order.id,
            item_id=menu_item.id,
            cantidad=item_data.cantidad,
            precio_unitario=item_data.precio_unitario,
            es_adicional=True,
            nota=None
        )
        db.add(order_item)
        db.flush()

        # Descontar inventario según receta
        recetas = db.query(Recipe).filter(Recipe.item_id == menu_item.id).all()
        for receta in recetas:
            cantidad_a_descontar = receta.cantidad * item_data.cantidad

            # Crear movimiento de salida
            movimiento = StockMovement(
                ingredient_id=receta.ingredient_id,
                tipo="salida",
                cantidad=cantidad_a_descontar,
                motivo=f"Comanda #{comanda_numero} - {menu_item.nombre}",
                usuario_id=user.id
            )
            db.add(movimiento)

            # Actualizar stock
            ingrediente = receta.ingrediente
            ingrediente.stock_actual -= cantidad_a_descontar

        total += item_data.precio_unitario * item_data.cantidad

    order.total = total
    db.commit()
    db.refresh(order)

    # Cargar items con nombre
    for item in order.items:
        if item.item:
            item.item_nombre = item.item.nombre

    return order


@router.get("/menu-hoy")
def get_menu_hoy(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """
    Obtener proteínas, jugos y ensaladas del menú del día para "Otros"
    """
    today = colToday()
    menu_dia = db.query(DailyMenu).filter(
        DailyMenu.fecha == today,
        DailyMenu.activo == True
    ).first()

    if not menu_dia:
        return {"proteinas": [], "jugos": [], "ensaladas": []}

    items = db.query(DailyMenuItem).filter(
        DailyMenuItem.daily_menu_id == menu_dia.id
    ).all()

    proteinas = []
    jugos = []
    ensaladas = []

    for item in items:
        if item.menu_item and item.tipo in ["proteina", "proteina_sola"]:
            proteinas.append({
                "id": item.menu_item.id,
                "nombre": item.menu_item.nombre,
                "precio": item.menu_item.precio or 0.0
            })
        elif item.menu_item and item.tipo == "jugo":
            jugos.append({
                "id": item.menu_item.id,
                "nombre": item.menu_item.nombre,
                "precio": item.menu_item.precio or 0.0
            })
        elif item.menu_item and item.tipo == "ensalada":
            ensaladas.append({
                "id": item.menu_item.id,
                "nombre": item.menu_item.nombre,
                "precio": item.menu_item.precio or 0.0
            })

    return {
        "proteinas": proteinas,
        "jugos": jugos,
        "ensaladas": ensaladas
    }
