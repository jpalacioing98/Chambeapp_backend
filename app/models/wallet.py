"""Domain models: Wallet, Transaction, Coin (RF-25, RF-27 — Billetera Virtual y Monedas)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class TipoTransaccion(str, Enum):
    """Tipos de transacción en la billetera."""

    COMISION = "comision"
    MONEDAS = "monedas"
    RETIRO = "retiro"
    REEMBOLSO = "reembolso"
    DEPOSITO = "deposito"

    @classmethod
    def values(cls):
        return [t.value for t in cls]


class TipoMoneda(str, Enum):
    """Tipos de monedas en el sistema."""

    COMPRADA = "comprada"
    PROMOCIONAL = "promocional"
    GANADA = "ganada"

    @classmethod
    def values(cls):
        return [t.value for t in cls]


class Wallet(db.Model):
    """Billetera virtual del usuario (RF-25)."""

    __tablename__ = "wallets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    saldo = db.Column(db.Integer, default=0, nullable=False)  # COP disponibles
    saldo_bloqueado = db.Column(db.Integer, default=0, nullable=False)  # COP en proceso
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship("User", backref="wallet", uselist=False)
    transactions = db.relationship(
        "Transaction", backref="wallet", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Wallet user={self.user_id} saldo={self.saldo}>"


class Transaction(db.Model):
    """Transacción de billetera (RF-25)."""

    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(
        db.Integer, db.ForeignKey("wallets.id"), nullable=False, index=True
    )
    tipo = db.Column(
        db.Enum(TipoTransaccion), nullable=False, index=True
    )
    monto = db.Column(db.Integer, nullable=False)  # COP (positivo=entrada, negativo=salida)
    descripcion = db.Column(db.Text, nullable=True)
    referencia = db.Column(db.String(100), nullable=True)  # ID de orden, pago, etc.
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<Transaction {self.tipo.value} monto={self.monto}>"


class Coin(db.Model):
    """Monedas del usuario (RF-27)."""

    __tablename__ = "coins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    cantidad = db.Column(db.Integer, default=0, nullable=False)
    tipo = db.Column(db.Enum(TipoMoneda), nullable=False, index=True)
    vence_en = db.Column(db.DateTime, nullable=True)  # Solo para promocionales
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = db.relationship("User", backref="coins")

    def __repr__(self):
        return f"<Coin user={self.user_id} tipo={self.tipo.value} cant={self.cantidad}>"
