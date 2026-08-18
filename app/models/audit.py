"""Audit log model + helper (RBAC Fase 1 — trazabilidad de acciones admin)."""

import json
from datetime import datetime, timezone

from app.extensions import db


class AuditLog(db.Model):
    """Registro inmutable de acciones administrativas (quién, qué, cuándo)."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    before_json = db.Column(db.Text, nullable=True)
    after_json = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


def _dump(obj):
    if obj is None:
        return None
    return json.dumps(obj, default=str)


def write_audit(actor_id, action, entity_type, entity_id, before, after, ip=None):
    """Crea un AuditLog y hace flush (dentro de la transacción de la request)."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=_dump(before),
        after_json=_dump(after),
        ip=ip,
    )
    db.session.add(log)
    db.session.flush()
    return log
