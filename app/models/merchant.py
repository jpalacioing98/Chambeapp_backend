"""Modelos del módulo Comerciante: MerchantPreference, MerchantPaymentMethod.

Tablas nuevas definidas en la migración 005_add_merchant_to_rol_enum.py.
"""

from datetime import datetime, timezone

from app.extensions import db


class MerchantPreference(db.Model):
    """Preferencias de notificación y configuración del comerciante."""

    __tablename__ = "merchant_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True,
        index=True,
    )
    # Notificaciones
    notif_nueva_solicitud = db.Column(db.Boolean, default=True, nullable=False)
    notif_nueva_resena = db.Column(db.Boolean, default=True, nullable=False)
    notif_estado_kyc = db.Column(db.Boolean, default=True, nullable=False)
    notif_pago_recibido = db.Column(db.Boolean, default=True, nullable=False)
    # Configuración
    push_enabled = db.Column(db.Boolean, default=True, nullable=False)
    email_digest = db.Column(db.String(10), default="daily", nullable=False)
    # Preferencias UI (perfil unificado: disponibles para todos los roles)
    idioma = db.Column(db.String(5), default="es", nullable=False)
    tema = db.Column(db.String(10), default="system", nullable=False)
    # Timestamps
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship("User", backref="merchant_preferences", uselist=False)


class MerchantPaymentMethod(db.Model):
    """Método de pago asociado al negocio del comerciante."""

    __tablename__ = "merchant_payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True,
    )
    tipo = db.Column(db.String(30), nullable=False)  # nequi, bancolombia, efectivo, etc.
    detalle = db.Column(db.JSON, nullable=False)       # { numero, titular, ... }
    principal = db.Column(db.Boolean, default=False, nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User", backref="payment_methods")
