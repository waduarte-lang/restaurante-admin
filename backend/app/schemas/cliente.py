from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClienteIn(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    observaciones: Optional[str] = None


class ClienteOut(ClienteIn):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
