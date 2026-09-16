"""Badge types and model for user achievements (P2-5)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class BadgeType(str, Enum):
    """All available badges in ChambeApp."""

    PRIMER_CONTRATO = "primer_contrato"
    DIEZ_CONTRATOS = "diez_contratos"
    CIEN_CONTRATOS = "cien_contratos"
    VERIFICADO = "verificado"
    PERFIL_COMPLETO = "perfil_completo"
    PRIMER_SERVICIO = "primer_servicio"
    TOP_RATED = "top_rated"
    SIN_DISPUTAS = "sin_disputas"
    MONEDERO_ACTIVO = "monedero_activo"

    @classmethod
    def values(cls):
        return [b.value for b in cls]


class Badge(db.Model):
    """Badge otorgado a un usuario."""

    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tipo = db.Column(db.String(50), nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    otorgado_en = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref="user_badges")
