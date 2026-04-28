from sqlalchemy import Column, Integer, Float, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    concepto = Column(String(200), nullable=False)
    monto = Column(Float, nullable=False)
    categoria = Column(String(50), default="general")  # personal, servicios, insumos, general
    fecha = Column(Date, nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    usuario = relationship("User")
