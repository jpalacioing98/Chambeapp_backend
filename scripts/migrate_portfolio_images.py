"""Migra las fotos del portafolio del PDS al bucket público.

Uso (dentro del contenedor backend):
    PYTHONPATH=/app python scripts/migrate_portfolio_images.py

Copia cada objeto referenciado por `portfolio_items` desde el bucket
privado a `chambeapp-portafolio-publico` y reescribe `url`, `antes`,
`despues` y `galeria` con la URL pública (`S3_PUBLIC_ENDPOINT`).
"""

from app import create_app
from app.extensions import db
from app.models.portfolio import PortfolioItem
from app.services.storage import storage


def _public_url(key: str) -> str:
    return (
        f"{storage.S3_PUBLIC_ENDPOINT}/{storage.S3_PORTFOLIO_BUCKET}/{key}"
    )


def _key_from_url(url: str) -> str | None:
    """Extrae la key de una URL del bucket privado (cualquier host)."""
    marker = f"/{storage.S3_BUCKET}/"
    if marker not in url:
        return None
    return url.split(marker, 1)[1] or None


def _migrar_url(url: str | None) -> tuple[str | None, bool]:
    if not url:
        return url, False
    key = _key_from_url(url)
    if not key:
        return url, False
    try:
        storage.client.copy_object(
            Bucket=storage.S3_PORTFOLIO_BUCKET,
            CopySource={"Bucket": storage.S3_BUCKET, "Key": key},
            Key=key,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  no se pudo copiar {key}: {exc}")
        return url, False
    return _public_url(key), True


def migrate() -> None:
    if storage is None:
        print("StorageService no disponible: revisa MinIO/S3.")
        return

    app = create_app()
    with app.app_context():
        items = PortfolioItem.query.all()
        cambiados = 0
        for item in items:
            changed = False
            if item.tipo == "foto" and item.url:
                nueva, ok = _migrar_url(item.url)
                if ok:
                    item.url = nueva
                    changed = True

            for campo in ("antes", "despues", "galeria"):
                actual = getattr(item, campo) or []
                nuevas = []
                for url in actual:
                    nueva, ok = _migrar_url(url)
                    nuevas.append(nueva)
                    changed = changed or ok
                if nuevas != actual:
                    setattr(item, campo, nuevas)

            if changed:
                cambiados += 1

        db.session.commit()
        print(f"Items de portafolio revisados: {len(items)}. Actualizados: {cambiados}.")


if __name__ == "__main__":
    migrate()
