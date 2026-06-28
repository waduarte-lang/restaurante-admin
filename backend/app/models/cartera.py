from sqlalchemy import Column, Integer, String, Date, Numeric, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class CarteraFactura(Base):
    __tablename__ = "cartera_facturas"

    id = Column(Integer, primary_key=True, index=True)
    nit = Column(String(20), index=True)
    nombre_cliente = Column(String(200))
    vendedor = Column(String(100), nullable=True)
    num_factura = Column(String(50))
    fecha_factura = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=True)
    valor_pendiente = Column(Numeric(15, 2))
    activo = Column(Boolean, default=True)
    importado_at = Column(DateTime, server_default=func.now())
