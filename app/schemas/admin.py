"""Marshmallow schemas para el panel admin (RBAC Fase 1 y Fase 2)."""

from marshmallow import Schema, fields, validate

from app.models.user import RolUsuario
from app.models.ticket import TICKET_CATEGORIES
from app.schemas.region import RegionMinSchema


class UserListSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    status = fields.String()
    created_at = fields.DateTime(attribute="fecha_registro")
    region = fields.Nested(RegionMinSchema, allow_none=True)


class UserDetailSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    status = fields.String()
    telefono = fields.String(allow_none=True)
    created_at = fields.DateTime(attribute="fecha_registro")
    last_login = fields.DateTime(allow_none=True)
    region = fields.Nested(RegionMinSchema, allow_none=True)


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
    contract_id = fields.Integer(allow_none=True)
    solicitud_id = fields.Integer(allow_none=True)
    oferta_id = fields.Integer(allow_none=True)
    solicitud_titulo = fields.String(attribute="solicitud.titulo", allow_none=True)
    reason = fields.String()
    status = fields.String()
    chat_habilitado = fields.Boolean()
    created_at = fields.DateTime()


class DisputeListResponseSchema(Schema):
    items = fields.List(fields.Nested(DisputeListSchema))
    total = fields.Integer()


class DisputeDetailSchema(Schema):
    id = fields.Integer()
    contract_id = fields.Integer(allow_none=True)
    solicitud_id = fields.Integer(allow_none=True)
    oferta_id = fields.Integer(allow_none=True)
    reason = fields.String()
    status = fields.String()
    chat_habilitado = fields.Boolean()
    chat_habilitado_solicitante = fields.Boolean()
    chat_habilitado_proveedor = fields.Boolean()
    decision_estado = fields.String(allow_none=True)
    decision_solicitante = fields.String(allow_none=True)
    decision_proveedor = fields.String(allow_none=True)
    negociacion_cerrada = fields.Boolean()
    resolved_by = fields.Integer(allow_none=True)
    resolved_at = fields.DateTime(allow_none=True)
    resolution = fields.String(allow_none=True)
    created_at = fields.DateTime()
    contract = fields.Raw(allow_none=True)
    solicitud = fields.Raw(allow_none=True)
    payment = fields.Raw(allow_none=True)
    resolved_by_user = fields.Raw(allow_none=True)


class DisputeResolveSchema(Schema):
    resolution = fields.String(required=True)


class DisputeChatSchema(Schema):
    """Habilita o bloquea el chat de una parte o de ambas."""

    habilitado = fields.Boolean(required=True)
    # Si se envía, solo cambia el chat del usuario indicado. Sin él,
    # habilita/bloquea a las dos partes.
    usuario_id = fields.Integer(required=False, allow_none=True)


class DisputeMessageSchema(Schema):
    """Mensaje de soporte dentro del chat de la disputa."""

    contenido = fields.String(required=True, validate=validate.Length(min=1, max=5000))


class DisputeVariablesSchema(Schema):
    """Variables de la negociación que soporte puede ajustar."""

    monto = fields.Float(required=False, allow_none=True)
    fecha_deseada = fields.Date(required=False, allow_none=True)
    horario = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=80)
    )
    condiciones = fields.List(
        fields.String(validate=validate.Length(min=1, max=500)), required=False
    )


# --------------------------------------------------------------------------
# Fase 2: tickets de soporte
# --------------------------------------------------------------------------
class TicketCreateSchema(Schema):
    subject = fields.String(required=True, validate=validate.Length(min=4, max=200))
    body = fields.String(required=True, validate=validate.Length(min=10, max=5000))
    category = fields.String(
        load_default="otro",
        validate=validate.OneOf(TICKET_CATEGORIES),
    )
    # Solo staff (soporte/admin/superadmin): crea el ticket a nombre de otro usuario.
    user_id = fields.Integer(required=False, allow_none=True)


class TicketCreateResponseSchema(Schema):
    id = fields.Integer()
    status = fields.String()
    category = fields.String()


class TicketUserSchema(Schema):
    id = fields.Integer()
    nombre = fields.String(allow_none=True)
    email = fields.Email(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)


class TicketListSchema(Schema):
    id = fields.Integer()
    user_id = fields.Integer()
    subject = fields.String()
    category = fields.String()
    status = fields.String()
    priority = fields.String()
    assigned_to = fields.Integer(allow_none=True)
    created_at = fields.DateTime()
    usuario = fields.Nested(TicketUserSchema, attribute="user", allow_none=True)
    assigned = fields.Nested(
        TicketUserSchema, attribute="assigned_user", allow_none=True
    )
    conversation_id = fields.Integer(allow_none=True)


class TicketDetailSchema(TicketListSchema):
    body = fields.String()
    resolved_at = fields.DateTime(allow_none=True)


class TicketListResponseSchema(Schema):
    items = fields.List(fields.Nested(TicketListSchema))
    total = fields.Integer()


class MyTicketSchema(Schema):
    """Ticket visto por su dueño (sin datos internos de staff)."""
    id = fields.Integer()
    subject = fields.String()
    body = fields.String()
    category = fields.String()
    status = fields.String()
    priority = fields.String()
    created_at = fields.DateTime()
    resolved_at = fields.DateTime(allow_none=True)


class MyTicketsResponseSchema(Schema):
    items = fields.List(fields.Nested(MyTicketSchema))
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
# Cobros en monedas (superadmin)
# --------------------------------------------------------------------------
class TarifasCobroUpdateSchema(Schema):
    pct_contrato = fields.Float(required=False)
    precio_moneda_cop = fields.Float(required=False)
    monedas_fijas = fields.Float(required=False)
    min_monedas_contrato = fields.Float(required=False)
    costo_publicar_anuncio = fields.Float(required=False)
    costo_reactivar_anuncio = fields.Float(required=False)


class TarifasCobroResponseSchema(Schema):
    tarifas = fields.Dict(keys=fields.String(), values=fields.Float())
    config = fields.Dict(keys=fields.String(), values=fields.Float())
    updated_at = fields.String(allow_none=True)
    updated_by = fields.Integer(allow_none=True)


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


# --------------------------------------------------------------------------
# División regional: personal (verificador/soporte) que crea el admin regional
# --------------------------------------------------------------------------
class StaffCreateSchema(Schema):
    """Crea un verificador/soporte dentro de la región del admin."""

    email = fields.Email(required=True)
    nombre = fields.String(required=True)
    rol = fields.String(
        required=True,
        validate=validate.OneOf(
            [RolUsuario.VERIFICADOR.value, RolUsuario.SOPORTE.value]
        ),
    )
    password = fields.String(required=True, validate=validate.Length(min=6))


class StaffItemSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    status = fields.String()
    created_at = fields.DateTime(attribute="fecha_registro")
    region = fields.Nested(RegionMinSchema, allow_none=True)


class StaffListResponseSchema(Schema):
    items = fields.List(fields.Nested(StaffItemSchema))
    total = fields.Integer()
