"""Marshmallow schemas para el panel SUPERADMIN (RBAC Fase 3)."""

from marshmallow import Schema, fields, validate

from app.models.user import RolUsuario

# Roles internos que un SUPERADMIN puede gestionar (no superadmin ni roles públicos).
INTERNAL_ROLES = [RolUsuario.ADMIN.value, RolUsuario.SOPORTE.value, RolUsuario.VERIFICADOR.value]


class AdminCreateSchema(Schema):
    email = fields.Email(required=True)
    nombre = fields.String(required=True)
    rol = fields.String(required=True, validate=validate.OneOf(INTERNAL_ROLES))
    password = fields.String(required=True, validate=validate.Length(min=6))


class AdminPatchSchema(Schema):
    nombre = fields.String(required=False)
    rol = fields.String(required=False, validate=validate.OneOf(INTERNAL_ROLES))
    status = fields.String(
        required=False, validate=validate.OneOf(["active", "suspended", "banned"])
    )


class AdminItemSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    status = fields.String()


class AdminListResponseSchema(Schema):
    items = fields.List(fields.Nested(AdminItemSchema))
    total = fields.Integer()


class ConfigPatchSchema(Schema):
    key = fields.String(required=True)
    value = fields.Raw(required=True)


class ConfigItemSchema(Schema):
    key = fields.String()
    value = fields.Raw()
    value_type = fields.String()
    description = fields.String(allow_none=True)


class ConfigListResponseSchema(Schema):
    configs = fields.List(fields.Nested(ConfigItemSchema))


class AuditLogItemSchema(Schema):
    id = fields.Integer()
    actor_id = fields.Integer()
    action = fields.String()
    entity_type = fields.String()
    entity_id = fields.Integer(allow_none=True)
    ip = fields.String(allow_none=True)
    created_at = fields.DateTime()


class AuditLogListResponseSchema(Schema):
    items = fields.List(fields.Nested(AuditLogItemSchema))
    total = fields.Integer()


class AuditLogDetailSchema(Schema):
    id = fields.Integer()
    actor_id = fields.Integer()
    action = fields.String()
    entity_type = fields.String()
    entity_id = fields.Integer(allow_none=True)
    before_json = fields.Raw(allow_none=True)
    after_json = fields.Raw(allow_none=True)
    ip = fields.String(allow_none=True)
    created_at = fields.DateTime()

    def post_dump(self, data, **kwargs):
        # Parsea before/after (texto JSON) a objetos para respuesta legible.
        for key in ("before_json", "after_json"):
            val = data.get(key)
            if isinstance(val, str):
                try:
                    data[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        return data


class TyCGetSchema(Schema):
    version = fields.Raw()
    content = fields.String(allow_none=True)
    published_at = fields.String(allow_none=True)


class TyCPostSchema(Schema):
    content = fields.String(required=True)


class TyCPostResponseSchema(Schema):
    version = fields.Raw()
    published_at = fields.String(allow_none=True)


class OverrideUserSchema(Schema):
    user_id = fields.Integer(required=True)
    action = fields.String(
        required=True, validate=validate.OneOf(["reactivate", "suspend"])
    )


class OverrideOrderSchema(Schema):
    order_id = fields.Integer(required=True)
    action = fields.String(
        required=True, validate=validate.OneOf(["complete", "cancel"])
    )


class FlagPatchSchema(Schema):
    enabled = fields.Boolean(required=True)


class FlagItemSchema(Schema):
    key = fields.String()
    enabled = fields.Boolean()
    description = fields.String(allow_none=True)


class FlagListResponseSchema(Schema):
    items = fields.List(fields.Nested(FlagItemSchema))
