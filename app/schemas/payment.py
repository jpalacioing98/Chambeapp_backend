"""Marshmallow schemas for payments (RF-08)."""

from marshmallow import Schema, fields, validate

from app.models.payment import EstadoPago


class PaymentCreateSchema(Schema):
    """Body de creacion de pago (RF-08.1)."""

    contract_id = fields.Integer(required=True)
    monto = fields.Integer(required=True, validate=validate.Range(min=1))
    pasarela = fields.String(
        required=False,
        load_default="nequi",
        validate=validate.OneOf(["nequi", "mock"]),
    )


class PaymentEstadoSchema(Schema):
    """Accion de reembolso / estado (RF-08.7)."""

    estado = fields.String(
        required=False,
        validate=validate.OneOf(EstadoPago.values()),
    )
    motivo_reembolso = fields.String(required=False, allow_none=True)


class PaymentSchema(Schema):
    id = fields.Integer()
    contract_id = fields.Integer()
    monto = fields.Integer()
    comision = fields.Integer()
    estado = fields.Enum(EstadoPago, by_value=True)
    pasarela = fields.String()
    referencia_pasarela = fields.String(allow_none=True)
    motivo_reembolso = fields.String(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    liberado_en = fields.DateTime(allow_none=True)


class NequiInfoSchema(Schema):
    """RF-08 (Nequi): numero y titular expuestos para transferencia manual."""

    numero = fields.String()
    titular = fields.String()


class IncomeCertificateHistorySchema(Schema):
    """Entrada mensual del historial de ingresos (RF-13)."""

    mes = fields.String()  # "YYYY-MM"
    ingreso = fields.Integer()  # neto (monto - comision)
    servicios = fields.Integer()  # contratos completados en el mes


class IncomeCertificateSchema(Schema):
    """RF-13: certificado de trazabilidad de ingresos del proveedor."""

    nombre = fields.String()
    verificado = fields.Boolean()
    calificacion_promedio = fields.Float()
    periodo = fields.Raw()  # {"desde": "YYYY-MM-DD", "hasta": "YYYY-MM-DD"}
    total_ingresos = fields.Integer()
    promedio_mensual = fields.Integer()
    servicios_completados = fields.Integer()
    historial = fields.List(fields.Nested(IncomeCertificateHistorySchema))
