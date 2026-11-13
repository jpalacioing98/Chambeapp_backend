"""Seed idempotente de tarifas de cobro en monedas."""

from app.extensions import db
from app.models.cobro import TARIFAS_DEFAULT, TarifaCobro


def sync_tarifas_cobro() -> int:
    """Crea las claves de tarifa que falten (no pisa valores existentes)."""
    creadas = 0
    existentes = {t.clave for t in TarifaCobro.query.all()}
    for clave, valor in TARIFAS_DEFAULT.items():
        if clave in existentes:
            continue
        db.session.add(TarifaCobro(clave=clave, valor=float(valor)))
        creadas += 1
    if creadas:
        db.session.commit()
    return creadas
