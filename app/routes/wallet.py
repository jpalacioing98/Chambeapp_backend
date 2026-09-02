"""Wallet blueprint: billetera virtual, monedas, modalidades y hitos (RF-25, RF-26, RF-27, RF-29)."""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.wallet import Wallet, Transaction, Coin
from app.models.modalidad import Modalidad, Milestone
from app.models.contract import Contract
from app.models.solicitud import Solicitud
from app.schemas.wallet import (
    WalletSchema,
    WalletDepositSchema,
    WalletWithdrawSchema,
    TransactionSchema,
    CoinSchema,
    CoinBuySchema,
    CoinUseSchema,
    ModalidadSchema,
    ModalidadCreateSchema,
    MilestoneSchema,
    MilestoneCreateSchema,
    MilestoneActionSchema,
)
from app.services.wallet import (
    get_or_create_wallet,
    get_wallet,
    depositar,
    retirar,
    get_historial,
    get_saldo_monedas,
    comprar_monedas,
    usar_monedas,
    crear_modalidad,
    get_modalidad,
    crear_hitos,
    aprobar_hito,
    rechazar_hito,
    get_hitos,
    verificar_todos_aprobados,
    PAQUETES_MONEDAS,
)

blp = Blueprint("wallet", __name__, description="Billetera virtual y monedas (RF-25/27)")


def _es_admin(user_id: int) -> bool:
    user = db.session.get(User, user_id)
    return user is not None and user.rol in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN)


# --------------------------------------------------------------------------
# Billetera Virtual (RF-25)
# --------------------------------------------------------------------------

@blp.route("/")
class WalletDetail(MethodView):
    @jwt_required()
    @blp.response(200, WalletSchema)
    def get(self):
        """RF-25.1: consulta saldo y datos de billetera."""
        user_id = int(get_jwt_identity())
        wallet = get_or_create_wallet(user_id)
        db.session.commit()
        return wallet


@blp.route("/deposit")
class WalletDeposit(MethodView):
    @jwt_required()
    @blp.arguments(WalletDepositSchema)
    @blp.response(201, TransactionSchema)
    def post(self, data):
        """RF-25.5: deposita fondos en la billetera."""
        user_id = int(get_jwt_identity())
        try:
            tx = depositar(user_id, data["monto"], data.get("pasarela", "nequi"))
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return tx


