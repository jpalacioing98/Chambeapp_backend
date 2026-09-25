"""SocketIO handlers para chat en tiempo real (RF-16).

Autenticación: el `user_id` NUNCA se toma del payload del cliente. Se deriva
del JWT (handshake `auth` o token del evento) vía `app.auth.socket_auth`.
El `connect` autenticado guarda `sid -> user_id`; join/message lo usan.
"""

from flask import request
from flask_socketio import join_room, emit

from app.extensions import socketio, db
from app.auth.socket_auth import decode_socket_user_id
from app.models.chat import Conversation, Message
from app.schemas.chat import MessageSchema

_user_by_sid: dict[str, int] = {}


def _authed_user_id(data=None):
    """Devuelve el user_id autenticado para el sid actual."""
    sid_user = _user_by_sid.get(getattr(request, "sid", None))
    if sid_user is not None:
        return sid_user
    return decode_socket_user_id(data=data)


def register_chat_socketio(sio) -> None:
    """Registra los eventos de chat. Llamar DESPUÉS de socketio.init_app."""

    @sio.on("connect")
    def on_connect(auth=None):
        user_id = decode_socket_user_id(auth=auth)
        if user_id is not None:
            _user_by_sid[request.sid] = user_id

    @sio.on("join")
    def on_join(data):
        conversation_id = data.get("conversation_id")
        user_id = _authed_user_id(data)
        if user_id is None:
            emit("error", {"msg": "No autenticado"})
            return
        conv = db.session.get(Conversation, conversation_id) if conversation_id else None
        if conv and conv.involves(int(user_id)):
            join_room(f"conversation_{conversation_id}")
            emit(
                "status",
                {"msg": f"Usuario {user_id} unido a conversación {conversation_id}"},
                room=f"conversation_{conversation_id}",
            )
        else:
            emit("error", {"msg": "No autorizado para unirse a la conversación"})

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

        emit(
            "message",
            MessageSchema().dump(msg),
            room=f"conversation_{conversation_id}",
        )

    @sio.on("disconnect")
    def on_disconnect():
        _user_by_sid.pop(getattr(request, "sid", None), None)