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
    monedas_saldo = fields.Integer()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


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
    """Body para comprar un paquete de monedas."""

    paquete_id = fields.Integer(required=True, validate=validate.Range(min=1))
    metodo_pago_id = fields.Integer(required=False, allow_none=True)


class CoinUseSchema(Schema):
    """Body para usar monedas."""

    cantidad = fields.Integer(required=True, validate=validate.Range(min=1))
    motivo = fields.String(required=True)


class PaqueteMonedasSchema(Schema):
    """Paquete de monedas configurado por el superadmin."""

    id = fields.Integer()
    nombre = fields.String()
    descripcion = fields.String(allow_none=True)
    cantidad = fields.Integer()
    bonus = fields.Integer()
    monedas_totales = fields.Method("get_monedas_totales")
    precio_cop = fields.Integer()
    precio_efectivo_cop = fields.Method("get_precio_efectivo")
    activo = fields.Boolean()
    en_oferta = fields.Boolean()
    oferta_vigente = fields.Method("get_oferta_vigente")
    precio_oferta_cop = fields.Integer(allow_none=True)
    oferta_desde = fields.DateTime(allow_none=True)
    oferta_hasta = fields.DateTime(allow_none=True)
    orden = fields.Integer()
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()

    def get_monedas_totales(self, obj) -> int:
        return int(obj.cantidad) + int(obj.bonus or 0)

    def get_precio_efectivo(self, obj) -> int:
        return obj.precio_efectivo()

    def get_oferta_vigente(self, obj) -> bool:
        return obj.oferta_vigente()


class PaqueteCreateSchema(Schema):
    """Alta de un paquete de monedas."""

    nombre = fields.String(required=True, validate=validate.Length(min=2, max=80))
    descripcion = fields.String(required=False, allow_none=True, validate=validate.Length(max=255))
    cantidad = fields.Integer(required=True, validate=validate.Range(min=1))
    bonus = fields.Integer(required=False, load_default=0, validate=validate.Range(min=0))
    precio_cop = fields.Integer(required=True, validate=validate.Range(min=1))
    activo = fields.Boolean(required=False, load_default=True)
    en_oferta = fields.Boolean(required=False, load_default=False)
    precio_oferta_cop = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1))
    oferta_desde = fields.DateTime(required=False, allow_none=True)
    oferta_hasta = fields.DateTime(required=False, allow_none=True)
    orden = fields.Integer(required=False, load_default=0)


class PaqueteUpdateSchema(Schema):
    """Edición parcial de un paquete de monedas."""

    nombre = fields.String(required=False, validate=validate.Length(min=2, max=80))
    descripcion = fields.String(required=False, allow_none=True, validate=validate.Length(max=255))
    cantidad = fields.Integer(required=False, validate=validate.Range(min=1))
    bonus = fields.Integer(required=False, validate=validate.Range(min=0))
    precio_cop = fields.Integer(required=False, validate=validate.Range(min=1))
    activo = fields.Boolean(required=False)
    en_oferta = fields.Boolean(required=False)
    precio_oferta_cop = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1))
    oferta_desde = fields.DateTime(required=False, allow_none=True)
    oferta_hasta = fields.DateTime(required=False, allow_none=True)
    orden = fields.Integer(required=False)


class CompraPaqueteSchema(Schema):
    """Registro de una compra de paquete."""

    id = fields.Integer()
    user_id = fields.Integer()
    paquete_id = fields.Integer(allow_none=True)
    monedas = fields.Integer()
    precio_cop = fields.Integer()
    pasarela = fields.String()
    estado = fields.String()
    referencia = fields.String(allow_none=True)
    creado_en = fields.DateTime()


class MovimientoMonedasSchema(Schema):
    """Movimiento del libro de monedas."""

    id = fields.Integer()
    user_id = fields.Integer()
    tipo = fields.String()
    cantidad = fields.Integer()
    saldo_resultante = fields.Integer()
    descripcion = fields.String(allow_none=True)
    referencia = fields.String(allow_none=True)
    paquete_id = fields.Integer(allow_none=True)
    vence_en = fields.DateTime(allow_none=True)
    creado_en = fields.DateTime()


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


class PaqueteReorderSchema(Schema):
    """Nuevo orden de paquetes: la posición en la lista es el orden final."""

    ids = fields.List(
        fields.Integer(), required=True, validate=validate.Length(min=1)
    )
