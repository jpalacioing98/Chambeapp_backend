"""Emisión segura de eventos Socket.IO.

Un fallo del broker (p. ej. Redis caído cuando `message_queue` está
configurado) NO debe tumbar la petición HTTP que ya persistió el cambio.
El evento se pierde, pero el cliente se reconcilia en su siguiente fetch.

Todo módulo que emita eventos de dominio debe usar `safe_emit` en lugar de
`socketio.emit` directo.

Observabilidad: cada emisión deja una línea de log estructurada
(`socket_emit` / `socket_emit_failed`) con evento, sala, duración y un
`correlation_id` opcional para seguir un flujo completo. Los contadores
en proceso se consultan con `get_emit_stats()`.
"""

import logging
import time
from collections import Counter
from typing import Any

from app.extensions import socketio

log = logging.getLogger(__name__)

# Contadores por proceso. Se reinician con el worker; sirven para detectar
# caídas del broker desde un health-check o desde los tests.
_stats: Counter[str] = Counter()


def get_emit_stats() -> dict[str, int]:
    """Devuelve los contadores de emisión del proceso actual."""
    return {
        "ok": _stats["ok"],
        "failed": _stats["failed"],
    }


def safe_emit(
    event: str,
    payload: Any,
    room: str | None = None,
    *,
    correlation_id: str | None = None,
) -> bool:
    """Emite un evento; registra el fallo en lugar de propagarlo.

    Devuelve `True` si Flask-SocketIO aceptó la emisión (en modo
    `message_queue` esto significa que se publicó en Redis) y `False` si el
    broker falló. Nunca lanza: el flujo de negocio ya persistió el cambio.
    """
    started = time.perf_counter()
    destino = room or "*"
    try:
        socketio.emit(event, payload, room=room)
    except Exception as exc:  # noqa: BLE001 — nunca romper el flujo de negocio
        _stats["failed"] += 1
        log.warning(
            "socket_emit_failed event=%s room=%s correlation_id=%s error=%s",
            event,
            destino,
            correlation_id or "-",
            exc,
            exc_info=True,
        )
        return False

    _stats["ok"] += 1
    log.debug(
        "socket_emit event=%s room=%s correlation_id=%s duration_ms=%.2f",
        event,
        destino,
        correlation_id or "-",
        (time.perf_counter() - started) * 1000,
    )
    return True


def emit_to_user(
    user_id: int,
    event: str,
    payload: Any,
    *,
    correlation_id: str | None = None,
) -> bool:
    """Atajo para emitir a la sala personal `user:<id>`."""
    return safe_emit(
        event,
        payload,
        room=f"user:{user_id}",
        correlation_id=correlation_id,
    )
