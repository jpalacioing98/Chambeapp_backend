"""Service layer: pasarela de pagos y ciclo de escrow (RF-08).

Implementa un gateway abstracto (Protocol) para que la logica de negocio sea
testable sin claves reales de MercadoPago. Se incluye MockGateway (siempre ok)
y un stub comentado de MercadoPagoGateway para iteracion futura.
"""

from datetime import datetime, timedelta, timezone

from app.config import (
    COMMISSION_EXEMPT_THRESHOLD,
    COMMISSION_RATE,
    ESCROW_AUTO_RELEASE_HOURS,
)
from app.extensions import db
from app.models.contract import Contract, EstadoContrato
from app.models.payment import Payment, EstadoPago


# --------------------------------------------------------------------------
# Gateway abstracto
# --------------------------------------------------------------------------
class PaymentGateway:
    """Protocolo de pasarela de pago.

    Implementaciones concretas (MockGateway, MercadoPagoGateway) deben
    proveer ``charge(payment) -> (ok: bool, referencia_o_error: str)``.
    """

    def charge(self, payment: Payment):
        raise NotImplementedError


class MockGateway(PaymentGateway):
    """Pasarela mock: siempre retorna exito con referencia fake (testable)."""

    def charge(self, payment: Payment):
        ref = f"MOCK-{payment.id or 0}-{int(datetime.now(timezone.utc).timestamp())}"
        return True, ref


# --------------------------------------------------------------------------
# Stub para iteracion futura (MercadoPago real). NO activo en esta iteracion.
# --------------------------------------------------------------------------
# class MercadoPagoGateway(PaymentGateway):
#     """Integracion real con MercadoPago (PSE / tarjeta). Requiere claves."""
#     def __init__(self, access_token: str):
#         import mercadopago
#         self.sdk = mercadopago.SDK(access_token)
#
#     def charge(self, payment: Payment):
#         preference = {
#             "items": [{
#                 "title": f"ChambeApp orden {payment.order_id}",
#                 "quantity": 1,
#                 "currency_id": "COP",
#                 "unit_price": float(payment.monto),
#             }],
#             "external_reference": str(payment.id),
#         }
#         result = self.sdk.preference().create(preference)
#         if result["status"] == 201:
#             return True, result["response"]["id"]
#         return False, result.get("message", "error_mercadopago")


# Gateway por defecto de la plataforma (mock hasta iteracion con claves reales).
DEFAULT_GATEWAY = MockGateway()


# --------------------------------------------------------------------------
# Operaciones de negocio
# --------------------------------------------------------------------------
def crear_pago(contract_id: int, monto: int, gateway: PaymentGateway = None) -> Payment:
    """RF-08.1: crea un pago asociado a un contrato completado.

    - Valida que el contrato exista y su estado sea 'completado'.
    - Calcula comision: 0 si monto < COMMISSION_EXEMPT_THRESHOLD,
      sino round(monto * COMMISSION_RATE) (T&C §7.1).
    - Crea Payment en estado 'pendiente'.
    """
    contract = db.session.get(Contract, contract_id)
    if contract is None:
        raise ValueError("El contrato no existe.")
    if contract.estado != EstadoContrato.COMPLETADO:
        raise ValueError("Solo se puede pagar un contrato completado.")

    gateway = gateway or DEFAULT_GATEWAY

    if monto < COMMISSION_EXEMPT_THRESHOLD:
        comision = 0
    else:
        comision = round(monto * COMMISSION_RATE)

    payment = Payment(
        contract_id=contract.id,
        monto=monto,
        comision=comision,
        estado=EstadoPago.PENDIENTE,
        pasarela=getattr(gateway, "name", "mock"),
    )
    db.session.add(payment)
    db.session.flush()
    return payment


def confirmar_pago(payment_id: int, gateway: PaymentGateway = None) -> Payment:
    """RF-08.3: confirma el cargo en la pasarela y retiene en escrow.

    Estado pendiente -> en_escrow. Ejecuta el gateway; si falla pasa a
    'fallido' con referencia de error (RF-08.5 reintentable).
    """
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("El pago no existe.")
    if payment.estado != EstadoPago.PENDIENTE:
        raise ValueError("Solo se confirma un pago en estado 'pendiente'.")

    gateway = gateway or DEFAULT_GATEWAY
    ok, ref = gateway.charge(payment)
    if not ok:
        payment.estado = EstadoPago.FALLIDO
        payment.referencia_pasarela = ref
        db.session.commit()
        raise RuntimeError(f"Pasarela rechazó el pago: {ref}")

    payment.estado = EstadoPago.EN_ESCROW
    payment.referencia_pasarela = ref
    db.session.commit()
    return payment


def liberar_escrow(payment_id: int) -> Payment:
    """RF-08.6: libera el escrow al proveedor (estado en_escrow -> liberado)."""
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("El pago no existe.")
    if payment.estado != EstadoPago.EN_ESCROW:
        raise ValueError("Solo se libera un pago en estado 'en_escrow'.")

    payment.estado = EstadoPago.LIBERADO
    payment.liberado_en = datetime.now(timezone.utc)
    db.session.commit()
    return payment


def reembolsar(payment_id: int, motivo: str) -> Payment:
    """RF-08.7: reembolsa el pago (retracto, no-show 100%, cancelacion)."""
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("El pago no existe.")
    if payment.estado in (EstadoPago.LIBERADO, EstadoPago.REEMBOLSADO):
        raise ValueError("No se reembolsa un pago ya liberado o reembolsado.")

    payment.estado = EstadoPago.REEMBOLSADO
    payment.motivo_reembolso = motivo
    db.session.commit()
    return payment


def reintentar_pago(payment_id: int, gateway: PaymentGateway = None) -> Payment:
    """RF-08.5: reintenta un pago fallido ejecutando la pasarela de nuevo."""
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("El pago no existe.")
    if payment.estado != EstadoPago.FALLIDO:
        raise ValueError("Solo se reintenta un pago en estado 'fallido'.")

    gateway = gateway or DEFAULT_GATEWAY
    ok, ref = gateway.charge(payment)
    if not ok:
        payment.referencia_pasarela = ref
        db.session.commit()
        raise RuntimeError(f"Reintento falló: {ref}")

    payment.estado = EstadoPago.EN_ESCROW
    payment.referencia_pasarela = ref
    db.session.commit()
    return payment


def auto_liberar_vencidos(now: datetime = None) -> int:
    """RF-08.6: libera escrows con >48h desde confirmacion y sin queja.

    Devuelve el numero de pagos liberados. (Celery lo programara despues.)
    """
    now = now or datetime.now(timezone.utc)
    limite = now - timedelta(hours=ESCROW_AUTO_RELEASE_HOURS)

    vencidos = (
        Payment.query.filter(Payment.estado == EstadoPago.EN_ESCROW)
        .filter(Payment.actualizado_en <= limite)
        .all()
    )
    count = 0
    for p in vencidos:
        p.estado = EstadoPago.LIBERADO
        p.liberado_en = now
        count += 1
    if count:
        db.session.commit()
    return count
