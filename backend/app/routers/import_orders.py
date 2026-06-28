"""
Carga Histórica de Comandas
POST /api/admin/import/comanda  — Solo administradores
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import date, datetime, time as time_type
from pydantic import BaseModel
from app.database import get_db
from app.models.order import Order, OrderItem
from app.models.menu import MenuItem
from app.models.payment import Payment
from app.models.table import Table
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/admin/import", tags=["import"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ImportItemIn(BaseModel):
    item_id: int
    cantidad: int = 1
    precio_unitario: float
    nota: Optional[str] = None          # Ej: "Sopa: Ajiaco | Seco: Pollo al Horno"

class ImportComandaIn(BaseModel):
    fecha: date
    hora: str = "12:00"
    tipo: str = "mesa"                   # "mesa" | "domicilio"
    mesa_numero: Optional[int] = None    # número de mesa (se busca en la tabla; si no existe, se anota)
    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_direccion: Optional[str] = None
    domiciliario_id: Optional[int] = None
    observaciones: Optional[str] = None
    items: List[ImportItemIn]
    metodo_pago: str = "efectivo"
    valor_domicilio: float = 0.0
    total_override: Optional[float] = None  # Si se envía, reemplaza el total calculado

class ImportComandaOut(BaseModel):
    ok: bool
    order_id: int
    comanda_numero: int
    total: float
    aviso: Optional[str] = None          # Ej: "Mesa 99 no encontrada, se registró sin mesa_id"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_comanda_global(db: Session) -> int:
    from sqlalchemy import func
    last = db.query(func.max(Order.comanda_numero)).scalar()
    return (last or 0) + 1


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/comanda", response_model=ImportComandaOut)
def import_comanda(
    data: ImportComandaIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")

    if not data.items:
        raise HTTPException(status_code=400, detail="La comanda debe tener al menos un ítem")

    # Validar items
    for it in data.items:
        if not db.query(MenuItem).filter(MenuItem.id == it.item_id).first():
            raise HTTPException(status_code=404, detail=f"Plato con id {it.item_id} no encontrado en el menú")

    # Resolver mesa — sin error si no existe, se registra el aviso
    aviso: Optional[str] = None
    mesa_id = None
    obs_extra = ""

    if data.tipo == "mesa":
        if not data.mesa_numero:
            raise HTTPException(status_code=400, detail="Indica el número de mesa")
        table = db.query(Table).filter(Table.numero == data.mesa_numero).first()
        if table:
            mesa_id = table.id
        else:
            # Mesa no existe en el sistema: se registra igualmente sin FK
            aviso = f"Mesa {data.mesa_numero} no está registrada en el sistema; la comanda se guardó sin asignación de mesa."
            obs_extra = f"[Mesa {data.mesa_numero}] "

    elif data.tipo == "domicilio":
        if not data.cliente_nombre:
            raise HTTPException(status_code=400, detail="Nombre del cliente requerido para domicilio")

    # Observaciones combinadas
    obs_final = (obs_extra + (data.observaciones or "")).strip() or None

    # Número de comanda para esa fecha
    comanda_num = _next_comanda_global(db)

    # Crear orden
    order = Order(
        comanda_numero=comanda_num,
        comanda_fecha=data.fecha,
        tipo=data.tipo,
        mesa_id=mesa_id,
        mesero_id=current_user.id,
        estado="pagado",
        observaciones=obs_final,
        cliente_nombre=data.cliente_nombre,
        cliente_telefono=data.cliente_telefono,
        cliente_direccion=data.cliente_direccion,
        domiciliario_id=data.domiciliario_id if data.tipo == "domicilio" else None,
        valor_domicilio=data.valor_domicilio if data.tipo == "domicilio" else 0.0,
        total=0.0,
    )
    db.add(order)
    db.flush()

    # Insertar ítems
    subtotal = 0.0
    for it in data.items:
        oi = OrderItem(
            order_id=order.id,
            item_id=it.item_id,
            cantidad=it.cantidad,
            precio_unitario=it.precio_unitario,
            nota=it.nota,
            estado="listo",
        )
        db.add(oi)
        subtotal += it.cantidad * it.precio_unitario

    total_calculado = subtotal + (data.valor_domicilio if data.tipo == "domicilio" else 0.0)
    order.total = data.total_override if data.total_override is not None else total_calculado
    db.flush()

    # Pago
    payment = Payment(
        order_id=order.id,
        monto=order.total,
        metodo=data.metodo_pago,
        cajero_id=current_user.id,
    )
    db.add(payment)
    db.flush()

    # Retrofechar timestamps
    try:
        h, m = data.hora.split(":")
        dt = datetime.combine(data.fecha, time_type(int(h), int(m)))
    except Exception:
        dt = datetime.combine(data.fecha, time_type(12, 0))

    dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    db.execute(text(f"UPDATE orders   SET created_at = '{dt_str}' WHERE id = {order.id}"))
    db.execute(text(f"UPDATE payments SET created_at = '{dt_str}' WHERE id = {payment.id}"))

    db.commit()

    return ImportComandaOut(
        ok=True,
        order_id=order.id,
        comanda_numero=comanda_num,
        total=order.total,
        aviso=aviso,
    )
