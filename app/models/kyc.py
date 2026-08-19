"""Modelos KYC documental por rol (Politica_KYC.md).

DocumentoRequerido: catálogo de documentos exigidos según el rol del usuario.
DocumentoUsuario: trazabilidad del estado de cada documento enviado por un usuario.
"""

from datetime import datetime, timezone

from app.extensions import db


class DocumentoRequerido(db.Model):
    """Catálogo de documentos KYC requeridos por rol (pds | solicitante)."""

    __tablename__ = "documentos_requeridos"

    id = db.Column(db.Integer, primary_key=True)
    rol = db.Column(db.String(30), nullable=False, index=True)  # pds | solicitante
    clave = db.Column(db.String(60), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    obligatorio = db.Column(db.Boolean, default=True, nullable=False)
    grupo = db.Column(db.String(30), nullable=True)  # identidad|antecedentes|financiero|opcional
    orden = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("rol", "clave", name="uq_documento_requerido_rol_clave"),
    )


class DocumentoUsuario(db.Model):
    """Estado documental KYC de un usuario concreto (trazabilidad)."""

    __tablename__ = "documentos_usuario"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    documento_clave = db.Column(db.String(60), nullable=False)
    rol = db.Column(db.String(30), nullable=True)
    estado = db.Column(
        db.String(20), default="no_enviado", nullable=False
    )  # no_enviado|enviado|aprobado|rechazado
    url = db.Column(db.String(512), nullable=True)
    fecha_envio = db.Column(db.DateTime, nullable=True)
    fecha_revision = db.Column(db.DateTime, nullable=True)
    revisado_por = db.Column(db.Integer, nullable=True)
    motivo = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "documento_clave", name="uq_documento_usuario_user_clave"
        ),
    )
