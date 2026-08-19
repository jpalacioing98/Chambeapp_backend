"""Domain models: User, Profile, LegalAcceptance (RF-01, RF-17)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class RolUsuario(str, Enum):
    """6 roles de ChambeApp."""

    PDS = "pds"
    SOLICITANTE = "solicitante"
    VERIFICADOR = "verificador"
    SOPORTE = "soporte"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"

    @classmethod
    def values(cls):
        return [r.value for r in cls]


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.Enum(RolUsuario), nullable=False,
                    default=RolUsuario.PDS)
    # RBAC Fase 1: estado de cuenta y versionado de rol para revocación de token.
    status = db.Column(db.String(20), default="active", nullable=False,
                       index=True)  # active | suspended | banned
    role_version = db.Column(db.Integer, default=1, nullable=False)
    nombre = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    edad_verificada = db.Column(db.Boolean, default=False, nullable=False)
    acepto_tyc = db.Column(db.Boolean, default=False, nullable=False)
    fecha_registro = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_login = db.Column(db.DateTime, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)

    profile = db.relationship(
        "Profile", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        from app.extensions import bcrypt

        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        from app.extensions import bcrypt

        return bcrypt.check_password_hash(self.password_hash, password)


class Profile(db.Model):
    __tablename__ = "profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    habilidades = db.Column(db.JSON, default=list)
    experiencia = db.Column(db.Text, nullable=True)
    zona = db.Column(db.String(120), nullable=True)
    calificacion_promedio = db.Column(db.Float, default=0.0, nullable=False)
    verificado = db.Column(db.Boolean, default=False, nullable=False)
    badges = db.Column(db.JSON, default=list)
    portafolio = db.Column(db.JSON, default=list)  # fotos / enlaces
    categorias = db.Column(db.JSON, default=list)
    perfil_completo = db.Column(db.Boolean, default=False, nullable=False)
    # RF-11: plan de suscripción y perfil destacado.
    plan = db.Column(db.String(20), default="free", nullable=False)
    destacado = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="profile")


class LegalAcceptance(db.Model):
    """Trazabilidad clickwrap T&C (Ley 527/1999, RF-17)."""

    __tablename__ = "legal_acceptances"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    version_tyc = db.Column(db.String(20), nullable=False)
    fecha = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    ip = db.Column(db.String(45), nullable=True)


class Verification(db.Model):
    """Solicitudes de verificación de identidad (KYC) revisadas por Verificador.

    Fase 1 RBAC: el panel admin (y el rol verificador) aprueban/rechazan.
    """

    __tablename__ = "verifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    document_type = db.Column(db.String(50), nullable=True)  # cédula, pasaporte...
    document_number = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default="pending", nullable=False,
                       index=True)  # pending | approved | rejected
    reviewed_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User", foreign_keys=[user_id])
