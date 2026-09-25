"""Catálogo de regiones de Colombia (sincronización idempotente).

Regiones naturales de Colombia para la división administrativa del panel.
Se insertan las que falten al arrancar la app (no-testing); no borra las
regiones custom creadas por el superadmin.
"""

REGIONES = [
    {
        "clave": "caribe",
        "nombre": "Región Caribe",
        "descripcion": "Atlántico, Bolívar, Cesar, Córdoba, La Guajira, Magdalena, Sucre, San Andrés.",
        "departamentos": [
            "Atlántico", "Bolívar", "Cesar", "Córdoba", "La Guajira",
            "Magdalena", "Sucre", "San Andrés y Providencia",
        ],
    },
    {
        "clave": "andina",
        "nombre": "Región Andina",
        "descripcion": "Antioquia, Boyacá, Caldas, Cundinamarca, Huila, Norte de Santander, Quindío, Risaralda, Santander, Tolima.",
        "departamentos": [
            "Antioquia", "Boyacá", "Caldas", "Cundinamarca", "Huila",
            "Norte de Santander", "Quindío", "Risaralda", "Santander", "Tolima",
        ],
    },
    {
        "clave": "pacifica",
        "nombre": "Región Pacífica",
        "descripcion": "Cauca, Chocó, Nariño, Valle del Cauca.",
        "departamentos": ["Cauca", "Chocó", "Nariño", "Valle del Cauca"],
    },
    {
        "clave": "orinoquia",
        "nombre": "Región Orinoquía",
        "descripcion": "Arauca, Casanare, Guainía (parcial), Meta, Vichada.",
        "departamentos": ["Arauca", "Casanare", "Meta", "Vichada"],
    },
    {
        "clave": "amazonia",
        "nombre": "Región Amazónica",
        "descripcion": "Amazonas, Caquetá, Guainía, Guaviare, Putumayo, Vaupés.",
        "departamentos": ["Amazonas", "Caquetá", "Guainía", "Guaviare", "Putumayo", "Vaupés"],
    },
]


def sync_regions() -> None:
    """Inserta las regiones del catálogo que falten. Idempotente."""
    from app.extensions import db
    from app.models.region import Region

    existing = {r.clave for r in Region.query.all()}
    for data in REGIONES:
        if data["clave"] not in existing:
            db.session.add(Region(**data))
    db.session.commit()