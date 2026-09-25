"""Domain model: MetodoPago — métodos de pago vinculados por el usuario.

El primer método SIEMPRE es la billetera virtual que crea el sistema
(tipo='billetera'); el usuario puede vincular cuentas bancarias
(tipo='banco', con banco de texto libre y número de cuenta).
"""

from datetime import datetime, timezone

from app.extensions import db


class MetodoPago(db.Model):
    __tablename__ = "metodos_pago"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    tipo = db.Column(db.String(30), nullable=False, default="banco")  # billetera | banco
    banco = db.Column(db.String(120), nullable=True)   # texto libre (ej: Nequi, Bancolombia...)
    numero_cuenta = db.Column(db.String(60), nullable=True)
    es_principal = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "banco": self.banco,
            "numero_cuenta": self.numero_cuenta,
            "es_principal": self.es_principal,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
        }