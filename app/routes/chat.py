"""Chat blueprint: conversaciones y mensajes 1:1 (RF-16 — mensajería)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db, socketio
from app.models.chat import Conversation, Message
from app.schemas.chat import (
    ConversationSchema,
    ConversationCreateSchema,
    MessageSchema,
    MessageCreateSchema,
)

blp = Blueprint("chat", __name__, description="Chat y mensajería en tiempo real")


def _get_conversation_or_404(conversation_id: int) -> Conversation:
    return db.get_or_404(Conversation, conversation_id)


def _ensure_participant(conv: Conversation, user_id: int) -> None:
    if not conv.involves(user_id):
        abort(403, message="No eres participante de esta conversación.")


@blp.route("/conversations")
class Conversations(MethodView):
    @jwt_required()
    @blp.arguments(ConversationCreateSchema)
    @blp.response(200, ConversationSchema)
    @blp.response(201, ConversationSchema)
    def post(self, data):
        """Crea (o devuelve existente) conversación 1:1 con otro_usuario_id."""
        current = int(get_jwt_identity())
        otro = int(data["user_b_id"])
        if otro == current:
            abort(400, message="No puedes iniciar una conversación contigo mismo.")

        a, b = Conversation.normalize(current, int(otro))
        conv = Conversation.query.filter_by(user_a_id=a, user_b_id=b).first()
        if conv:
            return conv, 200

        conv = Conversation(user_a_id=a, user_b_id=b)
        db.session.add(conv)
        db.session.commit()
        return conv, 201

    @jwt_required()
    @blp.response(200, ConversationSchema(many=True))
    def get(self):
        """Lista conversaciones del usuario actual con su último mensaje."""
        current = int(get_jwt_identity())
        convs = (
            Conversation.query.filter(
                (Conversation.user_a_id == current)
                | (Conversation.user_b_id == current)
            )
            .order_by(Conversation.creado_en.desc())
            .all()
        )
        for conv in convs:
            conv.last_message = (
                Message.query.filter_by(conversation_id=conv.id)
                .order_by(Message.creado_en.desc())
                .first()
            )
        return convs


@blp.route("/conversations/<int:conversation_id>/messages")
class ConversationMessages(MethodView):
    @jwt_required()
    @blp.response(200, MessageSchema(many=True))
    def get(self, conversation_id):
        """Historial de mensajes (solo participantes)."""
        current = int(get_jwt_identity())
        conv = _get_conversation_or_404(conversation_id)
        _ensure_participant(conv, current)
        return (
            Message.query.filter_by(conversation_id=conversation_id)
            .order_by(Message.creado_en.asc())
            .all()
        )

    @jwt_required()
    @blp.arguments(MessageCreateSchema)
    @blp.response(201, MessageSchema)
    def post(self, data, conversation_id):
        """Envía mensaje: persiste y difunde vía SocketIO a la sala."""
        current = int(get_jwt_identity())
        conv = _get_conversation_or_404(conversation_id)
        _ensure_participant(conv, current)

        msg = Message(
            conversation_id=conversation_id,
            sender_id=current,
            contenido=data["contenido"],
            leido=False,
        )
        db.session.add(msg)
        db.session.commit()

        payload = MessageSchema().dump(msg)
        socketio.emit("message", payload, room=f"conversation_{conversation_id}")

        return msg, 201


@blp.route("/conversations/<int:conversation_id>/messages/read")
class ConversationMessagesRead(MethodView):
    @jwt_required()
    @blp.response(200, MessageSchema(many=True))
    def patch(self, conversation_id):
        """Marca como leídos los mensajes recibidos por el usuario actual."""
        current = int(get_jwt_identity())
        conv = _get_conversation_or_404(conversation_id)
        _ensure_participant(conv, current)

        pendientes = Message.query.filter_by(
            conversation_id=conversation_id, leido=False
        ).filter(Message.sender_id != current).all()
        for m in pendientes:
            m.leido = True
        db.session.commit()
        return pendientes
