from pydantic import BaseModel
from typing import Optional


class TableCreate(BaseModel):
    numero: int
    capacidad: int = 4
    zona: str = "salon"


class TableUpdate(BaseModel):
    numero: Optional[int] = None
    capacidad: Optional[int] = None
    zona: Optional[str] = None
    estado: Optional[str] = None


class TableOut(BaseModel):
    id: int
    numero: int
    capacidad: int
    estado: str
    zona: str

    class Config:
        from_attributes = True
