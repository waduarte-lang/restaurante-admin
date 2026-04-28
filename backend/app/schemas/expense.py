from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class ExpenseCreate(BaseModel):
    concepto: str
    monto: float
    categoria: str = "general"
    fecha: date


class ExpenseUpdate(BaseModel):
    concepto: Optional[str] = None
    monto: Optional[float] = None
    categoria: Optional[str] = None
    fecha: Optional[date] = None


class ExpenseOut(BaseModel):
    id: int
    concepto: str
    monto: float
    categoria: str
    fecha: date
    created_at: datetime

    class Config:
        from_attributes = True
