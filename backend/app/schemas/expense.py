from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class ExpenseCreate(BaseModel):
    concepto: str
    monto: float
    categoria: str = "general"
    fecha: date
    metodo_pago: str = "efectivo"    # efectivo | tarjeta | transferencia
    caja_id: Optional[int] = None


class ExpenseUpdate(BaseModel):
    concepto: Optional[str] = None
    monto: Optional[float] = None
    categoria: Optional[str] = None
    fecha: Optional[date] = None
    metodo_pago: Optional[str] = None


class ExpenseOut(BaseModel):
    id: int
    concepto: str
    monto: float
    categoria: str
    fecha: date
    metodo_pago: str = "efectivo"
    caja_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
