"""Marshmallow schemas del módulo Comerciante."""

from marshmallow import Schema, fields, validate


class MerchantPaymentMethodCreateSchema(Schema):
    """Body de POST /merchant/payment-methods."""
    tipo = fields.String(
        required=True,
        validate=validate.OneOf(["nequi", "daviplata", "bancolombia",
                                  "efectivo", "otro"]),
    )
    detalle = fields.Dict(required=True)
    principal = fields.Boolean(load_default=False)


class MerchantPaymentMethodResponseSchema(Schema):
    """Salida de un método de pago."""
    id = fields.Integer()
    user_id = fields.Integer()
    tipo = fields.String()
    detalle = fields.Dict()
    principal = fields.Boolean()
    activo = fields.Boolean()
    creado_en = fields.DateTime()


class MerchantPaymentMethodsListSchema(Schema):
    """Wrapper para lista de métodos de pago."""
    metodos = fields.List(fields.Nested(MerchantPaymentMethodResponseSchema))


class MerchantPreferencesResponseSchema(Schema):
    """Salida de GET /merchant/preferences (y /users/me/preferences)."""
    notif_nueva_solicitud = fields.Boolean()
    notif_nueva_resena = fields.Boolean()
    notif_estado_kyc = fields.Boolean()
    notif_pago_recibido = fields.Boolean()
    push_enabled = fields.Boolean()
    email_digest = fields.String()
    idioma = fields.String()
    tema = fields.String()
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()


class MerchantPreferencesUpdateSchema(Schema):
    """Body de PUT /merchant/preferences (campos opcionales)."""
    notif_nueva_solicitud = fields.Boolean()
    notif_nueva_resena = fields.Boolean()
    notif_estado_kyc = fields.Boolean()
    notif_pago_recibido = fields.Boolean()
    push_enabled = fields.Boolean()
    email_digest = fields.String(
        validate=validate.OneOf(["daily", "weekly", "never"]),
    )
    idioma = fields.String(validate=validate.OneOf(["es", "en"]))
    tema = fields.String(validate=validate.OneOf(["light", "dark", "system"]))


class NegocioStatsSchema(Schema):
    """Salida de GET /negocios/<id>/stats."""
    negocio_id = fields.Integer()
    periodo = fields.String()
    calificacion_promedio = fields.Float()
    total_calificaciones = fields.Integer()
    distribucion_estrellas = fields.Dict()
    total_solicitudes_zona = fields.Integer()
    solicitudes_activas = fields.Integer()
    contratos_completados = fields.Integer()
    ingresos_totales = fields.Integer()
    visitas_perfil = fields.Integer()
    tasa_respuesta = fields.Float()


class NegocioImagenUploadResponseSchema(Schema):
    """Salida de POST /negocios/<id>/imagenes/upload."""
    url = fields.String()
    negocio_id = fields.Integer()


class TrustScorePublicSchema(Schema):
    """Salida de GET /trust/<user_id> (público)."""
    user_id = fields.Integer()
    puntuacion = fields.Float()
    nivel = fields.String()
    kyc_verificado = fields.Boolean()
    rating_score = fields.Float()
    contratos_completados = fields.Integer()
    nivel_label = fields.String()
