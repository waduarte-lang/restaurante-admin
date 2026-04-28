from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PaymentCreate(BaseModel):
    order_id: int
    monto: float
    metodo: str = "efectivo"
    caja_id: Optional[int] = None


class PaymentOut(BaseModel):
    id: int
    order_id: int
    monto: float
    metodo: str
    cajero_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class CashRegisterCreate(BaseModel):
    fondo_inicial: float = 0.0


class CashRegisterClose(BaseModel):
    total_final: float


class CashRegisterOut(BaseModel):
    id: int
    cajero_id: int
    fondo_inicial: float
    total_final: Optional[float]
    estado: str
    apertura: datetime
    cierre: Optional[datetime]

    class Config:
        from_attributes = True
