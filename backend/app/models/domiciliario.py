from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Domiciliario(Base):
    __tablename__ = "domiciliarios"

    id         = Column(Integer, primary_key=True, index=True)
    nombre     = Column(String(100), nullable=False)
    telefono   = Column(String(30))
    pin        = Column(String(10), nullable=True)   # PIN de acceso a la app del domiciliario
    activo     = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
