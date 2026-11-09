"""Middleware transversal: compresión gzip de respuestas JSON/texto.

No añade dependencias (usa `gzip` de la stdlib). Se excluyen respuestas
streaming (SSE/descargas) y las que ya vienen comprimidas.
"""

import gzip

from flask import request

_MIN_BYTES = 500
_SKIP_TYPES = ("text/event-stream",)


def init_compression(app):
    """Registra la compresión gzip en la app Flask."""

    @app.after_request
    def _compress(response):
        if response.direct_passthrough or response.is_streamed:
            return response
        if response.status_code != 200:
            return response
        if response.headers.get("Content-Encoding"):
            return response
        if "gzip" not in (request.headers.get("Accept-Encoding") or "").lower():
            return response
        content_type = (response.content_type or "").lower()
        if not (content_type.startswith("application/json") or content_type.startswith("text/")):
            return response
        if any(t in content_type for t in _SKIP_TYPES):
            return response
        data = response.get_data()
        if len(data) < _MIN_BYTES:
            return response
        compressed = gzip.compress(data, compresslevel=6)
        if len(compressed) >= len(data):
            return response
        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(compressed))
        response.headers.add("Vary", "Accept-Encoding")
        return response
