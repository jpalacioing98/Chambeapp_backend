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
    """Estado documental KYC de un usuario concreto (trazabilidad).

    Estado (máquina de estados): no_enviado | enviado | aprobado | rechazado.
    El MVP almacena el archivo en base64 (sin S3).
    """

    __tablename__ = "documentos_usuario"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    documento_requerido_id = db.Column(
        db.Integer, db.ForeignKey("documentos_requeridos.id"), nullable=True, index=True
    )
    documento_clave = db.Column(db.String(60), nullable=False)
    rol = db.Column(db.String(30), nullable=True)
    estado = db.Column(
        db.String(20), default="no_enviado", nullable=False
    )  # no_enviado|enviado|aprobado|rechazado
    url = db.Column(db.String(512), nullable=True)
    # MVP: archivo KYC en base64 (sin S3).
    archivo_base64 = db.Column(db.Text, nullable=True)
    nombre_archivo = db.Column(db.String(255), nullable=True)
    tipo_mime = db.Column(db.String(100), nullable=True)
    fecha_envio = db.Column(db.DateTime, nullable=True)
    revisado_en = db.Column(db.DateTime, nullable=True)
    revisor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )  # verificador/admin que revisó
    nota = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "documento_clave", name="uq_documento_usuario_user_clave"
        ),
    )
