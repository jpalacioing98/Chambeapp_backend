"""SocketIO handlers para chat en tiempo real (RF-16).

**Único módulo que registra eventos Socket.IO.** Antes cada módulo
(chat/ofertas/notificaciones) registraba `connect`/`disconnect` y Flask-
SocketIO guarda UN handler por evento: el último pisaba al anterior y por
eso el chat en vivo no recibía mensajes. Ahora todo vive aquí.

Autenticación: el `user_id` NUNCA se toma del payload del cliente. Se deriva
del JWT (handshake `auth` o token del evento) vía `app.auth.socket_auth`.
Al conectar, el usuario se une automáticamente a su sala personal
`user:<id>` (recibe ofertas, contratos, chambas, marañas, negocios, etc.)
y a las salas de conversación que solicite con `join`.
"""

from flask import request
from flask_socketio import join_room, emit

from app.extensions import db
from app.auth.socket_auth import decode_socket_user_id
from app.models.chat import Conversation, Message
from app.schemas.chat import MessageSchema
from app.services.realtime import safe_emit

_user_by_sid: dict[str, int] = {}


def _authed_user_id(data=None):
    """Devuelve el user_id autenticado para el sid actual."""
    sid_user = _user_by_sid.get(getattr(request, "sid", None))
    if sid_user is not None:
        return sid_user
    return decode_socket_user_id(data=data)


def register_chat_socketio(sio) -> None:
    """Registra TODOS los eventos Socket.IO. Llamar tras socketio.init_app."""

    @sio.on("connect")
    def on_connect(auth=None):
        user_id = decode_socket_user_id(auth=auth)
        if user_id is not None:
            _user_by_sid[request.sid] = user_id
            # Sala personal: recibe eventos de dominio (ofertas, contratos,
            # chambas, marañas, anuncios, negocios, notificaciones) sin
            # necesidad de emitir `join` explícito.
            join_room(f"user:{user_id}")
            emit("status", {"msg": f"Conectado a sala user:{user_id}"})

    @sio.on("join")
    def on_join(data):
        """Une al usuario a la sala de una conversación (chat 1:1)."""
        data = data or {}
        user_id = _authed_user_id(data)
        if user_id is None:
            emit("error", {"msg": "No autenticado"})
            return

        room = f"user:{user_id}"
        join_room(room)
        emit("joined", {"room": room})

        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return
        conv = db.session.get(Conversation, conversation_id)
        if conv and conv.involves(int(user_id)):
            join_room(f"conversation_{conversation_id}")
            safe_emit(
                "status",
                {"msg": f"Usuario {user_id} unido a conversación {conversation_id}"},
                room=f"conversation_{conversation_id}",
            )
        else:
            emit("error", {"msg": "No autorizado para unirse a la conversación"})

    @sio.on("leave")
    def on_leave(data):
        """Sale de la sala de una conversación."""
        from flask_socketio import leave_room

        data = data or {}
        conversation_id = data.get("conversation_id")
        if conversation_id:
            leave_room(f"conversation_{conversation_id}")

    @sio.on("message")
    def on_message(data):
        conversation_id = data.get("conversation_id")
        sender_id = _authed_user_id(data)
        contenido = data.get("contenido")
        if sender_id is None:
            emit("error", {"msg": "No autenticado"})
            return
        conv = db.session.get(Conversation, conversation_id) if conversation_id else None
        if not conv or not conv.involves(int(sender_id)) or not contenido:
            return

        msg = Message(
            conversation_id=int(conversation_id),
            sender_id=int(sender_id),
            contenido=contenido,
            leido=False,
        )
        db.session.add(msg)
        db.session.commit()

        payload = MessageSchema().dump(msg)
        safe_emit("message", payload, room=f"conversation_{conversation_id}")
        # La contraparte recibe el mensaje aunque no tenga el hilo abierto.
        peer_id = conv.user_b_id if int(sender_id) == conv.user_a_id else conv.user_a_id
        safe_emit("message", payload, room=f"user:{peer_id}")

    @sio.on("disconnect")
    def on_disconnect():
        _user_by_sid.pop(getattr(request, "sid", None), None)