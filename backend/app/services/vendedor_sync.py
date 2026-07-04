"""Propaga el asesor asignado en el CRM hacia las tablas de facturas/cartera.

Cuando un gerente reasigna un cliente a otro asesor en el CRM, las facturas
y la cartera de ese cliente (identificadas por NIT) deben reflejar el cambio,
para que los reportes por vendedor (resumen-vendedores, cartera) queden
consistentes de inmediato sin esperar al próximo sync de Alegra.
"""
from typing import Optional
from sqlalchemy.orm import Session


def propagar_vendedor_por_nit(db: Session, nit: Optional[str], nuevo_asesor_nombre: Optional[str]) -> int:
    """Actualiza vendedor en CarteraFactura y AlegraFactura para el NIT dado.

    Devuelve el número de filas actualizadas. No hace nada si no hay NIT
    (no hay forma confiable de vincular las facturas al cliente).
    """
    if not nit:
        return 0
    from app.models.cartera import CarteraFactura
    from app.models.alegra_factura import AlegraFactura

    nombre = (nuevo_asesor_nombre or "SIN ASESOR").strip().upper()
    n1 = db.query(CarteraFactura).filter(CarteraFactura.nit == nit).update({"vendedor": nombre})
    n2 = db.query(AlegraFactura).filter(AlegraFactura.nit == nit).update({"vendedor": nombre})
    db.commit()
    return n1 + n2
