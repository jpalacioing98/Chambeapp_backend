"""Fotos de perfil simuladas — descarga de i.pravatar.cc al bucket público.

Contexto: el seed histórico asignaba `foto_perfil` a URLs de
`https://sim.chambeapp.co/...`, un dominio que no existe en DNS. El
navegador pintaba la imagen rota y, como el `alt` es el nombre del
usuario, el avatar mostraba el NOMBRE en lugar de una foto.

Este módulo descarga fotos reales de i.pravatar.cc y las sube al bucket
público de avatares (MinIO), de modo que el seed queda autocontenido y
las fotos siguen funcionando aunque no haya salida a internet en runtime.

Uso:
    from app.services.avatar_seed import upload_seed_avatar
    profile.foto_perfil = upload_seed_avatar("sim/pds/001", index=1)
"""

import logging
import urllib.error
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PRAVATAR_URL = "https://i.pravatar.cc/{size}?img={index}"
PRAVATAR_SIZE = 300
# i.pravatar.cc rechaza el User-Agent por defecto de urllib (403).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 20
# Catálogo de caras distintas del servicio; se recicla con módulo.
DISTINCT_FACES = 70

# Caché en memoria: la misma foto no se descarga dos veces en una corrida.
_CACHE: Dict[int, bytes] = {}


def face_index(index: int) -> int:
    """Normaliza un índice al catálogo de i.pravatar.cc (1..70)."""
    return (index % DISTINCT_FACES) + 1


def download_avatar(index: int) -> Optional[bytes]:
    """Descarga la foto de i.pravatar.cc. Devuelve None si falla."""
    face = face_index(index)
    if face in _CACHE:
        return _CACHE[face]

    url = PRAVATAR_URL.format(size=PRAVATAR_SIZE, index=face)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("No se pudo descargar la foto de avatar %s: %s", face, exc)
        return None

    if not data:
        logger.warning("La foto de avatar %s vino vacía.", face)
        return None

    _CACHE[face] = data
    return data


def upload_seed_avatar(folder: str, index: int) -> Optional[str]:
    """Descarga la foto y la sube al bucket público. Devuelve la URL o None."""
    from app.services.storage import storage

    if storage is None:
        logger.warning("MinIO no disponible: se omite la foto de avatar %s.", folder)
        return None

    data = download_avatar(index)
    if data is None:
        return None

    try:
        return storage.upload_public_avatar(data, folder, "perfil")
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo subir la foto de avatar %s: %s", folder, exc)
        return None
