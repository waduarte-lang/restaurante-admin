from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class TipoEvento(str, enum.Enum):
    visita = "visita"
    entrega = "entrega"
    pendiente = "pendiente"


class CalendarioEvento(Base):
    __tablename__ = "crm_calendario_eventos"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("crm_clientes.id"), nullable=True)
    asesor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tipo = Column(String(20), nullable=False, default="pendiente")
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    fecha_inicio = Column(DateTime(timezone=True), nullable=False)
    completado = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cliente = relationship("CRMCliente", back_populates="eventos")
    asesor = relationship("User", foreign_keys=[asesor_id])
