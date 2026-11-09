"""Support ticket model (RBAC Fase 2 — tickets de soporte)."""

from datetime import datetime, timezone

from app.extensions import db


class Ticket(db.Model):
    """Ticket de soporte creado por cualquier usuario autenticado."""

    __tablename__ = "tickets"
    __table_args__ = (
        db.Index("ix_tickets_user_creado", "user_id", "created_at"),
        db.Index("ix_tickets_status_creado", "status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.String(20), default="open", nullable=False
    )  # open | pending | closed
    priority = db.Column(
        db.String(20), default="normal", nullable=False
    )  # low | normal | high
    assigned_to = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
