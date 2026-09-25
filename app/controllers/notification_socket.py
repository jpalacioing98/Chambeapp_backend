"""SocketIO handlers para notificaciones en tiempo real (Fase 3 UI/UX).

El frontend se une a la sala `user:<id>` emitiendo el evento `join` con su
JWT. El backend (p.ej. CascadeManager corriendo en Celery) emite
`notificacion:nueva` a esa sala usando la cola de mensajes Redis configurada
en `socketio.init_app(..., message_queue=...)`.

NOTA: al igual que chat_socket, en producción se recomienda validar el JWT en
el handshake; aquí decodificamos el token en el evento `join`.
"""

from flask_socketio import emit, join_room

from app.extensions import socketio
from app.auth.socket_auth import decode_socket_user_id


def register_notification_socketio(sio) -> None:
    """Registra los eventos de notificaciones. Llamar tras socketio.init_app."""

    @sio.on("join")
    def on_join(data):
        user_id = decode_socket_user_id(data=data)
        if user_id is None:
            emit("error", {"msg": "Token inválido para notificaciones"})
            return

        room = f"user:{user_id}"
        join_room(room)
        emit("joined", {"room": room})

    @sio.on("disconnect")
    def on_disconnect():
        return
