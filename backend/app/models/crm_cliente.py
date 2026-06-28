from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CRMCliente(Base):
    __tablename__ = "crm_clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    nit = Column(String(20), nullable=True, index=True)
    telefono = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    ciudad = Column(String(100), nullable=True)
    direccion = Column(String(300), nullable=True)
    asesor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    datha_customer_id = Column(Integer, nullable=True, index=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    asesor = relationship("User", foreign_keys=[asesor_id])
    visitas = relationship("Visita", back_populates="cliente", order_by="Visita.fecha_visita.desc()")
    eventos = relationship("CalendarioEvento", back_populates="cliente")
