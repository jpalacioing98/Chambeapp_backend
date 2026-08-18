"""SocketIO handlers para chat en tiempo real (RF-16).

NOTA: Los handlers SocketIO NO son cubiertos por pytest (requieren un
cliente WS / `socketio.run`). Se prueban indirectamente vía REST
(la ruta POST /messages persiste y emite a la sala). En producción usar
async_mode='eventlet' y validar JWT en lugar de confiar en user_id del cliente.
"""

from flask_socketio import join_room, emit

from app.extensions import socketio, db
from app.models.chat import Conversation, Message
from app.schemas.chat import MessageSchema


def register_chat_socketio(sio) -> None:
    """Registra los eventos de chat. Llamar DESPUÉS de socketio.init_app."""

    @sio.on("join")
    def on_join(data):
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
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
        sender_id = data.get("user_id")
        contenido = data.get("contenido")
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
        return
