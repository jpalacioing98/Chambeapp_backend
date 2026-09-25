"""Modelo Region — división regional para la gestión administrativa.

Permite que cada región tenga su propio equipo de personal (admin,
verificador y soporte) y que el panel administrativo acote sus
operaciones (usuarios, verificaciones, KYC, solicitudes, contratos,
disputas, tickets y contenido) a su región.
"""

from datetime import datetime, timezone

from app.extensions import db


class Region(db.Model):
    __tablename__ = "regions"

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(40), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    departamentos = db.Column(db.JSON, default=list)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "clave": self.clave,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "departamentos": self.departamentos or [],
        }

    def __repr__(self):
        return f"<Region {self.clave} ({self.nombre})>"