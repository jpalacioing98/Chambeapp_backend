"""Domain model: Suscripcion (RF-11 Suscripciones Premium).

Suscripción simulada (sin pasarela real). Una suscripción activa por usuario.
"""

from datetime import datetime, timezone

from app.extensions import db


PLANES = ("basico", "profesional", "empresa", "free")
ESTADOS_SUSCRIPCION = ("activa", "cancelada", "vencida")


def _now():
    return datetime.now(timezone.utc)


class Suscripcion(db.Model):
    __tablename__ = "suscripciones"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    plan = db.Column(db.String(20), nullable=False, default="free")
    estado = db.Column(db.String(20), nullable=False, default="activa")
    inicio_en = db.Column(db.DateTime, default=_now, nullable=False)
    fin_en = db.Column(db.DateTime, nullable=True)
    monto = db.Column(db.Integer, nullable=False, default=0)  # COP
    metodo_pago = db.Column(db.String(20), nullable=False, default="mock")
    creado_en = db.Column(db.DateTime, default=_now, nullable=False)
    actualizado_en = db.Column(
        db.DateTime, default=_now, onupdate=_now, nullable=False
    )

    user = db.relationship("User")
