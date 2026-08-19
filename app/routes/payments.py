"""Payments blueprint: pasarela de pagos y escrow (RF-08, RF-09 parcial)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.contract import Contract
from app.models.payment import Payment, EstadoPago
from app.schemas.payment import (
    PaymentCreateSchema,
    PaymentEstadoSchema,
    PaymentSchema,
)
from app.services.payments import (
    crear_pago,
    confirmar_pago,
    liberar_escrow,
    reembolsar,
    reintentar_pago,
    auto_liberar_vencidos,
)

blp = Blueprint("payments", __name__, description="Pasarela de pagos (RF-08)")


def _es_admin(user_id: int) -> bool:
    user = db.session.get(User, user_id)
    return user is not None and user.rol in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN)


def _participa_en_contrato(user_id: int, contract: Contract) -> bool:
    return user_id in (contract.solicitante_id, contract.proveedor_id)


@blp.route("/")
class PaymentList(MethodView):
    @jwt_required()
    @blp.arguments(PaymentCreateSchema)
    @blp.response(201, PaymentSchema)
    def post(self, data):
        """RF-08.1: crea un pago para un contrato completado."""
        user_id = int(get_jwt_identity())
        contract = db.session.get(Contract, data["contract_id"])
        if contract is None:
            abort(404, message="El contrato no existe.")

        # Solo el solicitante (quien paga) o un admin pueden crear el pago.
        if not _es_admin(user_id) and contract.solicitante_id != user_id:
            abort(403, message="No puedes pagar este contrato.")

        try:
            payment = crear_pago(contract.id, data["monto"])
        except ValueError as e:
            abort(400, message=str(e))

        db.session.commit()
        return payment


@blp.route("/<int:payment_id>/confirm")
class PaymentConfirm(MethodView):
    @jwt_required()
    @blp.response(200, PaymentSchema)
    def post(self, payment_id):
        """RF-08.3: confirma el cargo (simula pasarela ok) -> en_escrow."""
        user_id = int(get_jwt_identity())
        payment = db.session.get(Payment, payment_id)
        if payment is None:
            abort(404, message="El pago no existe.")
        contract = db.session.get(Contract, payment.contract_id)
        if not _es_admin(user_id) and contract.solicitante_id != user_id:
            abort(403, message="No autorizado para confirmar este pago.")

        try:
            payment = confirmar_pago(payment.id)
        except ValueError as e:
            abort(400, message=str(e))
        except RuntimeError as e:
            abort(502, message=str(e))
        return payment


@blp.route("/<int:payment_id>/release")
class PaymentRelease(MethodView):
    @jwt_required()
    @blp.response(200, PaymentSchema)
    def post(self, payment_id):
        """RF-08.6: libera el escrow al proveedor."""
        user_id = int(get_jwt_identity())
        payment = db.session.get(Payment, payment_id)
        if payment is None:
            abort(404, message="El pago no existe.")
        contract = db.session.get(Contract, payment.contract_id)
        # Solo el solicitante (quien pagó) o admin liberan.
        if not _es_admin(user_id) and contract.solicitante_id != user_id:
            abort(403, message="No autorizado para liberar este pago.")

        try:
            payment = liberar_escrow(payment.id)
        except ValueError as e:
            abort(400, message=str(e))
        return payment


@blp.route("/<int:payment_id>/refund")
class PaymentRefund(MethodView):
    @jwt_required()
    @blp.arguments(PaymentEstadoSchema)
    @blp.response(200, PaymentSchema)
    def post(self, data, payment_id):
        """RF-08.7: reembolsa el pago (retracto, no-show, cancelacion)."""
        user_id = int(get_jwt_identity())
        payment = db.session.get(Payment, payment_id)
        if payment is None:
            abort(404, message="El pago no existe.")
        contract = db.session.get(Contract, payment.contract_id)
        if not _es_admin(user_id) and contract.solicitante_id != user_id:
            abort(403, message="No autorizado para reembolsar este pago.")

        motivo = data.get("motivo_reembolso")
        if not motivo or not str(motivo).strip():
            abort(400, message="Se requiere un motivo de reembolso.")

        try:
            payment = reembolsar(payment.id, motivo)
        except ValueError as e:
            abort(400, message=str(e))
        return payment


@blp.route("/<int:payment_id>/retry")
class PaymentRetry(MethodView):
    @jwt_required()
    @blp.response(200, PaymentSchema)
    def post(self, payment_id):
        """RF-08.5: reintenta un pago fallido."""
        user_id = int(get_jwt_identity())
        payment = db.session.get(Payment, payment_id)
        if payment is None:
            abort(404, message="El pago no existe.")
        contract = db.session.get(Contract, payment.contract_id)
        if not _es_admin(user_id) and contract.solicitante_id != user_id:
            abort(403, message="No autorizado para reintentar este pago.")

        try:
            payment = reintentar_pago(payment.id)
        except ValueError as e:
            abort(400, message=str(e))
        except RuntimeError as e:
            abort(502, message=str(e))
        return payment


@blp.route("/<int:payment_id>")
class PaymentDetail(MethodView):
    @jwt_required()
    @blp.response(200, PaymentSchema)
    def get(self, payment_id):
        """Detalle de un pago (solo participantes del contrato o admin)."""
        user_id = int(get_jwt_identity())
        payment = db.session.get(Payment, payment_id)
        if payment is None:
            abort(404, message="El pago no existe.")
        contract = db.session.get(Contract, payment.contract_id)
        if not _es_admin(user_id) and not _participa_en_contrato(user_id, contract):
            abort(403, message="No participas en este pago.")
        return payment


@blp.route("/mine")
class MyPayments(MethodView):
    @jwt_required()
    @blp.response(200, PaymentSchema(many=True))
    def get(self):
        """RF-09 parcial: historial de pagos donde el usuario es proveedor
        o solicitante del contrato asociado."""
        user_id = int(get_jwt_identity())
        return (
            Payment.query.join(Contract, Payment.contract_id == Contract.id)
            .filter(
                (Contract.solicitante_id == user_id) | (Contract.proveedor_id == user_id)
            )
            .order_by(Payment.creado_en.desc())
            .all()
        )


@blp.route("/admin/auto-release")
class PaymentAdminAutoRelease(MethodView):
    @jwt_required()
    @blp.response(200)
    def post(self):
        """Helper admin: ejecuta auto_liberar_vencidos (RF-08.6)."""
        user_id = int(get_jwt_identity())
        if not _es_admin(user_id):
            abort(403, message="Requiere rol admin.")
        liberados = auto_liberar_vencidos()
        return {"liberados": liberados}
