from sqlalchemy import Column, Integer, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Visita(Base):
    __tablename__ = "crm_visitas"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("crm_clientes.id"), nullable=False)
    asesor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    fecha_visita = Column(DateTime(timezone=True), nullable=False)
    acuerdos = Column(Text, nullable=True)
    muestras_entregadas = Column(Text, nullable=True)
    proxima_visita = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cliente = relationship("CRMCliente", back_populates="visitas")
    asesor = relationship("User", foreign_keys=[asesor_id])
