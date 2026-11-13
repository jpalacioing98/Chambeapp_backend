"""Wallet blueprint: billetera virtual, monedas e hitos (RF-25, RF-27, RF-29)."""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.wallet import Wallet, Transaction, Coin
from app.models.modalidad import Milestone
from app.models.contract import Contract
from app.schemas.wallet import (
    WalletSchema,
    WalletWithdrawSchema,
    TransactionSchema,
    CoinSchema,
    CoinBuySchema,
    CoinUseSchema,
    PaqueteMonedasSchema,
    PaqueteCreateSchema,
    PaqueteUpdateSchema,
    PaqueteReorderSchema,
    CompraPaqueteSchema,
    MovimientoMonedasSchema,
    MilestoneSchema,
    MilestoneCreateSchema,
    MilestoneActionSchema,
)
from app.services.wallet import (
    get_or_create_wallet,
    get_wallet,
    retirar,
    get_historial,
    get_saldo_monedas,
    get_movimientos_monedas,
    get_paquetes,
    crear_paquete,
    actualizar_paquete,
    eliminar_paquete,
    reordenar_paquetes,
    activar_paquete,
    comprar_paquete,
    usar_monedas,
    get_resumen_financiero,
    crear_hitos,
    aprobar_hito,
    rechazar_hito,
    get_hitos,
    verificar_todos_aprobados,
)
from app.services.pagination import paginate_query

blp = Blueprint("wallet", __name__, description="Billetera virtual y monedas (RF-25/27)")


def _es_admin(user_id: int) -> bool:
    user = db.session.get(User, user_id)
    return user is not None and user.rol in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN)


def _es_superadmin(user_id: int) -> bool:
    user = db.session.get(User, user_id)
    return user is not None and user.rol == RolUsuario.SUPERADMIN


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


@blp.route("/withdraw")
class WalletWithdraw(MethodView):
    @jwt_required()
    @blp.arguments(WalletWithdrawSchema)
    @blp.response(201, TransactionSchema)
    def post(self, data):
        """RF-25.3: retira fondos COP de la billetera."""
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
        """RF-25.6: historial de transacciones COP de la billetera."""
        user_id = int(get_jwt_identity())
        wallet = get_wallet(user_id)
        query = Transaction.query.filter_by(wallet_id=wallet.id)

        page = request.args.get("page")
        per_page = request.args.get("per_page")
        return paginate_query(query, page=page, per_page=per_page)


# --------------------------------------------------------------------------
# Sistema de Monedas (RF-27)
# --------------------------------------------------------------------------

@blp.route("/coins")
class CoinsDetail(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self):
        """RF-27.5: saldo actual y totales de monedas."""
        user_id = int(get_jwt_identity())
        return get_saldo_monedas(user_id)


@blp.route("/coins/movimientos")
class CoinsMovements(MethodView):
    @jwt_required()
    @blp.response(200, MovimientoMonedasSchema(many=True))
    def get(self):
        """Historial de movimientos de monedas."""
        user_id = int(get_jwt_identity())
        limite = request.args.get("limite", 100)
        try:
            limite_int = int(limite)
        except (TypeError, ValueError):
            limite_int = 100
        return get_movimientos_monedas(user_id, limite_int)


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


@blp.route("/paquetes")
class PaquetesList(MethodView):
    @jwt_required()
    @blp.response(200, PaqueteMonedasSchema(many=True))
    def get(self):
        """Paquetes de monedas activos para comprar."""
        return get_paquetes(solo_activos=True)


@blp.route("/coins/buy")
class CoinsBuy(MethodView):
    @jwt_required()
    @blp.arguments(CoinBuySchema)
    @blp.response(201)
    def post(self, data):
        """Compra un paquete de monedas (pasarela simulada)."""
        user_id = int(get_jwt_identity())
        try:
            compra = comprar_paquete(user_id, data["paquete_id"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return {
            "compra": CompraPaqueteSchema().dump(compra),
            "saldo": get_saldo_monedas(user_id),
        }


@blp.route("/resumen")
class WalletResumen(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self):
        """Situación financiera general y por rol."""
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if user is None:
            abort(404, message="Usuario no encontrado.")
        return get_resumen_financiero(user_id, user.rol.value)


# --------------------------------------------------------------------------
# Paquetes de monedas — administración exclusiva del Superadmin
# --------------------------------------------------------------------------

@blp.route("/admin/paquetes")
class AdminPaquetes(MethodView):
    @jwt_required()
    @blp.response(200, PaqueteMonedasSchema(many=True))
    def get(self):
        user_id = int(get_jwt_identity())
        if not _es_superadmin(user_id):
            abort(403, message="Solo el superadministrador gestiona los paquetes.")
        return get_paquetes(solo_activos=False)

    @jwt_required()
    @blp.arguments(PaqueteCreateSchema)
    @blp.response(201, PaqueteMonedasSchema)
    def post(self, data):
        user_id = int(get_jwt_identity())
        if not _es_superadmin(user_id):
            abort(403, message="Solo el superadministrador gestiona los paquetes.")
        try:
            paquete = crear_paquete(data, creado_por=user_id)
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return paquete


@blp.route("/admin/paquetes/<int:paquete_id>")
class AdminPaqueteDetail(MethodView):
    @jwt_required()
    @blp.arguments(PaqueteUpdateSchema)
    @blp.response(200, PaqueteMonedasSchema)
    def patch(self, data, paquete_id):
        user_id = int(get_jwt_identity())
        if not _es_superadmin(user_id):
            abort(403, message="Solo el superadministrador gestiona los paquetes.")
        try:
            paquete = actualizar_paquete(paquete_id, data)
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return paquete

    @jwt_required()
    @blp.response(200)
    def delete(self, paquete_id):
        user_id = int(get_jwt_identity())
        if not _es_superadmin(user_id):
            abort(403, message="Solo el superadministrador gestiona los paquetes.")
        try:
            paquete = eliminar_paquete(paquete_id)
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return {"mensaje": "Paquete desactivado", "id": paquete.id}


@blp.route("/admin/paquetes/reordenar")
class AdminPaquetesReordenar(MethodView):
    @jwt_required()
    @blp.arguments(PaqueteReorderSchema)
    @blp.response(200, PaqueteMonedasSchema(many=True))
    def post(self, data):
        """Reordena todos los paquetes según la lista de ids (posición = orden)."""
        user_id = int(get_jwt_identity())
        if not _es_superadmin(user_id):
            abort(403, message="Solo el superadministrador gestiona los paquetes.")
        try:
            paquetes = reordenar_paquetes(data["ids"])
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return paquetes


@blp.route("/admin/paquetes/<int:paquete_id>/activar")
class AdminPaqueteActivar(MethodView):
    @jwt_required()
    @blp.response(200, PaqueteMonedasSchema)
    def post(self, paquete_id):
        """Reactiva un paquete desactivado."""
        user_id = int(get_jwt_identity())
        if not _es_superadmin(user_id):
            abort(403, message="Solo el superadministrador gestiona los paquetes.")
        try:
            paquete = activar_paquete(paquete_id)
        except ValueError as e:
            abort(400, message=str(e))
        db.session.commit()
        return paquete


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


@blp.route("/tarifas")
class TarifasUsuario(MethodView):
    @jwt_required()
    @blp.doc(summary="Tarifas de cobro vigentes")
    def get(self):
        """Precios en monedas que ve el usuario (contratos y anuncios)."""
        from app.services.cobros import get_config_publica

        return get_config_publica()
