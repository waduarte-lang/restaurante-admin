from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    usuario_nombre = Column(String(100))
    accion = Column(String(100))       # editar_item | agregar_item | eliminar_item
    entidad = Column(String(50), default="comanda")
    entidad_id = Column(Integer)       # order_id
    detalle = Column(Text)             # JSON string con antes/después

    usuario = relationship("User")
