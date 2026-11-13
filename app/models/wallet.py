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


class TipoMovimientoMonedas(str, Enum):
    """Movimientos del libro de monedas."""

    COMPRA = "compra"
    GASTO = "gasto"
    PROMOCIONAL = "promocional"
    GANADA = "ganada"
    VENCIMIENTO = "vencimiento"
    AJUSTE = "ajuste"

    @classmethod
    def values(cls):
        return [t.value for t in cls]


class Wallet(db.Model):
    """Billetera virtual del usuario (RF-25).

    `saldo` sigue siendo el saldo COP usado por los contratos/pagos reales.
    `monedas_saldo` es el saldo de monedas virtuales que se compran en
    paquetes y se gastan dentro de la plataforma.
    """

    __tablename__ = "wallets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    saldo = db.Column(db.Integer, default=0, nullable=False)  # COP disponibles
    saldo_bloqueado = db.Column(db.Integer, default=0, nullable=False)  # COP en proceso
    monedas_saldo = db.Column(db.Integer, default=0, nullable=False)  # monedas virtuales
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
    movimientos_monedas = db.relationship(
        "MovimientoMonedas",
        backref="wallet",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Wallet user={self.user_id} saldo={self.saldo} monedas={self.monedas_saldo}>"


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


class PaqueteMonedas(db.Model):
    """Paquete de monedas virtuales (configurable por el superadmin)."""

    __tablename__ = "paquetes_monedas"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    cantidad = db.Column(db.Integer, nullable=False, default=0)
    bonus = db.Column(db.Integer, nullable=False, default=0)
    precio_cop = db.Column(db.Integer, nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    en_oferta = db.Column(db.Boolean, nullable=False, default=False)
    precio_oferta_cop = db.Column(db.Integer, nullable=True)
    oferta_desde = db.Column(db.DateTime, nullable=True)
    oferta_hasta = db.Column(db.DateTime, nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0)
    creado_por = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<PaqueteMonedas {self.id} {self.nombre} {self.cantidad}+{self.bonus}>"

    def oferta_vigente(self, now: datetime | None = None) -> bool:
        """true si la oferta está activa y dentro de su vigencia."""
        if not self.en_oferta or self.precio_oferta_cop is None:
            return False
        now = now or datetime.now(timezone.utc)
        if self.oferta_desde and now < self.oferta_desde:
            return False
        if self.oferta_hasta and now > self.oferta_hasta:
            return False
        return True

    def precio_efectivo(self, now: datetime | None = None) -> int:
        """Precio a cobrar: promocional si la oferta está vigente."""
        if self.oferta_vigente(now):
            return int(self.precio_oferta_cop)
        return int(self.precio_cop)


class CompraPaquete(db.Model):
    """Compra de un paquete de monedas (pago simulado o pasarela real)."""

    __tablename__ = "compras_paquetes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    paquete_id = db.Column(
        db.Integer, db.ForeignKey("paquetes_monedas.id"), nullable=True, index=True
    )
    monedas = db.Column(db.Integer, nullable=False)
    precio_cop = db.Column(db.Integer, nullable=False)
    pasarela = db.Column(db.String(40), nullable=False, default="simulada")
    estado = db.Column(db.String(20), nullable=False, default="completado")
    referencia = db.Column(db.String(100), nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    paquete = db.relationship("PaqueteMonedas")

    def __repr__(self):
        return f"<CompraPaquete {self.id} user={self.user_id} monedas={self.monedas}>"


class MovimientoMonedas(db.Model):
    """Libro de movimientos de monedas (compra, gasto, bonificación...)."""

    __tablename__ = "movimientos_monedas"
    __table_args__ = (
        db.Index("ix_movimientos_monedas_user_creado", "user_id", "creado_en"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    wallet_id = db.Column(
        db.Integer, db.ForeignKey("wallets.id"), nullable=False, index=True
    )
    tipo = db.Column(db.String(20), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False)  # + entra / - sale
    saldo_resultante = db.Column(db.Integer, nullable=False, default=0)
    descripcion = db.Column(db.String(255), nullable=True)
    referencia = db.Column(db.String(100), nullable=True)
    paquete_id = db.Column(
        db.Integer, db.ForeignKey("paquetes_monedas.id"), nullable=True
    )
    vence_en = db.Column(db.DateTime, nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    paquete = db.relationship("PaqueteMonedas")

    def __repr__(self):
        return f"<MovimientoMonedas {self.tipo} {self.cantidad}>"
