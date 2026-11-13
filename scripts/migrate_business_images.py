"""Migra las imágenes de negocios del bucket privado al bucket público.

Uso (dentro del contenedor backend):
    python scripts/migrate_business_images.py

Copia `portfolio/<negocio_id>/...` del bucket principal a
`negocios/<negocio_id>/...` en el bucket público y reescribe las URLs
guardadas (`logo_url`, `banner_url`, `imagenes`) para que el navegador
pueda cargarlas con `S3_PUBLIC_ENDPOINT`.
"""

from app import create_app
from app.extensions import db
from app.models.negocio import Negocio
from app.services.storage import storage


def _old_urls(key: str) -> set[str]:
    """Variantes de URL con las que pudo guardarse un objeto privado."""
    candidates = {
        f"{storage.S3_ENDPOINT}/{storage.S3_BUCKET}/{key}",
        f"http://minio:9000/{storage.S3_BUCKET}/{key}",
        f"http://localhost:9000/{storage.S3_BUCKET}/{key}",
        f"/minio/{storage.S3_BUCKET}/{key}",
    }
    return candidates


def migrate() -> None:
    if storage is None:
        print("StorageService no disponible: revisa MinIO/S3.")
        return

    app = create_app()
    with app.app_context():
        business_ids = {int(row[0]) for row in db.session.query(Negocio.id).all()}
        if not business_ids:
            print("No hay negocios.")
            return

        paginator = storage.client.get_paginator("list_objects_v2")
        movidos = 0
        actualizados = 0

        for page in paginator.paginate(
            Bucket=storage.S3_BUCKET, Prefix="portfolio/"
        ):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                parts = key.split("/")
                if len(parts) < 3:
                    continue
                try:
                    negocio_id = int(parts[1])
                except ValueError:
                    continue
                if negocio_id not in business_ids:
                    continue

                filename = parts[-1]
                new_key = f"negocios/{negocio_id}/{filename}"
                storage.client.copy_object(
                    Bucket=storage.S3_BUSINESS_BUCKET,
                    CopySource={"Bucket": storage.S3_BUCKET, "Key": key},
                    Key=new_key,
                )
                movidos += 1

                old = _old_urls(key)
                new_url = (
                    f"{storage.S3_PUBLIC_ENDPOINT}/"
                    f"{storage.S3_BUSINESS_BUCKET}/{new_key}"
                )

                negocio = db.session.get(Negocio, negocio_id)
                if negocio is None:
                    continue
                changed = False
                if negocio.logo_url in old:
                    negocio.logo_url = new_url
                    changed = True
                if negocio.banner_url in old:
                    negocio.banner_url = new_url
                    changed = True
                if negocio.imagenes:
                    nuevas = [
                        new_url if url in old else url
                        for url in negocio.imagenes
                    ]
                    if nuevas != negocio.imagenes:
                        negocio.imagenes = nuevas
                        changed = True
                if changed:
                    actualizados += 1

        db.session.commit()
        print(
            f"Objetos copiados: {movidos}. Negocios actualizados: {actualizados}."
        )


if __name__ == "__main__":
    migrate()