@blp.route("/withdraw")
class WalletWithdraw(MethodView):
    @jwt_required()
    @blp.arguments(WalletWithdrawSchema)
    @blp.response(201, TransactionSchema)
    def post(self, data):
        """RF-25.3: retira fondos de la billetera."""
        user_id = int(get_jwt_identity())
        try:
            tx = retirar(user_id, data["monto"], data["cuenta_destino"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return tx


@blp.route("/history")
class WalletHistory(MethodView):
    @jwt_required()
    @blp.response(200, TransactionSchema(many=True))
    def get(self):
        """RF-25.6: historial de transacciones de la billetera."""
        user_id = int(get_jwt_identity())
        return get_historial(user_id)


# --------------------------------------------------------------------------
# Sistema de Monedas (RF-27)
# --------------------------------------------------------------------------

@blp.route("/coins")
class CoinsDetail(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self):
        """RF-27.5: consulta saldo de monedas por tipo."""
        user_id = int(get_jwt_identity())
        return get_saldo_monedas(user_id)


@blp.route("/coins/buy")
class CoinsBuy(MethodView):
    @jwt_required()
    @blp.arguments(CoinBuySchema)
    @blp.response(201, CoinSchema)
    def post(self, data):
        """RF-27.1: compra monedas con dinero real."""
        user_id = int(get_jwt_identity())
        try:
            coin = comprar_monedas(user_id, data["paquete"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return coin


@blp.route("/coins/use")
class CoinsUse(MethodView):
    @jwt_required()
    @blp.arguments(CoinUseSchema)
    @blp.response(200)
    def post(self, data):
        """RF-27.2: usa monedas (descuenta del saldo)."""
        user_id = int(get_jwt_identity())
        try:
            usar_monedas(user_id, data["cantidad"], data["motivo"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return {"mensaje": "Monedas descontadas exitosamente"}


@blp.route("/coins/packages")
class CoinsPackages(MethodView):
    @blp.response(200)
    def get(self):
        """Lista paquetes de monedas disponibles."""
        return PAQUETES_MONEDAS


# --------------------------------------------------------------------------
# Modalidades de Cobro (RF-26)
# --------------------------------------------------------------------------

@blp.route("/modalidades/<int:service_id>")
class ModalidadDetail(MethodView):
    @jwt_required()
    @blp.response(200, ModalidadSchema)
    def get(self, service_id):
        """RF-26.5: consulta modalidad de una solicitud."""
        return get_modalidad(service_id)

    @jwt_required()
    @blp.arguments(ModalidadCreateSchema)
    @blp.response(201, ModalidadSchema)
    def post(self, data, service_id):
        """RF-26.1: establece modalidad de cobro de una solicitud."""
        user_id = int(get_jwt_identity())
        solicitud = db.session.get(Solicitud, service_id)
        if solicitud is None:
            abort(404, message="La solicitud no existe.")
        if solicitud.solicitante_id != user_id and not _es_admin(user_id):
            abort(403, message="Solo el solicitante puede definir la modalidad.")

        try:
            modalidad = crear_modalidad(service_id, data["tipo"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return modalidad


# --------------------------------------------------------------------------
# Hitos de Pago (RF-29)
# --------------------------------------------------------------------------

@blp.route("/milestones/<int:contract_id>")
class MilestonesList(MethodView):
    @jwt_required()
    @blp.response(200, MilestoneSchema(many=True))
    def get(self, contract_id):
        """RF-29: consulta hitos de un contrato."""
        return get_hitos(contract_id)


@blp.route("/milestones/<int:contract_id>/create")
class MilestonesCreate(MethodView):
    @jwt_required()
    @blp.arguments(MilestoneCreateSchema)
    @blp.response(201, MilestoneSchema(many=True))
    def post(self, data, contract_id):
        """RF-29.1: crea hitos de pago para un contrato."""
        user_id = int(get_jwt_identity())
        contract = db.session.get(Contract, contract_id)
        if contract is None:
            abort(404, message="El contrato no existe.")
        if contract.solicitante_id != user_id and not _es_admin(user_id):
            abort(403, message="Solo el solicitante puede crear hitos.")

        try:
            hitos = crear_hitos(contract_id, data["hitos"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return hitos


@blp.route("/milestones/<int:hito_id>/action")
class MilestoneAction(MethodView):
    @jwt_required()
    @blp.arguments(MilestoneActionSchema)
    @blp.response(200, MilestoneSchema)
    def post(self, data, hito_id):
        """RF-29.2/29.4: aprueba o rechaza un hito de pago."""
        user_id = int(get_jwt_identity())
        hito = db.session.get(Milestone, hito_id)
        if hito is None:
            abort(404, message="El hito no existe.")

        contract = db.session.get(Contract, hito.contract_id)
        if contract.solicitante_id != user_id and not _es_admin(user_id):
            abort(403, message="Solo el solicitante puede aprobar/rechazar hitos.")

        try:
            if data["accion"] == "aprobar":
                hito = aprobar_hito(hito_id)
            elif data["accion"] == "rechazar":
                hito = rechazar_hito(hito_id)
            else:
                abort(400, message="Acción no válida.")
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return hito


@blp.route("/milestones/<int:contract_id>/check")
class MilestonesCheck(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, contract_id):
        """Verifica si todos los hitos están aprobados."""
        todos_aprobados = verificar_todos_aprobados(contract_id)
        hitos = get_hitos(contract_id)
        return {
            "todos_aprobados": todos_aprobados,
            "total_hitos": len(hitos),
            "aprobados": sum(1 for h in hitos if h.estado.value == "aprobado"),
        }
