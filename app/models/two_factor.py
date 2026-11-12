"""Códigos de recuperación de 2FA (one-time backup codes).

Se guardan **hasheados** (HMAC-SHA256 con la SECRET_KEY de la app). El texto
plano solo se muestra una vez, al generarlos o regenerarlos.
"""

from datetime import datetime, timezone

from app.extensions import db


class TwoFactorRecoveryCode(db.Model):
    __tablename__ = "two_factor_recovery_codes"
    __table_args__ = (
        db.Index("ix_2fa_recovery_user", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    code_hash = db.Column(db.String(64), nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)
    usado_en = db.Column(db.DateTime, nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User", backref="two_factor_recovery_codes")
