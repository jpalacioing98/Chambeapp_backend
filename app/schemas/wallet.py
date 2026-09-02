"""Marshmallow schemas for wallet, coins, modalities, milestones (RF-25, RF-26, RF-27, RF-29)."""

from marshmallow import Schema, fields, validate

from app.models.wallet import TipoTransaccion, TipoMoneda
from app.models.modalidad import TipoModalidad, EstadoHito


# --- Wallet (RF-25) ---

class WalletSchema(Schema):
    """Schema de billetera virtual."""

    id = fields.Integer()
    user_id = fields.Integer()
    saldo = fields.Integer()
    saldo_bloqueado = fields.Integer()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class WalletDepositSchema(Schema):
    """Body para depositar fondos."""

    monto = fields.Integer(required=True, validate=validate.Range(min=1000))
    pasarela = fields.String(
        required=False,
        load_default="nequi",
        validate=validate.OneOf(["nequi", "mercadopago", "pse", "mock"]),
    )


class WalletWithdrawSchema(Schema):
    """Body para retirar fondos."""

    monto = fields.Integer(required=True, validate=validate.Range(min=10000))
    cuenta_destino = fields.String(required=True)


class TransactionSchema(Schema):
    """Schema de transacción de billetera."""

    id = fields.Integer()
    wallet_id = fields.Integer()
    tipo = fields.Enum(TipoTransaccion, by_value=True)
    monto = fields.Integer()
    descripcion = fields.String(allow_none=True)
    referencia = fields.String(allow_none=True)
    created_at = fields.DateTime()


# --- Coins (RF-27) ---

class CoinSchema(Schema):
    """Schema de moneda."""

    id = fields.Integer()
    user_id = fields.Integer()
    cantidad = fields.Integer()
    tipo = fields.Enum(TipoMoneda, by_value=True)
    vence_en = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()


class CoinBuySchema(Schema):
    """Body para comprar monedas."""

    paquete = fields.String(
        required=True,
        validate=validate.OneOf(["basico", "estandar", "premium"]),
    )


class CoinUseSchema(Schema):
    """Body para usar monedas."""

    cantidad = fields.Integer(required=True, validate=validate.Range(min=1))
    motivo = fields.String(required=True)


# --- Modalidades (RF-26) ---

class ModalidadSchema(Schema):
    """Schema de modalidad de cobro."""

    id = fields.Integer()
    service_id = fields.Integer()
    tipo = fields.Enum(TipoModalidad, by_value=True)
    monedas_requeridas = fields.Integer(allow_none=True)
    created_at = fields.DateTime()


class ModalidadCreateSchema(Schema):
    """Body para establecer modalidad."""

    tipo = fields.String(
        required=True,
        validate=validate.OneOf(TipoModalidad.values()),
    )


# --- Milestones (RF-29) ---

class MilestoneSchema(Schema):
    """Schema de hito de pago."""

    id = fields.Integer()
    contract_id = fields.Integer()
    numero = fields.Integer()
    descripcion = fields.String(allow_none=True)
    monto = fields.Integer()
    estado = fields.Enum(EstadoHito, by_value=True)
    aprobado_en = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()


class MilestoneCreateSchema(Schema):
    """Body para crear hitos."""

    hitos = fields.List(
        fields.Dict(
            keys=fields.String(),
            values=fields.Raw(),
        ),
        required=True,
        validate=validate.Length(min=1, max=12),
    )


class MilestoneActionSchema(Schema):
    """Body para aprobar/rechazar hito."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(["aprobar", "rechazar"]),
    )
