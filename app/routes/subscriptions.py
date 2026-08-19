"""Subscriptions blueprint: planes y suscripción simulada (RF-11).

Endpoints (prefijo /api/v1/subscriptions):
  GET  /planes    -> catálogo de planes (hardcoded)
  GET  /mine      -> suscripción activa del usuario (JWT)
  POST /          -> suscribirse a un plan (JWT, simulado)
  POST /cancel    -> cancelar suscripción activa (JWT)
"""

from datetime import datetime, timedelta, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, Profile
from app.models.subscription import Suscripcion
from app.schemas.subscription import (
    SuscripcionSchema,
    SuscripcionCreateSchema,
    PlanSchema,
)

blp = Blueprint(
    "subscriptions", __name__, description="Suscripciones Premium (RF-11)"
)

PLANES_CATALOGO = [
    {
        "plan": "basico",
        "nombre": "Basico",
        "precio": 15000,
        "beneficios": [
            "Hasta 5 postulaciones por mes",
            "Perfil basico",
        ],
    },
    {
        "plan": "profesional",
        "nombre": "Profesional",
        "precio": 35000,
        "beneficios": [
            "Postulaciones ilimitadas",
            "Perfil destacado en busquedas",
            "Analytics basicos",
        ],
    },
    {
        "plan": "empresa",
        "nombre": "Empresa",
        "precio": 75000,
        "beneficios": [
            "Postulaciones ilimitadas",
            "Perfil destacado en busquedas",
            "Gestion de equipos",
            "Multi-cuenta",
            "Analytics avanzados",
            "Soporte prioritario",
        ],
    },
]

PLANES_PRECIO = {p["plan"]: p["precio"] for p in PLANES_CATALOGO}
PLANES_DESTACADOS = {"profesional", "empresa"}


def _now():
    return datetime.now(timezone.utc)


@blp.route("/planes")
class PlanesCatalogo(MethodView):
    @blp.response(200, PlanSchema(many=True))
    def get(self):
        """RF-11: catálogo de planes disponibles."""
        return PLANES_CATALOGO


@blp.route("/mine")
class MiSuscripcion(MethodView):
    @jwt_required()
    @blp.response(200, SuscripcionSchema)
    def get(self):
        """Suscripción activa del usuario (estado='activa' y fin_en > now)."""
        user_id = int(get_jwt_identity())
        now = _now()
        sub = (
            Suscripcion.query.filter_by(user_id=user_id, estado="activa")
            .filter(Suscripcion.fin_en > now)
            .first()
        )
        if sub is None:
            return None
        return sub


@blp.route("/")
class Suscribirse(MethodView):
    @jwt_required()
    @blp.arguments(SuscripcionCreateSchema)
    @blp.response(201, SuscripcionSchema)
    def post(self, data):
        """RF-11: suscripción simulada a un plan (sin pasarela real)."""
        user_id = int(get_jwt_identity())
        plan = data["plan"]

        # Cancelar cualquier suscripción activa previa.
        previas = Suscripcion.query.filter_by(
            user_id=user_id, estado="activa"
        ).all()
        for s in previas:
            s.estado = "cancelada"
            s.actualizado_en = _now()

        now = _now()
        sub = Suscripcion(
            user_id=user_id,
            plan=plan,
            estado="activa",
            inicio_en=now,
            fin_en=now + timedelta(days=30),
            monto=PLANES_PRECIO.get(plan, 0),
            metodo_pago="mock",
        )
        db.session.add(sub)

        # Actualizar perfil.
        profile = Profile.query.get(user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            db.session.add(profile)
        profile.plan = plan
        profile.destacado = plan in PLANES_DESTACADOS

        db.session.commit()
        return sub


@blp.route("/cancel")
class CancelarSuscripcion(MethodView):
    @jwt_required()
    @blp.response(200, SuscripcionSchema)
    def post(self):
        """RF-11: cancela la suscripción activa y revierte el perfil a free."""
        user_id = int(get_jwt_identity())
        now = _now()
        sub = (
            Suscripcion.query.filter_by(user_id=user_id, estado="activa")
            .filter(Suscripcion.fin_en > now)
            .first()
        )
        if sub is None:
            abort(404, message="No tienes una suscripcion activa para cancelar.")

        sub.estado = "cancelada"
        sub.fin_en = now
        sub.actualizado_en = now

        profile = Profile.query.get(user_id)
        if profile is None:
            profile = Profile(user_id=user_id)
            db.session.add(profile)
        profile.plan = "free"
        profile.destacado = False

        db.session.commit()
        return sub
