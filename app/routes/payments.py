"""Payments blueprint: pasarela de pagos directos (RF-08, RF-09 parcial)."""

from flask import request, Response
from flask.views import MethodView
from flask import current_app
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
    NequiInfoSchema,
)
from app.services.payments import (
    crear_pago,
    confirmar_pago,
    liberar_pago,
    reembolsar,
    reintentar_pago,
    auto_liberar_vencidos,
)
from app.services.pagination import paginate_query
from app.schemas.payment import PaymentSchema

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

        # RF-08 (Nequi): por defecto la pasarela es 'nequi'.
        pasarela = data.get("pasarela") or "nequi"

        try:
            payment = crear_pago(contract.id, data["monto"], pasarela=pasarela)
        except ValueError as e:
            abort(400, message=str(e))

        db.session.commit()
        return payment


@blp.route("/nequi")
class NequiInfo(MethodView):
    @blp.response(200, NequiInfoSchema)
    def get(self):
        """RF-08 (Nequi): expone el numero y titular de la plataforma para
        que el usuario realice la transferencia manual (sin pasarela externa)."""
        return {
            "numero": current_app.config["NEQUI_NUMBER"],
            "titular": current_app.config["NEQUI_TITULAR"],
        }


@blp.route("/<int:payment_id>/confirm")
class PaymentConfirm(MethodView):
    @jwt_required()
    @blp.response(200, PaymentSchema)
    def post(self, payment_id):
        """RF-08.3: confirma el cargo (simula pasarela ok) -> pago directo."""
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
        """RF-08.6: libera el pago al proveedor (pago directo)."""
        user_id = int(get_jwt_identity())
        payment = db.session.get(Payment, payment_id)
        if payment is None:
            abort(404, message="El pago no existe.")
        contract = db.session.get(Contract, payment.contract_id)
        # Solo el solicitante (quien pagó) o admin liberan.
        if not _es_admin(user_id) and contract.solicitante_id != user_id:
            abort(403, message="No autorizado para liberar este pago.")

        try:
            payment = liberar_pago(payment.id)
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
        o solicitante del contrato asociado.

        Supports optional page/per_page query params for pagination (P2-4).
        If no params, returns all items (backward compatible).
        """
        user_id = int(get_jwt_identity())
        query = (
            Payment.query.join(Contract, Payment.contract_id == Contract.id)
            .filter(
                (Contract.solicitante_id == user_id) | (Contract.proveedor_id == user_id)
            )
            .order_by(Payment.creado_en.desc())
        )

        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        if isinstance(result, list):
            return result
        return result


@blp.route("/admin/auto-release")
class PaymentAdminAutoRelease(MethodView):
    @jwt_required()
    @blp.response(200)
    def post(self):
        """Helper admin: ejecuta auto_liberar_vencidos (pagos directos)."""
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
                Payment.estado == EstadoPago.COMPLETADO,
            )
            .all()
        )

        total_ingresos = sum((p.monto - p.comision_pds) for p in pagos)

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
                    ingreso += (p.monto - p.comision_pds)

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


@blp.route("/certificado-ingresos/pdf")
class IncomeCertificatePDF(MethodView):
    @jwt_required()
    def get(self):
        """P2-3: genera PDF del certificado de ingresos."""
        from app.services.exports import generar_pdf_certificado

        # Reuse the same data collection as the JSON endpoint
        user = db.session.get(User, int(get_jwt_identity()))
        contratos_completados = Contract.query.filter_by(
            proveedor_id=user.id, estado=EstadoContrato.COMPLETADO
        ).all()

        pagos = (
            Payment.query.join(Contract, Payment.contract_id == Contract.id)
            .filter(
                Contract.proveedor_id == user.id,
                Payment.estado == EstadoPago.COMPLETADO,
            )
            .all()
        )

        total_ingresos = sum((p.monto - p.comision_pds) for p in pagos)

        from datetime import datetime
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
                    ingreso += (p.monto - p.comision_pds)

            servicios = 0
            for c in contratos_completados:
                ref = c.fin_en or c.creado_en
                if ref is not None and inicio <= ref < fin:
                    servicios += 1

            historial.append(
                {"mes": f"{a:04d}-{m:02d}", "ingreso": ingreso, "servicios": servicios}
            )

        a0, m0 = ventana[0]
        periodo = {
            "desde": _inicio_mes(a0, m0).date().isoformat(),
            "hasta": hoy.date().isoformat(),
        }

        data = {
            "nombre": user.nombre or user.email,
            "verificado": bool(user.profile.verificado),
            "calificacion_promedio": float(user.profile.calificacion_promedio or 0.0),
            "periodo": periodo,
            "total_ingresos": total_ingresos,
            "promedio_mensual": round(total_ingresos / 12),
            "servicios_completados": len(contratos_completados),
            "historial": historial,
        }

        pdf_bytes = generar_pdf_certificado(data)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=certificado_ingresos.pdf"},
        )


@blp.route("/certificado-ingresos/csv")
class IncomeCertificateCSV(MethodView):
    @jwt_required()
    def get(self):
        """P2-3: genera CSV del historial de pagos del certificado de ingresos."""
        from app.services.exports import generar_csv_historial

        user = db.session.get(User, int(get_jwt_identity()))
        pagos = (
            Payment.query.join(Contract, Payment.contract_id == Contract.id)
            .filter(
                Contract.proveedor_id == user.id,
                Payment.estado == EstadoPago.COMPLETADO,
            )
            .all()
        )

        csv_bytes = generar_csv_historial(pagos)
        return Response(
            csv_bytes,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=historial_pagos.csv"},
        )


@blp.route("/history/csv")
class PaymentHistoryCSV(MethodView):
    @jwt_required()
    def get(self):
        """P2-3: genera CSV del historial completo de pagos del usuario."""
        from app.services.exports import generar_csv_historial

        user_id = int(get_jwt_identity())
        pagos = (
            Payment.query.join(Contract, Payment.contract_id == Contract.id)
            .filter(
                (Contract.solicitante_id == user_id) | (Contract.proveedor_id == user_id)
            )
            .order_by(Payment.creado_en.desc())
            .all()
        )

        csv_bytes = generar_csv_historial(pagos)
        return Response(
            csv_bytes,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=historial_pagos.csv"},
        )
