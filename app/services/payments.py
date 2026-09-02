"""Service layer: pasarela de pagos directos (RF-08).

Implementa un gateway abstracto (Protocol) para que la logica de negocio sea
testable sin claves reales de MercadoPago. Se incluye MockGateway (siempre ok)
y un stub comentado de MercadoPagoGateway para iteracion futura.

Flujo: pago directo sin escrow — al confirmar, el monto neto se transfiere
al proveedor inmediatamente.
"""

from datetime import datetime, timedelta, timezone
import uuid

from app.config import (
    COMMISSION_EXEMPT_THRESHOLD,
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
def crear_pago(
    contract_id: int,
    monto: int,
    pasarela: str = "nequi",
    gateway: PaymentGateway = None,
) -> Payment:
    """RF-08.1: crea un pago asociado a un contrato completado.

    - Valida que el contrato exista y su estado sea 'completado'.
    - Calcula comisiones: 
      - PDS: 12% si monto >= COMMISSION_EXEMPT_THRESHOLD
      - Solicitante: 8% si monto >= COMMISSION_EXEMPT_THRESHOLD
    - Crea Payment en estado 'pendiente'.
    - Por defecto la pasarela es 'nequi' (transferencia manual). Para
      pagos 'nequi' se genera una referencia tipo NEQ-XXXX.
    """
    contract = db.session.get(Contract, contract_id)
    if contract is None:
        raise ValueError("El contrato no existe.")
    if contract.estado != EstadoContrato.COMPLETADO:
        raise ValueError("Solo se puede pagar un contrato completado.")

    gateway = gateway or DEFAULT_GATEWAY

    # Calcular comisiones
    if monto < COMMISSION_EXEMPT_THRESHOLD:
        comision_pds = 0
        comision_solicitante = 0
    else:
        comision_pds = round(monto * 0.12)  # 12% para PDS
        comision_solicitante = round(monto * 0.08)  # 8% para solicitante

    # Referencia de pasarela: Nequi usa NEQ-XXXX; el gateway mock la fija en confirm.
    referencia = f"NEQ-{uuid.uuid4().hex[:8].upper()}" if pasarela == "nequi" else None

    payment = Payment(
        contract_id=contract.id,
        monto=monto,
        comision_pds=comision_pds,
        comision_solicitante=comision_solicitante,
        estado=EstadoPago.PENDIENTE,
        pasarela=pasarela,
        referencia_pasarela=referencia,
    )
    db.session.add(payment)
    db.session.flush()
    return payment


def confirmar_pago(payment_id: int, gateway: PaymentGateway = None) -> Payment:
    """RF-08.3: confirma el cargo en la pasarela y completa el pago.

    Estado pendiente -> completado. Ejecuta el gateway; si falla pasa a
    'fallido' con referencia de error (RF-08.5 reintentable).
    
    El pago se completa directamente y el monto neto
    (monto - comision_pds) se transfiere al proveedor.
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

    payment.estado = EstadoPago.COMPLETADO
    payment.referencia_pasarela = ref
    payment.liberado_en = datetime.now(timezone.utc)
    db.session.commit()
    return payment


def reembolsar(payment_id: int, motivo: str) -> Payment:
    """RF-08.7: reembolsa el pago (retracto, no-show 100%, cancelacion)."""
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("El pago no existe.")
    if payment.estado in (EstadoPago.REEMBOLSADO, EstadoPago.FALLIDO):
        raise ValueError("No se reembolsa un pago ya reembolsado o fallido.")

    payment.estado = EstadoPago.REEMBOLSADO
    payment.motivo_reembolso = motivo
    db.session.commit()
    return payment


def liberar_pago(payment_id: int) -> Payment:
    """Libera un pago al proveedor (pago directo, sin escrow).

    Si el pago esta pendiente, lo confirma. Si ya esta completado, retorna
    sin cambios. Equivalente al antiguo liberar_escrow.
    """
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("El pago no existe.")
    if payment.estado == EstadoPago.PENDIENTE:
        return confirmar_pago(payment_id)
    if payment.estado in (EstadoPago.COMPLETADO, EstadoPago.REEMBOLSADO):
        return payment
    raise ValueError(
        f"No se puede liberar un pago en estado '{payment.estado.value}'."
    )


def auto_liberar_vencidos() -> int:
    """Auto-libera pagos pendientes con mas de 48h (RF-08.6 simplificado).

    En el modelo de pago directo, simplemente confirma pagos pendientes
    vencidos. Retorna el numero de pagos liberados.
    """
    from app.config import ESCROW_AUTO_RELEASE_HOURS

    cutoff = datetime.now(timezone.utc) - timedelta(hours=ESCROW_AUTO_RELEASE_HOURS)
    pendientes = Payment.query.filter(
        Payment.estado == EstadoPago.PENDIENTE,
        Payment.creado_en < cutoff,
    ).all()
    liberados = 0
    for p in pendientes:
        try:
            confirmar_pago(p.id)
            liberados += 1
        except (ValueError, RuntimeError):
            continue
    return liberados


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

    payment.estado = EstadoPago.COMPLETADO
    payment.referencia_pasarela = ref
    payment.liberado_en = datetime.now(timezone.utc)
    db.session.commit()
    return payment
