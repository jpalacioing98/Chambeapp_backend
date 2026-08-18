"""Domain models: User, Profile, LegalAcceptance (RF-01, RF-17)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class RolUsuario(str, Enum):
    """6 roles de ChambeApp."""

    TRABAJADOR = "trabajador"
    EMPLEADOR = "empleador"
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
                    default=RolUsuario.TRABAJADOR)
    edad_verificada = db.Column(db.Boolean, default=False, nullable=False)
    acepto_tyc = db.Column(db.Boolean, default=False, nullable=False)
    fecha_registro = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
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
