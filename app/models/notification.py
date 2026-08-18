"""Domain models: Notification (RF-16 parcial — notificaciones in-app)."""

from datetime import datetime, timezone

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    tipo = db.Column(db.String(50), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    leida = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User")
