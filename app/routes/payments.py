"""Payments blueprint: pasarela de pagos y escrow (RF-08, RF-09 parcial)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.contract import Contract, EstadoContrato
from app.models.payment import Payment, EstadoPago
from app.schemas.payment import (
    PaymentCreateSchema,
    PaymentEstadoSchema,
    PaymentSchema,
    IncomeCertificateSchema,
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


def _meses_ventana(hoy):
    """Devuelve lista de (anio, mes) de los ultimos 12 meses, ascendente."""
    anio, mes = hoy.year, hoy.month
    ventana = []
    for i in range(11, -1, -1):
        m = mes - i
        a = anio
        while m <= 0:
            m += 12
            a -= 1
        ventana.append((a, m))
    return ventana


def _inicio_mes(anio, mes):
    from datetime import datetime

    return datetime(anio, mes, 1, 0, 0, 0)


def _mes_siguiente(anio, mes):
    mes += 1
    if mes > 12:
        mes = 1
        anio += 1
    return anio, mes


@blp.route("/certificado-ingresos")
class IncomeCertificate(MethodView):
    @jwt_required()
    @blp.response(200, IncomeCertificateSchema)
    def get(self):
        """RF-13: certificado de ingresos del proveedor (ultimos 12 meses)."""
        from datetime import datetime, timezone

        user = db.session.get(User, int(get_jwt_identity()))

        contratos_completados = Contract.query.filter_by(
            proveedor_id=user.id, estado=EstadoContrato.COMPLETADO
        ).all()

        pagos = (
            Payment.query.join(Contract, Payment.contract_id == Contract.id)
            .filter(
                Contract.proveedor_id == user.id,
                Payment.estado == EstadoPago.LIBERADO,
            )
            .all()
        )

        total_ingresos = sum((p.monto - p.comision) for p in pagos)

        # Historial: ultimos 12 meses (mes actual hacia atras), ascendente.
        hoy = datetime.utcnow()
        ventana = _meses_ventana(hoy)
        historial = []
        for (a, m) in ventana:
            inicio = _inicio_mes(a, m)
            fa, fm = _mes_siguiente(a, m)
            fin = _inicio_mes(fa, fm)

            ingreso = 0
            for p in pagos:
                ref = p.liberado_en or p.creado_en
                if ref is not None and inicio <= ref < fin:
                    ingreso += (p.monto - p.comision)

            servicios = 0
            for c in contratos_completados:
                ref = c.fin_en or c.creado_en
                if ref is not None and inicio <= ref < fin:
                    servicios += 1

            historial.append(
                {"mes": f"{a:04d}-{m:02d}", "ingreso": ingreso, "servicios": servicios}
            )

        promedio_mensual = round(total_ingresos / 12)
        calificacion_promedio = float(user.profile.calificacion_promedio or 0.0)
        verificado = bool(user.profile.verificado)
        nombre = user.nombre or user.email

        a0, m0 = ventana[0]
        periodo = {
            "desde": _inicio_mes(a0, m0).date().isoformat(),
            "hasta": hoy.date().isoformat(),
        }

        return {
            "nombre": nombre,
            "verificado": verificado,
            "calificacion_promedio": calificacion_promedio,
            "periodo": periodo,
            "total_ingresos": total_ingresos,
            "promedio_mensual": promedio_mensual,
            "servicios_completados": len(contratos_completados),
            "historial": historial,
        }
