from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base


class AlegraFactura(Base):
    __tablename__ = "alegra_facturas"

    id = Column(Integer, primary_key=True, index=True)
    alegra_id = Column(String(20), unique=True, index=True)
    num_factura = Column(String(20), index=True)
    fecha_factura = Column(Date, index=True)
    fecha_vencimiento = Column(Date)
    status = Column(String(20))          # open | closed | void
    termino_pago = Column(String(50))    # "30 días" | "De contado"

    alegra_cliente_id = Column(String(20))
    nit = Column(String(30), index=True)
    nombre_cliente = Column(String(200))

    subtotal = Column(Numeric(18, 2), default=0)
    descuento = Column(Numeric(18, 2), default=0)
    iva = Column(Numeric(18, 2), default=0)
    total = Column(Numeric(18, 2), default=0)
    total_pagado = Column(Numeric(18, 2), default=0)
    saldo = Column(Numeric(18, 2), default=0)

    vendedor = Column(String(100))

    fecha_sync = Column(DateTime, server_default=func.now(), onupdate=func.now())
