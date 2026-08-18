"""Marshmallow schemas para el panel admin (RBAC Fase 1)."""

from marshmallow import Schema, fields, validate

from app.models.user import RolUsuario


class UserListSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    status = fields.String()
    created_at = fields.DateTime(attribute="fecha_registro")


class UserDetailSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    status = fields.String()
    telefono = fields.String(allow_none=True)
    created_at = fields.DateTime(attribute="fecha_registro")
    last_login = fields.DateTime(allow_none=True)


class RolePatchSchema(Schema):
    role = fields.String(
        required=True, validate=validate.OneOf(RolUsuario.values())
    )


class StatusPatchSchema(Schema):
    status = fields.String(
        required=True, validate=validate.OneOf(["active", "suspended", "banned"])
    )


class RejectSchema(Schema):
    reason = fields.String(required=True)


class VerificationListSchema(Schema):
    id = fields.Integer()
    user_id = fields.Integer()
    nombre = fields.String(allow_none=True)
    document_type = fields.String(allow_none=True)
    document_number = fields.String(allow_none=True)
    status = fields.String()
    created_at = fields.DateTime()


class VerificationActionSchema(Schema):
    id = fields.Integer()
    status = fields.String()


class StatsOverviewSchema(Schema):
    users_total = fields.Integer()
    users_active = fields.Integer()
    services_total = fields.Integer()
    orders_total = fields.Integer()
    revenue_total = fields.Integer()
    disputes_open = fields.Integer()


class UserListResponseSchema(Schema):
    items = fields.List(fields.Nested(UserListSchema))
    total = fields.Integer()


class VerificationListResponseSchema(Schema):
    items = fields.List(fields.Nested(VerificationListSchema))
    total = fields.Integer()
