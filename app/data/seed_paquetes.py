"""Seed idempotente de paquetes de monedas por defecto.

Los paquetes son administrables por el superadmin; este seed solo cubre el
caso de una base nueva (o creada con `db.create_all()` sin migraciones).
"""

from app.extensions import db
from app.models.wallet import PaqueteMonedas

PAQUETES_DEFAULT = (
    {
        "nombre": "Básico",
        "descripcion": "Para empezar a destacar tus publicaciones.",
        "cantidad": 50,
        "bonus": 0,
        "precio_cop": 5000,
        "orden": 1,
    },
    {
        "nombre": "Estándar",
        "descripcion": "El más elegido: monedas extra de regalo.",
        "cantidad": 150,
        "bonus": 15,
        "precio_cop": 15000,
        "orden": 2,
    },
    {
        "nombre": "Premium",
        "descripcion": "Máximo ahorro por moneda para negocios activos.",
        "cantidad": 350,
        "bonus": 50,
        "precio_cop": 30000,
        "orden": 3,
    },
)


def sync_paquetes_monedas() -> int:
    """Inserta los paquetes base si la tabla está vacía."""
    if PaqueteMonedas.query.count() > 0:
        return 0
    for data in PAQUETES_DEFAULT:
        db.session.add(PaqueteMonedas(**data))
    db.session.commit()
    return len(PAQUETES_DEFAULT)
