"""Domain models: Notification (RF-10 — centro de notificaciones persistente)."""

from datetime import datetime, timezone

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    tipo = db.Column(db.String(40), nullable=False)
    titulo = db.Column(db.String(200), nullable=True)
    mensaje = db.Column(db.Text, nullable=False)
    datos = db.Column(db.JSON, nullable=True)
    leida = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User")
