"""Emisión segura de eventos Socket.IO.

Un fallo del broker (p. ej. Redis caído cuando `message_queue` está
configurado) NO debe tumbar la petición HTTP que ya persistió el cambio.
El evento se pierde, pero el cliente se reconcilia en su siguiente fetch.

Todo módulo que emita eventos de dominio debe usar `safe_emit` en lugar de
`socketio.emit` directo.
"""

import logging

from app.extensions import socketio

log = logging.getLogger(__name__)


def safe_emit(event: str, payload, room: str | None = None) -> None:
    """Emite un evento; registra el error en lugar de propagarlo."""
    try:
        socketio.emit(event, payload, room=room)
    except Exception as exc:  # noqa: BLE001 — nunca romper el flujo de negocio
        log.warning("Socket.IO: no se pudo emitir '%s': %s", event, exc)
