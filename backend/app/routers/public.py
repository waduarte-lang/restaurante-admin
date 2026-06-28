"""
Endpoints públicos — sin autenticación.
Usados por la página de pedidos web (domicilio por link de WhatsApp).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import date
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.models.daily_menu import DailyMenu, DailyMenuItem
from app.models.menu import MenuCategory, MenuItem
from app.models.order import Order, OrderItem
from app.models.domiciliario import Domiciliario
from app.models.payment import Payment
from app.models.cliente import Cliente
from app.models.order_estado_log import OrderEstadoLog
from app.services.inventory_service import descontar_inventario
from sqlalchemy import func

router = APIRouter(prefix="/api/public", tags=["public"])

# Categorías visibles en la página de pedidos
CATS_CARTA = [2, 3, 4, 5]  # Especiales, Casa, Pescados, Bowls


# ─── Schema de entrada ────────────────────────────────────────────────────────
class ItemPedido(BaseModel):
    item_id: int
    cantidad: int = 1
    nota: Optional[str] = None
    precio_unitario: Optional[float] = None


class PedidoPublico(BaseModel):
    cliente_nombre: str
    cliente_telefono: str
    cliente_direccion: str
    metodo_pago: str = "efectivo"       # efectivo | transferencia
    observaciones: Optional[str] = None
    items: List[ItemPedido]


# ─── GET /api/public/menu-hoy ─────────────────────────────────────────────────
@router.get("/menu-hoy")
def get_menu_hoy(db: Session = Depends(get_db)):
    """
    Devuelve el menú del día + carta completa.
    Público, sin autenticación.
    """
    resultado = {
        "menu_dia": None,
        "secciones": [],
    }

    # Menú del día
    menu = db.query(DailyMenu).filter(
        DailyMenu.fecha == date.today(),
        DailyMenu.activo == True
    ).first()

    if menu:
        sopas     = []
        proteinas = []
        bebidas   = []
        contorno  = None

        for i in menu.items:
            nombre = i.menu_item.nombre if i.menu_item else i.contorno_nombre
            if i.tipo == "sopa" and i.menu_item_id:
                sopas.append({"id": i.menu_item_id, "nombre": nombre})
            elif i.tipo == "proteina" and i.menu_item_id:
                proteinas.append({"id": i.menu_item_id, "nombre": nombre})
            elif i.tipo in ("bebida", "jugo") and i.menu_item_id:
                bebidas.append({"id": i.menu_item_id, "nombre": nombre})
            elif i.tipo == "contorno":
                contorno = nombre

        precio_sopa     = float(menu.precio_sopa or 8000)
        precio_proteina = float(menu.precio_proteina or 12000)
        precio_completo = float(menu.precio or 0) or (precio_sopa + precio_proteina)

        resultado["menu_dia"] = {
            "precio":          precio_completo,
            "precio_sopa":     precio_sopa,
            "precio_proteina": precio_proteina,
            "sopas":     sopas,
            "proteinas": proteinas,
            "bebidas":   bebidas,
            "contorno":  contorno,
        }

    # Carta: categorías 2, 3, 4, 5
    categorias = db.query(MenuCategory).filter(
        MenuCategory.id.in_(CATS_CARTA)
    ).order_by(MenuCategory.id).all()

    for cat in categorias:
        items = db.query(MenuItem).filter(
            MenuItem.categoria_id == cat.id,
            MenuItem.activo == True
        ).order_by(MenuItem.nombre).all()

        if items:
            resultado["secciones"].append({
                "id":     cat.id,
                "nombre": cat.nombre,
                "items": [
                    {
                        "id":         it.id,
                        "nombre":     it.nombre,
                        "precio":     float(it.precio or 0),
                        "imagen_url": it.imagen_url or None,
                    }
                    for it in items
                ],
            })

    return resultado


# ─── POST /api/public/pedido ──────────────────────────────────────────────────
@router.post("/pedido")
def crear_pedido_publico(pedido: PedidoPublico, db: Session = Depends(get_db)):
    """
    Crea una orden de domicilio desde la página pública.
    Sin autenticación — validaciones básicas de negocio.
    """
    # Validaciones básicas
    if not pedido.cliente_nombre.strip():
        raise HTTPException(400, "Nombre requerido")
    if not pedido.cliente_direccion.strip():
        raise HTTPException(400, "Dirección requerida")
    if not pedido.items:
        raise HTTPException(400, "El pedido está vacío")
    if pedido.metodo_pago not in ("efectivo", "transferencia", "tarjeta", "credito"):
        raise HTTPException(400, "Método de pago inválido")

    # Validar items y calcular total
    total = 0.0
    order_items = []
    for it in pedido.items:
        menu_item = db.query(MenuItem).filter(
            MenuItem.id == it.item_id,
            MenuItem.activo == True
        ).first()
        if not menu_item:
            raise HTTPException(400, f"Item {it.item_id} no encontrado o inactivo")

        precio = it.precio_unitario if it.precio_unitario is not None else float(menu_item.precio or 0)
        total += precio * it.cantidad
        order_items.append((menu_item, it.cantidad, it.nota, precio))

    # Número de comanda consecutivo
    last = db.query(func.max(Order.comanda_numero)).scalar()
    comanda_numero = (last or 0) + 1

    # Crear orden
    orden = Order(
        comanda_numero    = comanda_numero,
        comanda_fecha     = date.today(),
        tipo              = "domicilio",
        estado            = "abierto",
        total             = total,
        cliente_nombre    = pedido.cliente_nombre.strip(),
        cliente_telefono  = pedido.cliente_telefono.strip(),
        cliente_direccion = pedido.cliente_direccion.strip(),
        metodo_pago       = pedido.metodo_pago,
        observaciones     = pedido.observaciones,
        valor_domicilio   = 0.0,
        fuente            = "whatsapp_web",
    )
    db.add(orden)
    db.flush()

    for menu_item, cantidad, nota, precio in order_items:
        oi = OrderItem(
            order_id        = orden.id,
            item_id         = menu_item.id,
            cantidad        = cantidad,
            precio_unitario = precio,
            nota            = nota,
            estado          = "pendiente",
        )
        db.add(oi)

    # Upsert en tabla clientes — para que el teléfono quede registrado para próximas visitas
    tel = pedido.cliente_telefono.strip()
    if tel:
        cliente_existente = db.query(Cliente).filter(Cliente.telefono == tel).first()
        if cliente_existente:
            # Actualizar nombre y dirección si cambió algo
            cliente_existente.nombre    = pedido.cliente_nombre.strip()
            cliente_existente.direccion = pedido.cliente_direccion.strip()
        else:
            db.add(Cliente(
                nombre    = pedido.cliente_nombre.strip(),
                telefono  = tel,
                direccion = pedido.cliente_direccion.strip(),
            ))

    db.commit()
    db.refresh(orden)

    return {
        "ok":             True,
        "id":             orden.id,
        "comanda_numero": orden.comanda_numero,
        "total":          orden.total,
    }


# ─── GET /api/public/cliente-por-telefono ────────────────────────────────────
@router.get("/cliente-por-telefono")
def cliente_por_telefono(telefono: str, db: Session = Depends(get_db)):
    """
    Busca un cliente en la tabla clientes por número de teléfono.
    Devuelve nombre y dirección para autocompletar el formulario.
    """
    t = telefono.strip()
    if not t:
        raise HTTPException(400, "Teléfono requerido")

    # Try exact match first, then fallback to LIKE (handles spaces/dashes in stored numbers)
    cliente = (
        db.query(Cliente)
        .filter(Cliente.telefono == t)
        .first()
    )
    if not cliente:
        cliente = (
            db.query(Cliente)
            .filter(Cliente.telefono.ilike(f"%{t}%"))
            .first()
        )
    if not cliente:
        # Fallback: buscar en órdenes anteriores (clientes que pidieron antes del fix)
        orden_anterior = (
            db.query(Order)
            .filter(
                Order.tipo == "domicilio",
                Order.cliente_telefono == t,
                Order.cliente_nombre.isnot(None),
            )
            .order_by(Order.id.desc())
            .first()
        )
        if orden_anterior:
            # Registrar en clientes para próximas búsquedas
            db.add(Cliente(
                nombre    = orden_anterior.cliente_nombre or "",
                telefono  = t,
                direccion = orden_anterior.cliente_direccion or "",
            ))
            db.commit()
            return {
                "nombre":    orden_anterior.cliente_nombre or "",
                "direccion": orden_anterior.cliente_direccion or "",
                "telefono":  t,
            }
        raise HTTPException(404, "Cliente no encontrado")

    return {
        "nombre":    cliente.nombre or "",
        "direccion": cliente.direccion or "",
        "telefono":  t,
    }


# ─── GET /api/public/seguimiento/{comanda_numero} ─────────────────────────────
ESTADOS_CLIENTE = {
    "abierto":   {"paso": 1, "label": "Recibido — pendiente de confirmación", "emoji": "⏳", "color": "yellow"},
    "en_cocina": {"paso": 2, "label": "Confirmado — en preparación",           "emoji": "👨‍🍳", "color": "blue"},
    "listo":     {"paso": 3, "label": "En camino",                              "emoji": "🛵", "color": "orange"},
    "pagado":    {"paso": 4, "label": "Entregado",                              "emoji": "✅", "color": "green"},
    "cancelado": {"paso": 0, "label": "Cancelado",                              "emoji": "❌", "color": "red"},
}

@router.get("/seguimiento/{comanda_numero}")
def get_seguimiento(comanda_numero: int, db: Session = Depends(get_db)):
    """Seguimiento público de un pedido por número de comanda."""
    orden = db.query(Order).filter(Order.comanda_numero == comanda_numero).first()
    if not orden:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    info = ESTADOS_CLIENTE.get(orden.estado, {"paso": 1, "label": orden.estado, "emoji": "📦", "color": "gray"})

    # Solo mostrar total cuando ya fue aprobado (en_cocina, listo, pagado)
    mostrar_total = orden.estado in ("en_cocina", "listo", "pagado")
    subtotal       = float(orden.total or 0)
    valor_domicilio = float(orden.valor_domicilio or 0)
    total_con_domicilio = subtotal  # total ya incluye domicilio si fue asignado

    return {
        "comanda_numero":    orden.comanda_numero,
        "cliente_nombre":    orden.cliente_nombre,
        "estado":            orden.estado,
        "paso":              info["paso"],
        "estado_label":      info["label"],
        "estado_emoji":      info["emoji"],
        "estado_color":      info["color"],
        "tipo":              orden.tipo,
        "mostrar_total":     mostrar_total,
        "subtotal":          subtotal,
        "valor_domicilio":   valor_domicilio,
        "total":             total_con_domicilio,
    }


# ─── App del domiciliario ─────────────────────────────────────────────────────

class EntregarBody(BaseModel):
    pin: str
    metodo_pago: str = "efectivo"   # efectivo | transferencia | mixto
    monto_efectivo: Optional[float] = None  # monto del primer método en mixto
    mixto_metodo1: Optional[str] = None     # primer método (default 'efectivo')
    mixto_metodo2: Optional[str] = None     # segundo método (default 'transferencia')


class TomarBody(BaseModel):
    pin: str
    comanda_numero: int

@router.get("/domiciliario/activos")
def get_domiciliarios_activos(db: Session = Depends(get_db)):
    """Lista de domiciliarios activos para el selector de login."""
    doms = db.query(Domiciliario).filter(Domiciliario.activo == True).order_by(Domiciliario.nombre).all()
    return [{"id": d.id, "nombre": d.nombre} for d in doms]


@router.post("/domiciliario/login")
def domiciliario_login(body: dict, db: Session = Depends(get_db)):
    """Verifica id + pin del domiciliario."""
    dom_id = body.get("dom_id")
    pin    = str(body.get("pin", "")).strip()
    if not dom_id or not pin:
        raise HTTPException(400, "Faltan datos")
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id, Domiciliario.activo == True).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")
    if not d.pin or d.pin.strip() != pin:
        raise HTTPException(401, "PIN incorrecto")
    return {"ok": True, "id": d.id, "nombre": d.nombre}


@router.get("/domiciliario/{dom_id}/pedidos")
def get_pedidos_domiciliario(dom_id: int, pin: str, db: Session = Depends(get_db)):
    """Pedidos activos asignados a este domiciliario (en_cocina o listo)."""
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id, Domiciliario.activo == True).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")
    if not d.pin or d.pin.strip() != pin.strip():
        raise HTTPException(401, "PIN incorrecto")

    orders = db.query(Order).filter(
        Order.domiciliario_id == dom_id,
        Order.tipo == "domicilio",
        Order.estado.in_(["en_cocina", "listo"])
    ).order_by(Order.comanda_numero).all()

    return [
        {
            "id":                o.id,
            "comanda_numero":    o.comanda_numero,
            "cliente_nombre":    o.cliente_nombre or "—",
            "cliente_telefono":  o.cliente_telefono or "",
            "cliente_direccion": o.cliente_direccion or "—",
            "metodo_pago":       o.metodo_pago or "efectivo",
            "estado":            o.estado,
            "total":             float(o.total or 0),
            "valor_domicilio":   float(o.valor_domicilio or 0),
            "observaciones":     o.observaciones or "",
        }
        for o in orders
    ]


@router.post("/domiciliario/{dom_id}/tomar")
def tomar_pedido(dom_id: int, body: TomarBody, db: Session = Depends(get_db)):
    """El domiciliario se auto-asigna a un pedido por número de comanda."""
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id, Domiciliario.activo == True).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")
    if not d.pin or d.pin.strip() != body.pin.strip():
        raise HTTPException(401, "PIN incorrecto")

    orden = db.query(Order).filter(
        Order.comanda_numero == body.comanda_numero,
        Order.tipo == "domicilio",
        Order.estado.in_(["en_cocina", "listo"])
    ).first()
    if not orden:
        raise HTTPException(404, "Pedido no encontrado o no está disponible para domicilio")
    if orden.domiciliario_id and orden.domiciliario_id != dom_id:
        raise HTTPException(409, "Este pedido ya está asignado a otro domiciliario")

    orden.domiciliario_id = dom_id
    orden.estado = "listo"   # "listo" = "En camino" en la página de seguimiento
    db.commit()
    db.refresh(orden)
    return {
        "ok":             True,
        "order_id":       orden.id,
        "comanda_numero": orden.comanda_numero,
        "cliente_nombre": orden.cliente_nombre or "—",
        "total":          float(orden.total or 0),
        "valor_domicilio": float(orden.valor_domicilio or 0),
    }


@router.post("/domiciliario/{dom_id}/entregar/{order_id}")
def confirmar_entrega(dom_id: int, order_id: int, body: EntregarBody, db: Session = Depends(get_db)):
    """El domiciliario confirma la entrega → estado pagado + registra Payment en caja."""
    d = db.query(Domiciliario).filter(Domiciliario.id == dom_id, Domiciliario.activo == True).first()
    if not d:
        raise HTTPException(404, "Domiciliario no encontrado")
    if not d.pin or d.pin.strip() != body.pin.strip():
        raise HTTPException(401, "PIN incorrecto")

    orden = db.query(Order).filter(
        Order.id == order_id,
        Order.domiciliario_id == dom_id,
        Order.tipo == "domicilio",
        Order.estado.in_(["en_cocina", "listo"])
    ).first()
    if not orden:
        raise HTTPException(404, "Pedido no encontrado o ya entregado")

    metodo = body.metodo_pago if body.metodo_pago in ("efectivo", "transferencia", "mixto") else "efectivo"

    # Solo los platos van a caja; el valor_domicilio es pago al repartidor
    monto_platos = float((orden.total or 0) - (orden.valor_domicilio or 0))

    estado_anterior = orden.estado
    orden.estado = "pagado"
    orden.metodo_pago = metodo

    if metodo == "mixto" and body.monto_efectivo is not None:
        met1 = body.mixto_metodo1 or "efectivo"
        met2 = body.mixto_metodo2 or "transferencia"
        monto1 = max(0.0, min(float(body.monto_efectivo), monto_platos))
        monto2 = round(monto_platos - monto1, 2)
        if monto1 > 0:
            db.add(Payment(order_id=orden.id, monto=monto1, metodo=met1, cajero_id=None, caja_id=None))
        if monto2 > 0:
            db.add(Payment(order_id=orden.id, monto=monto2, metodo=met2, cajero_id=None, caja_id=None))
    else:
        db.add(Payment(order_id=orden.id, monto=monto_platos, metodo=metodo, cajero_id=None, caja_id=None))

    # Registrar transición en log de trazabilidad
    db.add(OrderEstadoLog(
        order_id       = orden.id,
        tipo_orden     = "domicilio",
        estado_de      = estado_anterior,
        estado_a       = "pagado",
        usuario_id     = None,
        usuario_nombre = d.nombre,
    ))

    # Descontar inventario
    descontar_inventario(db, orden)

    db.commit()

    return {
        "ok":             True,
        "comanda_numero": orden.comanda_numero,
        "metodo_pago":    metodo,
        "monto_platos":   monto_platos,
        "valor_domicilio": float(orden.valor_domicilio or 0),
    }
