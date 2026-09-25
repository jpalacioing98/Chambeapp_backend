"""Blueprint de métodos de pago vinculados (RF-08, configuración de pago).

Endpoints (JWT requerido):
  GET    /metodos-pago            -> lista (la billetera virtual SIEMPRE va primera).
  POST   /metodos-pago            -> vincula una cuenta bancaria (banco libre + número).
  PATCH  /metodos-pago/<id>/principal -> marca el método como principal.
  DELETE /metodos-pago/<id>       -> desvincula (la billetera NO se elimina).
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.payment_method import MetodoPago
from app.schemas.payment_method import (
    MetodoPagoCreateSchema,
    MetodoPagoSchema,
    MessageResponseSchema,
)

blp = Blueprint("metodos_pago", __name__, description="Métodos de pago del usuario")


def _metodos(user_id: int):
    return MetodoPago.query.filter_by(user_id=user_id).order_by(
        MetodoPago.id
    ).all()


def _saldo_wallet(user_id: int):
    try:
        from app.models.wallet import Wallet
        wallet = Wallet.query.filter_by(user_id=user_id).first()
        return wallet.saldo if wallet else 0.0
    except Exception:
        return None


def _asegurar_billetera(user_id: int) -> MetodoPago:
    """La primera método SIEMPRE es la billetera virtual que crea el sistema.

    Solo es principal si no hay otro método con ese rol (no pisa al que el
    usuario ya marcó como principal)."""
    billetera = MetodoPago.query.filter_by(user_id=user_id, tipo="billetera").first()
    if billetera is None:
        existe_principal = (
            MetodoPago.query.filter_by(user_id=user_id, es_principal=True).first()
            is not None
        )
        billetera = MetodoPago(
            user_id=user_id,
            tipo="billetera",
            banco="ChambeApp",
            numero_cuenta=None,
            es_principal=not existe_principal,
        )
        db.session.add(billetera)
        db.session.commit()
    return billetera


def _serializar(m: MetodoPago) -> dict:
    d = {
        "id": m.id,
        "tipo": m.tipo,
        "banco": m.banco,
        "numero_cuenta": m.numero_cuenta,
        "es_principal": m.es_principal,
        "creado_en": m.creado_en,
    }
    if m.tipo == "billetera":
        d["saldo"] = _saldo_wallet(m.user_id)
    return d


@blp.route("")
class MetodosPagoList(MethodView):
    @jwt_required()
    @blp.response(200, MetodoPagoSchema(many=True))
    def get(self):
        """Lista los métodos de pago: la billetera virtual creada por el
        sistema es siempre el primer elemento; siguen los vinculados."""
        user_id = int(get_jwt_identity())
        billetera = _asegurar_billetera(user_id)
        metodos = _metodos(user_id)
        if not metodos or metodos[0].id != billetera.id:
            metodos = [billetera] + [m for m in metodos if m.id != billetera.id]
        return [_serializar(m) for m in metodos]

    @jwt_required()
    @blp.arguments(MetodoPagoCreateSchema)
    @blp.response(201, MetodoPagoSchema)
    def post(self, data):
        """Vincula una cuenta bancaria (banco libre + número de cuenta)."""
        user_id = int(get_jwt_identity())
        db.get_or_404(User, user_id)

        # El primer método vinculado pasa a ser principal automáticamente.
        tiene_vinculado = MetodoPago.query.filter_by(
            user_id=user_id, tipo="banco"
        ).first() is not None

        metodo = MetodoPago(
            user_id=user_id,
            tipo="banco",
            banco=data["banco"],
            numero_cuenta=data["numero_cuenta"],
            es_principal=not tiene_vinculado,
        )
        db.session.add(metodo)
        db.session.commit()
        return _serializar(metodo)


@blp.route("/<int:metodo_id>/principal")
class MetodoPrincipal(MethodView):
    @jwt_required()
    @blp.response(200, MetodoPagoSchema)
    def patch(self, metodo_id):
        """Marca un método propio como principal (el resto deja de serlo)."""
        user_id = int(get_jwt_identity())
        metodo = db.get_or_404(MetodoPago, metodo_id)
        if metodo.user_id != user_id:
            abort(403, message="No puedes modificar este método de pago.")

        for m in _metodos(user_id):
            m.es_principal = m.id == metodo_id
        db.session.commit()
        return _serializar(metodo)


@blp.route("/<int:metodo_id>")
class MetodoPagoDetail(MethodView):
    @jwt_required()
    @blp.response(200, MessageResponseSchema)
    def delete(self, metodo_id):
        """Desvincula un método propio (la billetera del sistema NO se elimina)."""
        user_id = int(get_jwt_identity())
        metodo = db.get_or_404(MetodoPago, metodo_id)
        if metodo.user_id != user_id:
            abort(403, message="No puedes eliminar este método de pago.")
        if metodo.tipo == "billetera":
            abort(400, message="La billetera virtual es creada por el sistema y no se puede eliminar.")

        era_principal = metodo.es_principal
        db.session.delete(metodo)
        db.session.commit()

        if era_principal:
            restantes = _metodos(user_id)
            if restantes:
                # Deja principal al primer método vinculado o a la billetera.
                candidato = next((m for m in restantes if m.tipo == "banco"), restantes[0])
                candidato.es_principal = True
                db.session.commit()

        return {"message": "Método de pago desvinculado."}