"""Modelo de suscripciones Web Push (RF-10 / HU-33).

Una fila por navegador/dispositivo suscrito. El `endpoint` es único a nivel
global: si el mismo navegador inicia sesión con otro usuario, la suscripción
se reasigna (no se duplica).
"""

from datetime import datetime, timezone

from app.extensions import db


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        db.Index("ix_push_subscriptions_user", "user_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    user_agent = db.Column(db.String(255), nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship("User", backref="push_subscriptions")

    def to_subscription_info(self) -> dict:
        """Formato que espera `pywebpush.webpush(subscription_info=...)`."""
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }
