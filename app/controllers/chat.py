"""Chat blueprint: conversaciones y mensajes 1:1 (RF-16 — mensajería)."""

import json
import os
import uuid

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db, socketio
from app.models.chat import Conversation, Message
from app.models.user import User
from app.schemas.chat import (
    ConversationSchema,
    ConversationCreateSchema,
    MessageSchema,
    MessageCreateSchema,
)

blp = Blueprint("chat", __name__, description="Chat y mensajería en tiempo real")

# Tipos de archivo permitidos en los adjuntos del chat.
TIPOS_ADJUNTO = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
    "text/plain",
}
EXTENSIONES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}
MAX_ADJUNTO_BYTES = 10 * 1024 * 1024


def _get_conversation_or_404(conversation_id: int) -> Conversation:
    return db.get_or_404(Conversation, conversation_id)


def _ensure_participant(conv: Conversation, user_id: int) -> None:
    if not conv.involves(user_id):
        abort(403, message="No eres participante de esta conversación.")


def _attach_peer(conv: Conversation, current_user_id: int) -> None:
    """Adjunta el otro participante (perspectiva del usuario autenticado).

    El "otro" cambia según quién consulta: si current es user_a, el peer es
    user_b y viceversa. Se guarda como atributo transitorio `conv.peer` que
    `ConversationSchema.otro_participante` serializa.
    """
    peer_id = conv.user_b_id if conv.user_a_id == current_user_id else conv.user_a_id
    peer = db.session.get(User, peer_id)
    if peer is None:
        conv.peer = None
        return
    conv.peer = {
        "id": peer.id,
        "nombre": peer.nombre,
        "username": peer.username,
        "verificado": bool(peer.profile.verificado) if peer.profile else False,
        "rol": getattr(peer.rol, "value", peer.rol),
        "foto_perfil": peer.profile.foto_perfil if peer.profile else None,
    }


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
            _attach_peer(conv, current)
            return conv, 200

        conv = Conversation(user_a_id=a, user_b_id=b)
        db.session.add(conv)
        db.session.commit()
        _attach_peer(conv, current)
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
            _attach_peer(conv, current)
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


@blp.route("/conversations/<int:conversation_id>/attachments")
class ConversationAttachments(MethodView):
    @jwt_required()
    @blp.response(201, MessageSchema)
    def post(self, conversation_id):
        """Sube un adjunto al chat y lo publica como mensaje.

        Multipart con el campo `file`. El archivo se guarda en el bucket
        público de chat (MinIO) y el hilo recibe un mensaje estructurado
        `⟦c:adjunto⟧` con la URL, el nombre, el tipo y el tamaño.
        """
        current = int(get_jwt_identity())
        conv = _get_conversation_or_404(conversation_id)
        _ensure_participant(conv, current)

        archivo = request.files.get("file")
        if archivo is None or not archivo.filename:
            abort(400, message="No se recibió el archivo.")

        content_type = (archivo.mimetype or "").lower()
        if content_type not in TIPOS_ADJUNTO:
            abort(
                400,
                message="Tipo de archivo no permitido (imágenes, PDF o texto plano).",
            )

        data = archivo.read()
        if not data:
            abort(400, message="El archivo está vacío.")
        if len(data) > MAX_ADJUNTO_BYTES:
            abort(400, message="El archivo supera el límite de 10 MB.")

        from app.services.storage import storage as storage_svc
        if storage_svc is None:
            abort(503, message="El almacenamiento de archivos no está disponible.")

        nombre_original = archivo.filename or "archivo"
        extension = EXTENSIONES.get(content_type, os.path.splitext(nombre_original)[1] or ".bin")
        clave = f"{uuid.uuid4().hex}{extension}"
        try:
            url = storage_svc.upload_chat_file(
                data, str(conversation_id), clave, content_type
            )
        except Exception:
            abort(502, message="No se pudo subir el archivo.")

        contenido = (
            "⟦c:adjunto⟧"
            + json.dumps(
                {
                    "url": url,
                    "nombre": nombre_original,
                    "tipo": content_type,
                    "tamano": len(data),
                },
                ensure_ascii=False,
            )
        )
        msg = Message(
            conversation_id=conversation_id,
            sender_id=current,
            contenido=contenido,
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
