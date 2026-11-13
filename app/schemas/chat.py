"""Marshmallow schemas for chat (RF-16 — mensajería)."""

from marshmallow import Schema, fields


class MessageSchema(Schema):
    id = fields.Integer()
    conversation_id = fields.Integer()
    sender_id = fields.Integer()
    contenido = fields.String()
    leido = fields.Boolean()
    es_soporte = fields.Boolean()
    creado_en = fields.DateTime()


class MessageCreateSchema(Schema):
    contenido = fields.String(required=True, validate=fields.validate.Length(min=1, max=5000))


class ConversationCreateSchema(Schema):
    user_b_id = fields.Integer(required=True, data_key="otro_usuario_id")


class ConversationSchema(Schema):
    id = fields.Integer()
    user_a_id = fields.Integer()
    user_b_id = fields.Integer()
    creado_en = fields.DateTime()
    last_message = fields.Nested(MessageSchema, dump_only=True, allow_none=True)
    # Otro participante desde la perspectiva del usuario autenticado.
    # Lo adjunta la ruta como atributo transitorio `conv.peer`.
    otro_participante = fields.Method(
        "get_otro_participante", dump_only=True, allow_none=True
    )
    # True mientras una disputa abierta mantiene bloqueado el chat entre
    # las partes y soporte no lo ha habilitado.
    chat_bloqueado = fields.Method("get_chat_bloqueado", dump_only=True)
    chat_oculto = fields.Method("get_chat_oculto", dump_only=True)

    def get_otro_participante(self, obj):
        return getattr(obj, "peer", None)

    def get_chat_bloqueado(self, obj):
        return bool(getattr(obj, "chat_bloqueado", False))

    def get_chat_oculto(self, obj):
        return bool(getattr(obj, "chat_oculto", False))
