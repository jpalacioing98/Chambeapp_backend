"""Modelos de configuración global y feature flags (RBAC Fase 3 — SUPERADMIN).

SystemConfig: clave/valor tipado (int|float|string|bool|json) para parámetros
de plataforma (comisiones, pagos, T&C, pesos de IA, planes, etc.).

FeatureFlag: toggles de funcionalidades (módulo 3D, certificados, mantenimiento…).
"""

import json
from datetime import datetime, timezone

from app.extensions import db


class SystemConfig(db.Model):
    """Configuración global tipada de la plataforma (supervisada por SUPERADMIN)."""

    __tablename__ = "system_configs"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(
        db.String(20), nullable=False, default="string"
    )  # int|float|string|bool|json
    description = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @staticmethod
    def parse_value(value, value_type):
        """Convierte el texto almacenado en su tipo nativo según value_type."""
        if value is None:
            return None
        if value_type == "int":
            return int(value)
        if value_type == "float":
            return float(value)
        if value_type == "bool":
            return str(value).strip().lower() in ("true", "1", "t", "yes")
        if value_type == "json":
            return json.loads(value)
        return value  # string

    @staticmethod
    def serialize_value(value, value_type):
        """Convierte un valor nativo al texto a almacenar según value_type."""
        if value is None:
            return None
        if value_type == "json":
            return json.dumps(value, default=str)
        if value_type == "bool":
            return "true" if bool(value) else "false"
        return str(value)

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.parse_value(self.value, self.value_type),
            "value_type": self.value_type,
            "description": self.description,
        }


class FeatureFlag(db.Model):
    """Feature flags de la plataforma (toggles controlados por SUPERADMIN)."""

    __tablename__ = "feature_flags"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    description = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "key": self.key,
            "enabled": self.enabled,
            "description": self.description,
        }
