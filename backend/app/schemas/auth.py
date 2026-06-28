from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserCreate(BaseModel):
    nombre: str
    username: str
    password: str
    rol: str = "mesero"


class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    username: Optional[str] = None
    rol: Optional[str] = None
    activo: Optional[bool] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    nombre: str
    username: str
    rol: str
    activo: bool

    class Config:
        from_attributes = True
