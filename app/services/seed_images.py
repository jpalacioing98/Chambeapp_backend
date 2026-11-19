"""Imágenes del seed: fotos reales (picsum) + fallback generado con PIL.

El seed histórico usaba URLs de `https://sim.chambeapp.co/...`, un dominio que
no existe: el navegador mostraba imágenes rotas. Este módulo descarga fotos
reales, las sube a MinIO (bucket público) y, si no hay internet/MinIO, genera
placeholders PNG deterministas. También genera PDFs KYC en base64.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import urllib.error
import urllib.request
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

PICSUM_URL = "https://picsum.photos/seed/{seed}/{w}/{h}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 8

_DOWNLOAD_CACHE: dict[str, Optional[bytes]] = {}
_KYC_PDF_CACHE: dict[str, str] = {}
_PICSUM_DISABLED = False

_PALETTE = [
    (214, 69, 65),    # coral
    (32, 120, 110),   # teal
    (58, 92, 160),    # azul
    (176, 110, 48),   # mostaza
    (110, 70, 140),   # violeta
    (54, 130, 70),    # verde
]


def _hash(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16)


def _color(seed: str) -> tuple[int, int, int]:
    return _PALETTE[_hash(seed) % len(_PALETTE)]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _download(url: str) -> Optional[bytes]:
    if url in _DOWNLOAD_CACHE:
        return _DOWNLOAD_CACHE[url]
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("No se pudo descargar imagen %s: %s", url, exc)
        data = None
    if not data:
        data = None
    _DOWNLOAD_CACHE[url] = data
    return data


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        probe = f"{current} {word}".strip()
        if draw.textlength(probe, font=font) <= max_width or not current:
            current = probe
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:3]


def _placeholder(text: str, size: tuple[int, int], seed: str) -> bytes:
    """PNG con degradado y texto: se usa si picsum/MinIO no están disponibles."""
    width, height = size
    base = _color(seed)
    img = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(img)
    # Degradado vertical suave.
    r0, g0, b0 = base
    for y in range(height):
        factor = 0.55 + 0.65 * (y / max(1, height - 1))
        draw.line(
            [(0, y), (width, y)],
            fill=(
                min(255, int(r0 * factor)),
                min(255, int(g0 * factor)),
                min(255, int(b0 * factor)),
            ),
        )
    # Banda y texto.
    draw.rectangle([(0, int(height * 0.72)), (width, height)], fill=(0, 0, 0))
    font = _font(max(18, int(min(width, height) * 0.08)))
    small = _font(max(12, int(min(width, height) * 0.045)))
    font_size = getattr(font, "size", 18)
    lines = _wrap(draw, text, font, int(width * 0.86))
    total_height = len(lines) * (font_size + 6)
    y = int(height * 0.72) + (int(height * 0.28) - total_height) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((width - w) / 2, y), line, font=font, fill=(255, 255, 255))
        y += font_size + 6
    draw.text((16, 12), "ChambeApp · simulación", font=small, fill=(255, 255, 255))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _image_bytes(seed: str, size: tuple[int, int], label: str) -> bytes:
    """Foto real de picsum o placeholder determinista (cacheado)."""
    global _PICSUM_DISABLED
    key = f"{seed}:{size[0]}x{size[1]}"
    cached = _DOWNLOAD_CACHE.get(key)
    if cached:
        return cached
    data = None
    if not _PICSUM_DISABLED:
        url = PICSUM_URL.format(seed=seed, w=size[0], h=size[1])
        data = _download(url)
        if data is None:
            _PICSUM_DISABLED = True
    if data is None:
        data = _placeholder(label, size, seed)
    _DOWNLOAD_CACHE[key] = data
    return data


def _storage():
    from app.services.storage import storage

    return storage


def _fallback_url(seed: str, size: tuple[int, int]) -> str:
    return PICSUM_URL.format(seed=seed, w=size[0], h=size[1])


def business_logo(seed: str, negocio_id: int | str, nombre: str) -> str:
    """Logo cuadrado generado (más creíble que una foto aleatoria)."""
    data = _placeholder(nombre, (420, 420), seed)
    storage = _storage()
    if storage is not None:
        try:
            return storage.upload_business_image(data, str(negocio_id), "logo")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Logo negocio %s no subió: %s", negocio_id, exc)
    return _fallback_url(seed, (420, 420))


def business_banner(seed: str, negocio_id: int | str, nombre: str) -> str:
    data = _image_bytes(seed, (1200, 600), f"{nombre} · portada")
    storage = _storage()
    if storage is not None:
        try:
            return storage.upload_business_image(data, str(negocio_id), "banner")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Banner negocio %s no subió: %s", negocio_id, exc)
    return _fallback_url(seed, (1200, 600))


def business_gallery(seed: str, negocio_id: int | str, idx: int, nombre: str) -> str:
    data = _image_bytes(seed, (900, 650), f"{nombre} · foto {idx}")
    storage = _storage()
    if storage is not None:
        try:
            return storage.upload_business_image(
                data, str(negocio_id), f"galeria-{idx}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Galería negocio %s no subió: %s", negocio_id, exc)
    return _fallback_url(seed, (900, 650))


def portfolio_image(seed: str, pds_id: int | str, idx: int) -> str:
    data = _image_bytes(seed, (900, 700), "Trabajo de portafolio")
    storage = _storage()
    if storage is not None:
        try:
            return storage.upload_portfolio_image(data, str(pds_id), f"trabajo-{idx}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Portafolio PDS %s no subió: %s", pds_id, exc)
    return _fallback_url(seed, (900, 700))


def solicitud_image(seed: str, solicitud_id: int | str, idx: int) -> str:
    data = _image_bytes(seed, (1000, 700), "Foto de la solicitud")
    storage = _storage()
    if storage is not None:
        try:
            return storage.upload_business_image(
                data, f"solicitud-{solicitud_id}", f"foto-{idx}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Solicitud %s foto no subió: %s", solicitud_id, exc)
    return _fallback_url(seed, (1000, 700))


def panorama(seed: str, solicitud_id: int | str) -> str:
    """Panorama equirectangular sintético (2:1) para el visor 360."""
    width, height = 2048, 1024
    base = _color(seed)
    img = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        factor = 0.35 + 1.15 * (y / (height - 1))
        draw.line(
            [(0, y), (width, y)],
            fill=(
                min(255, int(base[0] * factor)),
                min(255, int(base[1] * factor)),
                min(255, int(base[2] * factor)),
            ),
        )
    # Sol y silueta de cerros.
    draw.ellipse([(1450, 260), (1650, 460)], fill=(255, 230, 160))
    draw.polygon(
        [(0, 760), (300, 560), (620, 720), (980, 500), (1320, 730), (1700, 540), (2048, 760), (2048, 1024), (0, 1024)],
        fill=(38, 56, 44),
    )
    font = _font(48)
    draw.text((60, 60), "Panorama 360 · ChambeApp", font=font, fill=(255, 255, 255))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=88)
    data = buffer.getvalue()
    storage = _storage()
    if storage is not None:
        try:
            return storage.upload_business_image(
                data, f"solicitud-{solicitud_id}", "pano-360"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Panorama %s no subió: %s", solicitud_id, exc)
    return _fallback_url(seed, (2048, 1024))


def kyc_pdf_base64(clave: str, nombre_usuario: str) -> str:
    """PDF sintético (base64) para que el documento KYC sea visible en la UI."""
    cache_key = f"{clave}:{nombre_usuario[:1]}"
    if cache_key in _KYC_PDF_CACHE:
        return _KYC_PDF_CACHE[cache_key]

    width, height = 800, 1100
    img = Image.new("RGB", (width, height), (248, 248, 246))
    draw = ImageDraw.Draw(img)
    title_font = _font(38)
    body_font = _font(24)
    small_font = _font(18)
    draw.rectangle([(0, 0), (width, 110)], fill=(214, 69, 65))
    draw.text((36, 30), "ChambeApp · Documento KYC", font=title_font, fill=(255, 255, 255))
    draw.text((36, 160), f"Documento: {clave.replace('_', ' ').title()}", font=body_font, fill=(30, 30, 30))
    draw.text((36, 210), f"Titular: {nombre_usuario}", font=body_font, fill=(30, 30, 30))
    draw.text((36, 260), "Estado: verificado en simulación", font=body_font, fill=(30, 30, 30))
    draw.rectangle([(36, 340), (width - 36, 860)], outline=(180, 180, 180), width=3)
    draw.text((70, 390), "REPÚBLICA DE COLOMBIA", font=body_font, fill=(60, 60, 60))
    draw.text((70, 450), "DOCUMENTO DE IDENTIDAD", font=body_font, fill=(60, 60, 60))
    draw.text((70, 560), "NOMBRE APELLIDO", font=title_font, fill=(20, 20, 20))
    draw.text((70, 640), "000.000.000", font=body_font, fill=(20, 20, 20))
    draw.text((70, 760), "Valledupar · Cesar", font=body_font, fill=(60, 60, 60))
    draw.text((36, 920), "Este documento es ficticio y se generó para la sustentación.", font=small_font, fill=(100, 100, 100))
    draw.text((36, 950), "No tiene validez legal.", font=small_font, fill=(100, 100, 100))
    buffer = io.BytesIO()
    img.save(buffer, format="PDF", resolution=100)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    _KYC_PDF_CACHE[cache_key] = encoded
    return encoded
