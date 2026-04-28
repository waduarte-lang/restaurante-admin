from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.menu import MenuItem
from app.models.table import Table
from app.schemas.order import OrderCreate, OrderUpdate, OrderOut, OrderItemOut
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _calc_total(items):
    return sum(i.precio_unitario * i.cantidad for i in items)


@router.get("", response_model=List[OrderOut])
def list_orders(estado: Optional[str] = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Order).options(joinedload(Order.items))
    if estado:
        q = q.filter(Order.estado == estado)
    orders = q.order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        o_dict = {c.name: getattr(o, c.name) for c in o.__table__.columns}
        o_dict["items"] = [
            {**{c.name: getattr(i, c.name) for c in i.__table__.columns},
             "item_nombre": i.item.nombre if i.item else None}
            for i in o.items
        ]
        result.append(o_dict)
    return result


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    o_dict = {c.name: getattr(order, c.name) for c in order.__table__.columns}
    o_dict["items"] = [
        {**{c.name: getattr(i, c.name) for c in i.__table__.columns},
         "item_nombre": i.item.nombre if i.item else None}
        for i in order.items
    ]
    return o_dict


@router.post("", response_model=OrderOut)
def create_order(data: OrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    table = db.query(Table).filter(Table.id == data.mesa_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")
    order = Order(mesa_id=data.mesa_id, mesero_id=current_user.id, observaciones=data.observaciones)
    db.add(order)
    db.flush()
    for item_data in data.items:
        menu_item = db.query(MenuItem).filter(MenuItem.id == item_data.item_id, MenuItem.activo == True).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Item {item_data.item_id} no encontrado")
        oi = OrderItem(order_id=order.id, item_id=menu_item.id, cantidad=item_data.cantidad,
                       precio_unitario=menu_item.precio, nota=item_data.nota)
        db.add(oi)
    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items)
    table.estado = "ocupada"
    db.commit()
    db.refresh(order)
    o_dict = {c.name: getattr(order, c.name) for c in order.__table__.columns}
    o_dict["items"] = [
        {**{c.name: getattr(i, c.name) for c in i.__table__.columns},
         "item_nombre": i.item.nombre if i.item else None}
        for i in order.items
    ]
    return o_dict


@router.put("/{order_id}", response_model=OrderOut)
def update_order(order_id: int, data: OrderUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(order, field, value)
    if data.estado == "pagado":
        table = db.query(Table).filter(Table.id == order.mesa_id).first()
        if table:
            table.estado = "libre"
    db.commit()
    db.refresh(order)
    o_dict = {c.name: getattr(order, c.name) for c in order.__table__.columns}
    o_dict["items"] = [
        {**{c.name: getattr(i, c.name) for c in i.__table__.columns},
         "item_nombre": i.item.nombre if i.item else None}
        for i in order.items
    ]
    return o_dict


@router.post("/{order_id}/items")
def add_item_to_order(order_id: int, item_id: int, cantidad: int = 1, nota: str = None,
                      db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.estado in ("pagado", "cancelado"):
        raise HTTPException(status_code=400, detail="Pedido no disponible para modificar")
    menu_item = db.query(MenuItem).filter(MenuItem.id == item_id, MenuItem.activo == True).first()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    oi = OrderItem(order_id=order.id, item_id=menu_item.id, cantidad=cantidad,
                   precio_unitario=menu_item.precio, nota=nota)
    db.add(oi)
    db.flush()
    db.refresh(order)
    order.total = _calc_total(order.items)
    db.commit()
    return {"ok": True, "total": order.total}
