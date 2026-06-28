from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.payment import Payment
from app.models.cash_register import CashRegister
from app.models.order import Order
from app.schemas.payment import PaymentCreate, PaymentOut, CashRegisterCreate, CashRegisterClose, CashRegisterOut
from app.auth.dependencies import get_current_user, require_roles
from app.models.user import User

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("", response_model=PaymentOut)
def register_payment(data: PaymentCreate, db: Session = Depends(get_db),
                      current_user: User = Depends(require_roles("admin", "cajero"))):
    order = db.query(Order).filter(Order.id == data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    payment = Payment(order_id=data.order_id, monto=data.monto, metodo=data.metodo,
                      cajero_id=current_user.id, caja_id=data.caja_id)
    db.add(payment)
    order.estado = "pagado"
    db.commit()
    db.refresh(payment)
    return payment


@router.get("/cash-registers", response_model=List[CashRegisterOut])
def list_cash_registers(db: Session = Depends(get_db), _=Depends(require_roles("admin", "cajero"))):
    return db.query(CashRegister).order_by(CashRegister.apertura.desc()).limit(30).all()


@router.get("/cash-registers/active", response_model=CashRegisterOut)
def get_active_register(db: Session = Depends(get_db),
                         _: User = Depends(require_roles("admin", "cajero"))):
    # Caja compartida: cualquier cajero/admin ve la caja activa del turno
    reg = db.query(CashRegister).filter(
        CashRegister.estado == "abierta"
    ).order_by(CashRegister.apertura.desc()).first()
    if not reg:
        raise HTTPException(status_code=404, detail="No hay caja abierta")
    return reg


@router.post("/cash-registers/open", response_model=CashRegisterOut)
def open_register(data: CashRegisterCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(require_roles("admin", "cajero"))):
    # Solo puede haber UNA caja abierta a la vez en todo el sistema
    existing = db.query(CashRegister).filter(
        CashRegister.estado == "abierta"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya hay una caja abierta en este turno")
    reg = CashRegister(cajero_id=current_user.id, fondo_inicial=data.fondo_inicial)
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg


@router.patch("/cash-registers/{reg_id}/fondo")
def update_fondo(reg_id: int, data: dict, db: Session = Depends(get_db),
                 _=Depends(require_roles("admin", "cajero"))):
    reg = db.query(CashRegister).filter(CashRegister.id == reg_id, CashRegister.estado == "abierta").first()
    if not reg:
        raise HTTPException(status_code=404, detail="Caja no encontrada o ya cerrada")
    reg.fondo_inicial = float(data.get("fondo_inicial", reg.fondo_inicial))
    db.commit()
    db.refresh(reg)
    return {"ok": True, "fondo_inicial": reg.fondo_inicial}


@router.post("/cash-registers/{reg_id}/close", response_model=CashRegisterOut)
def close_register(reg_id: int, data: CashRegisterClose, db: Session = Depends(get_db),
                    _=Depends(require_roles("admin", "cajero"))):
    from datetime import datetime
    reg = db.query(CashRegister).filter(CashRegister.id == reg_id, CashRegister.estado == "abierta").first()
    if not reg:
        raise HTTPException(status_code=404, detail="Caja no encontrada o ya cerrada")
    reg.total_final = data.total_final
    reg.estado = "cerrada"
    reg.cierre = datetime.utcnow()
    db.commit()
    db.refresh(reg)
    return reg


@router.get("/cash-registers/{reg_id}/detail")
def get_register_detail(
    reg_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero")),
):
    """Detalle completo de un turno: comandas, pagos, gastos y cuadres."""
    import json
    from app.models.cash_count import CashCount
    from app.models.expense import Expense
    from datetime import date as date_type

    reg = db.query(CashRegister).filter(CashRegister.id == reg_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Caja no encontrada")

    # Pagos de este turno
    payments = db.query(Payment).filter(Payment.caja_id == reg_id).all()
    ventas_efectivo      = sum(p.monto for p in payments if p.metodo == "efectivo")
    ventas_tarjeta       = sum(p.monto for p in payments if p.metodo == "tarjeta")
    ventas_transferencia = sum(p.monto for p in payments if p.metodo == "transferencia")
    total_ventas         = ventas_efectivo + ventas_tarjeta + ventas_transferencia

    payment_map: dict = {}
    for p in payments:
        payment_map.setdefault(p.order_id, []).append({"metodo": p.metodo, "monto": p.monto})

    # Comandas vinculadas al turno
    orders = db.query(Order).filter(Order.caja_id == reg_id).order_by(Order.id).all()

    # Gastos del día de apertura
    apertura_date = reg.apertura.date() if reg.apertura else None
    cierre_date   = reg.cierre.date()   if reg.cierre   else date_type.today()
    gastos_q = []
    total_gastos = 0.0
    if apertura_date:
        gastos_q = db.query(Expense).filter(
            Expense.fecha >= apertura_date,
            Expense.fecha <= cierre_date,
        ).all()
        total_gastos = sum(g.monto for g in gastos_q)

    # Cuadres de este turno
    cuadres = []
    for c in db.query(CashCount).filter(CashCount.caja_id == reg_id).order_by(CashCount.created_at.desc()).all():
        cuadres.append({
            "id": c.id,
            "total_contado": c.total_contado,
            "total_esperado": c.total_esperado,
            "diferencia": c.diferencia,
            "observaciones": c.observaciones,
            "denominaciones": json.loads(c.denominaciones or "{}"),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    orders_list = []
    for o in orders:
        orders_list.append({
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
        })

    return {
        "caja": {
            "id": reg.id,
            "cajero": reg.cajero.nombre if reg.cajero else "—",
            "fondo_inicial": reg.fondo_inicial,
            "total_final": reg.total_final,
            "estado": reg.estado,
            "apertura": reg.apertura.isoformat() if reg.apertura else None,
            "cierre": reg.cierre.isoformat() if reg.cierre else None,
        },
        "resumen": {
            "total_ventas": round(total_ventas, 2),
            "ventas_efectivo": round(ventas_efectivo, 2),
            "ventas_tarjeta": round(ventas_tarjeta, 2),
            "ventas_transferencia": round(ventas_transferencia, 2),
            "total_pedidos": len(orders),
            "pedidos_pagados": sum(1 for o in orders if o.estado == "pagado"),
            "total_gastos": round(total_gastos, 2),
            "utilidad": round(total_ventas - total_gastos, 2),
        },
        "gastos": [
            {"id": g.id, "concepto": g.concepto, "monto": g.monto, "categoria": g.categoria, "fecha": str(g.fecha)}
            for g in gastos_q
        ],
        "cuadres": cuadres,
        "comandas": orders_list,
    }
