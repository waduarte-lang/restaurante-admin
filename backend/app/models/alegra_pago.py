from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.database import Base


class AlegraPago(Base):
    __tablename__ = "alegra_pagos"

    id = Column(Integer, primary_key=True, index=True)
    alegra_id = Column(String(20), unique=True, index=True)
    num_recibo = Column(String(30))          # RCATH91, RCINI961
    fecha_pago = Column(Date, index=True)
    tipo = Column(String(10), default="in") # in = ingreso
    metodo_pago = Column(String(30))        # transfer, cash, check
    monto = Column(Numeric(18, 2), default=0)
    anotacion = Column(String(200))
    banco = Column(String(100))

    # Cliente
    alegra_cliente_id = Column(String(20))
    nit = Column(String(30), index=True)
    nombre_cliente = Column(String(200))

    # Facturas aplicadas (JSON string)  ["FE10001","FE10002"]
    facturas_aplicadas = Column(Text)
    # Si es anticipo (sin factura específica)
    es_anticipo = Column(Boolean, default=False)

    fecha_sync = Column(DateTime, server_default=func.now())
