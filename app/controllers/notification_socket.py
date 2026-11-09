"""SocketIO handlers para notificaciones en tiempo real (Fase 3 UI/UX).

El frontend se une a la sala `user:<id>` al conectar (ver
`app.controllers.oferta_socket`), y el backend (p.ej. CascadeManager
corriendo en Celery) emite `notificacion:nueva` a esa sala usando la
cola de mensajes Redis configurada en `socketio.init_app(...,
message_queue=...)`.

NOTA: el evento `join` NO se registra aquí. Flask-SocketIO guarda UN
handler por evento, así que registrar `join` en este módulo pisaba el
handler de `app.controllers.chat_socket` (que une al usuario a la sala
de la conversación) y los mensajes en vivo nunca llegaban. El `join`
unificado vive en `chat_socket.py`.
"""

from app.extensions import socketio


def register_notification_socketio(sio) -> None:
    """Registra los handlers de notificaciones. Llamar tras socketio.init_app."""

    @sio.on("disconnect")
    def on_disconnect():
        return
