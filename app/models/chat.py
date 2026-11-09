"""Domain models: Conversation y Message (RF-16 — chat/mensajería 1:1)."""

from datetime import datetime, timezone

from app.extensions import db


class Conversation(db.Model):
    """Conversación 1:1 entre dos usuarios (orden de usuarios normalizado)."""

    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    user_b_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint("user_a_id", "user_b_id", name="uq_conversation_pair"),
        db.Index("ix_conversations_user_a_creado", "user_a_id", "creado_en"),
        db.Index("ix_conversations_user_b_creado", "user_b_id", "creado_en"),
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
    """Mensaje dentro de una conversaci�n."""

    __tablename__ = "messages"
    __table_args__ = (
        db.Index(
            "ix_messages_conversation_creado",
            "conversation_id",
            "creado_en",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("conversations.id"), nullable=False
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
