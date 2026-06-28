from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Tarea(Base):
    __tablename__ = "crm_tareas"

    id = Column(Integer, primary_key=True, index=True)
    asesor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("crm_clientes.id"), nullable=True)
    titulo = Column(String(200), nullable=False)
    actividades = Column(Text, nullable=True)       # JSON array de strings
    duracion_minutos = Column(Integer, default=60)
    que_llevar = Column(Text, nullable=True)
    fecha_inicio = Column(DateTime(timezone=True), nullable=True)  # nullable = sin fecha aún
    ejecutado = Column(Boolean, default=False)
    etapa = Column(String(30), default="prospecto", nullable=False)
    # prospecto | contactado | visita_agendada | propuesta | negociacion | cumplido
    color = Column(String(7), default="#3B82F6")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    asesor = relationship("User", foreign_keys=[asesor_id])
    cliente = relationship("CRMCliente", foreign_keys=[cliente_id])
