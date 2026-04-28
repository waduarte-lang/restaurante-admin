from sqlalchemy import Column, Integer, String
from app.database import Base


class Table(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, unique=True, nullable=False)
    capacidad = Column(Integer, default=4)
    estado = Column(String(20), default="libre")  # libre, ocupada, esperando_pago
    zona = Column(String(50), default="salon")
