"""Saca el logo y el banner de la galería (`negocios.imagenes`).

Las subidas antiguas agregaban el logo/banner también a `imagenes`, así que
aparecían duplicados en el portafolio del negocio y en el perfil público.
Este script es idempotente: deja en `imagenes` solo las fotos de galería.

Uso (dentro del contenedor backend):
    PYTHONPATH=/app python scripts/clean_business_gallery.py
"""

from app import create_app
from app.extensions import db
from app.models.negocio import Negocio


def clean() -> None:
    app = create_app()
    with app.app_context():
        negocios = Negocio.query.filter(Negocio.imagenes.isnot(None)).all()
        revisados = 0
        cambiados = 0

        for negocio in negocios:
            revisados += 1
            actuales = list(negocio.imagenes or [])
            excluidas = {negocio.logo_url, negocio.banner_url} - {None}
            nuevas = [url for url in actuales if url not in excluidas]
            if nuevas != actuales:
                negocio.imagenes = nuevas
                cambiados += 1

        db.session.commit()
        print(f"Negocios revisados: {revisados}. Galerías limpias: {cambiados}.")


if __name__ == "__main__":
    clean()
