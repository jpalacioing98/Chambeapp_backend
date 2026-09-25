"""Marshmallow schemas for chat (RF-16 — mensajería)."""

from marshmallow import Schema, fields


class MessageSchema(Schema):
    id = fields.Integer()
    conversation_id = fields.Integer()
    sender_id = fields.Integer()
    contenido = fields.String()
    leido = fields.Boolean()
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

    def get_otro_participante(self, obj):
        return getattr(obj, "peer", None)
