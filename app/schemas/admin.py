"""Marshmallow schemas para el panel admin (RBAC Fase 1 y Fase 2)."""

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
    contracts_total = fields.Integer()
    revenue_total = fields.Integer()
    disputes_open = fields.Integer()


class UserListResponseSchema(Schema):
    items = fields.List(fields.Nested(UserListSchema))
    total = fields.Integer()


class VerificationListResponseSchema(Schema):
    items = fields.List(fields.Nested(VerificationListSchema))
    total = fields.Integer()


# --------------------------------------------------------------------------
# Fase 2: moderación de solicitudes
# --------------------------------------------------------------------------
class SolicitudModerateSchema(Schema):
    action = fields.String(
        required=True, validate=validate.OneOf(["approve", "reject", "hide"])
    )


class SolicitudListSchema(Schema):
    id = fields.Integer()
    titulo = fields.String(allow_none=True)
    descripcion = fields.String()
    categoria = fields.String()
    estado = fields.String()
    user_id = fields.Integer(attribute="solicitante_id")
    created_at = fields.DateTime(attribute="creado_en")


class SolicitudListResponseSchema(Schema):
    items = fields.List(fields.Nested(SolicitudListSchema))
    total = fields.Integer()


# --------------------------------------------------------------------------
# Fase 2: moderación de contratos
# --------------------------------------------------------------------------
class ContractModerateSchema(Schema):
    action = fields.String(
        required=True, validate=validate.OneOf(["cancel", "flag"])
    )


class ContractListSchema(Schema):
    id = fields.Integer()
    estado = fields.String()
    comprador_id = fields.Integer(attribute="solicitante_id")
    vendedor_id = fields.Integer(attribute="proveedor_id")
    servicio_id = fields.Integer(attribute="service_id")
    monto = fields.Integer(allow_none=True)
    created_at = fields.DateTime(attribute="creado_en")


class ContractListResponseSchema(Schema):
    items = fields.List(fields.Nested(ContractListSchema))
    total = fields.Integer()


# --------------------------------------------------------------------------
# Fase 2: disputas / pagos directos
# --------------------------------------------------------------------------
class DisputeListSchema(Schema):
    id = fields.Integer()
    contract_id = fields.Integer()
    reason = fields.String()
    status = fields.String()
    created_at = fields.DateTime()


class DisputeListResponseSchema(Schema):
    items = fields.List(fields.Nested(DisputeListSchema))
    total = fields.Integer()


class DisputeDetailSchema(Schema):
    id = fields.Integer()
    contract_id = fields.Integer()
    reason = fields.String()
    status = fields.String()
    resolved_by = fields.Integer(allow_none=True)
    resolved_at = fields.DateTime(allow_none=True)
    resolution = fields.String(allow_none=True)
    payment_action = fields.String(allow_none=True)
    created_at = fields.DateTime()
    contract = fields.Raw(allow_none=True)
    payment = fields.Raw(allow_none=True)


class DisputeResolveSchema(Schema):
    resolution = fields.String(required=True)
    payment_action = fields.String(
        required=True, validate=validate.OneOf(["release", "refund"])
    )


# --------------------------------------------------------------------------
# Fase 2: tickets de soporte
# --------------------------------------------------------------------------
class TicketCreateSchema(Schema):
    subject = fields.String(required=True)
    body = fields.String(required=True)


class TicketCreateResponseSchema(Schema):
    id = fields.Integer()
    status = fields.String()


class TicketListSchema(Schema):
    id = fields.Integer()
    user_id = fields.Integer()
    subject = fields.String()
    status = fields.String()
    priority = fields.String()
    assigned_to = fields.Integer(allow_none=True)
    created_at = fields.DateTime()


class TicketListResponseSchema(Schema):
    items = fields.List(fields.Nested(TicketListSchema))
    total = fields.Integer()


class TicketPatchSchema(Schema):
    status = fields.String(
        required=False,
        validate=validate.OneOf(["open", "pending", "closed"]),
    )
    assigned_to = fields.Integer(required=False, allow_none=True)
    priority = fields.String(
        required=False, validate=validate.OneOf(["low", "normal", "high"])
    )


# --------------------------------------------------------------------------
# Fase 2: moderación de contenido (ratings)
# --------------------------------------------------------------------------
class ContentReportSchema(Schema):
    id = fields.Integer()
    service_id = fields.Integer()
    user_id = fields.Integer(attribute="autor_id")
    comentario = fields.String(allow_none=True)
    puntuacion = fields.Integer(attribute="puntaje")


class ContentReportResponseSchema(Schema):
    items = fields.List(fields.Nested(ContentReportSchema))
    total = fields.Integer()


class ContentModerateSchema(Schema):
    action = fields.String(
        required=True, validate=validate.OneOf(["hide", "delete"])
    )
