from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.payment import Payment, CashRegister
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
                         current_user: User = Depends(require_roles("admin", "cajero"))):
    reg = db.query(CashRegister).filter(
        CashRegister.cajero_id == current_user.id,
        CashRegister.estado == "abierta"
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail="No hay caja abierta")
    return reg


@router.post("/cash-registers/open", response_model=CashRegisterOut)
def open_register(data: CashRegisterCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(require_roles("admin", "cajero"))):
    existing = db.query(CashRegister).filter(
        CashRegister.cajero_id == current_user.id,
        CashRegister.estado == "abierta"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya tienes una caja abierta")
    reg = CashRegister(cajero_id=current_user.id, fondo_inicial=data.fondo_inicial)
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg


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
