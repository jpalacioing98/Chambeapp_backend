"""Domain models: Conversation y Message (RF-16 — chat/mensajería 1:1)."""

from datetime import datetime, timezone

from app.extensions import db


class Conversation(db.Model):
    """Conversación 1:1 entre dos usuarios (orden de usuarios normalizado)."""

    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    user_b_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),
    )

    messages = db.relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.creado_en.asc()",
    )

    @staticmethod
    def normalize(user_1: int, user_2: int):
        """Devuelve (a, b) ordenados para evitar duplicados por orden."""
        return tuple(sorted((user_1, user_2)))

    def involves(self, user_id: int) -> bool:
        return self.user_a_id == user_id or self.user_b_id == user_id


class Message(db.Model):
    """Mensaje dentro de una conversación."""

    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True
    )
    sender_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    contenido = db.Column(db.Text, nullable=False)
    leido = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    conversation = db.relationship("Conversation", back_populates="messages")
