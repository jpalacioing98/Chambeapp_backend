"""SUPERADMIN blueprint (RBAC Fase 3): panel de superadministración.

Todos los endpoints requieren rol superadmin (ver @superadmin_required).
Registrado en /api/v1/superadmin.

Incluye: gestión de admins internos, config global, auditoría, T&C,
override forzado, parámetros de IA y feature flags.
"""

from datetime import datetime, timezone
from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.auth.decorators import superadmin_required
from app.models.user import User, RolUsuario
from app.models.contract import Contract, EstadoContrato
from app.models.audit import AuditLog, write_audit
from app.models.config import SystemConfig, FeatureFlag
from app.schemas.superadmin import (
    AdminCreateSchema,
    AdminPatchSchema,
    AdminListResponseSchema,
    ConfigPatchSchema,
    ConfigListResponseSchema,
    AuditLogListResponseSchema,
    AuditLogDetailSchema,
    TyCGetSchema,
    TyCPostSchema,
    TyCPostResponseSchema,
    OverrideUserSchema,
    OverrideContractSchema,
    FlagPatchSchema,
    FlagListResponseSchema,
)

blp = Blueprint("superadmin", __name__, description="Panel SUPERADMIN (RBAC Fase 3)")

# Roles internos gestionables por SUPERADMIN (no incluye superadmin ni roles públicos).
_INTERNAL_ROLES = [RolUsuario.ADMIN, RolUsuario.SOPORTE, RolUsuario.VERIFICADOR]


def _actor_id() -> int:
    return int(get_jwt_identity())


def _client_ip() -> str:
    return request.remote_addr or "127.0.0.1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==========================================================================
# GESTIÓN DE ADMINS INTERNOS
# ==========================================================================
@blp.route("/admins")
class SuperAdminAdminList(MethodView):
    @superadmin_required
    @blp.response(200, AdminListResponseSchema)
    def get(self):
        """Lista usuarios con rol interno (admin, soporte, verificador)."""
        query = User.query.filter(User.rol.in_(_INTERNAL_ROLES))
        total = query.count()
        users = query.order_by(User.id).all()
        return {"items": users, "total": total}

    @superadmin_required
    @blp.arguments(AdminCreateSchema)
    @blp.response(201, AdminListResponseSchema)
    def post(self, data):
        """Crea un usuario interno (admin | soporte | verificador)."""
        if User.query.filter_by(email=data["email"]).first():
            abort(409, message="El email ya está registrado.")
        user = User(
            email=data["email"],
            rol=RolUsuario(data["rol"]),
            nombre=data["nombre"],
            acepto_tyc=True,
            activo=True,
            status="active",
        )
        user.set_password(data["password"])
        db.session.add(user)
        db.session.flush()
        write_audit(
            _actor_id(), "superadmin.admin.create", "user", user.id,
            None, {"email": user.email, "rol": user.rol.value},
            _client_ip(),
        )
        db.session.commit()
        return {"items": [user], "total": 1}


@blp.route("/admins/<int:admin_id>")
class SuperAdminAdminDetail(MethodView):
    @superadmin_required
    @blp.arguments(AdminPatchSchema)
    @blp.response(200)
    def patch(self, data, admin_id):
        """Actualiza nombre/rol/status de un admin interno."""
        user = db.get_or_404(User, admin_id)
        if user.rol not in _INTERNAL_ROLES:
            abort(400, message="Solo se pueden gestionar usuarios internos.")
        before = {
            "nombre": user.nombre,
            "rol": user.rol.value,
            "status": user.status,
        }
        if "nombre" in data:
            user.nombre = data["nombre"]
        if "rol" in data:
            user.rol = RolUsuario(data["rol"])
            user.role_version += 1  # revoca tokens del afectado
        if "status" in data:
            user.status = data["status"]
            user.role_version += 1  # revoca tokens del afectado
        write_audit(
            _actor_id(), "superadmin.admin.update", "user", user.id,
            before,
            {"nombre": user.nombre, "rol": user.rol.value, "status": user.status},
            _client_ip(),
        )
        db.session.commit()
        return {"id": user.id, "rol": user.rol.value, "status": user.status}

    @superadmin_required
    @blp.response(200)
    def delete(self, admin_id):
        """Desactiva (banned) un admin interno."""
        user = db.get_or_404(User, admin_id)
        if user.rol not in _INTERNAL_ROLES:
            abort(400, message="Solo se pueden gestionar usuarios internos.")
        before = {"status": user.status}
        user.status = "banned"
        user.role_version += 1  # revoca tokens
        write_audit(
            _actor_id(), "superadmin.admin.delete", "user", user.id,
            before, {"status": "banned"}, _client_ip(),
        )
        db.session.commit()
        return {"id": user.id, "status": user.status}


# ==========================================================================
# CONFIG GLOBAL
# ==========================================================================
@blp.route("/config")
class SuperAdminConfig(MethodView):
    @superadmin_required
    @blp.response(200, ConfigListResponseSchema)
    def get(self):
        """Lista toda la configuración global tipada."""
        configs = SystemConfig.query.order_by(SystemConfig.key).all()
        return {"configs": [c.to_dict() for c in configs]}

    @superadmin_required
    @blp.arguments(ConfigPatchSchema)
    @blp.response(200)
    def patch(self, data):
        """Actualiza el valor de una SystemConfig (castea según value_type)."""
        cfg = SystemConfig.query.filter_by(key=data["key"]).first_or_404(
            description="Config key no encontrada."
        )
        before = {"value": cfg.value}
        cfg.value = SystemConfig.serialize_value(data["value"], cfg.value_type)
        cfg.updated_by = _actor_id()
        cfg.updated_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "superadmin.config.update", "system_config", cfg.id,
            before, {"value": cfg.value}, _client_ip(),
        )
        db.session.commit()
        return cfg.to_dict()


# ==========================================================================
# AUDITORÍA
# ==========================================================================
@blp.route("/audit-logs")
class SuperAdminAuditList(MethodView):
    @superadmin_required
    @blp.response(200, AuditLogListResponseSchema)
    def get(self):
        """Lista logs de auditoría (filtros: actor_id, entity_type, limit=100)."""
        query = AuditLog.query
        actor_id = request.args.get("actor_id", type=int)
        if actor_id is not None:
            query = query.filter(AuditLog.actor_id == actor_id)
        entity_type = request.args.get("entity_type")
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)
        limit = request.args.get("limit", default=100, type=int)
        total = query.count()
        logs = query.order_by(AuditLog.id.desc()).limit(limit).all()
        return {"items": logs, "total": total}


@blp.route("/audit-logs/<int:log_id>")
class SuperAdminAuditDetail(MethodView):
    @superadmin_required
    @blp.response(200, AuditLogDetailSchema)
    def get(self, log_id):
        """Detalle de un log de auditoría (before/after json)."""
        log = db.get_or_404(AuditLog, log_id)
        return log


# ==========================================================================
# LEGAL / T&C
# ==========================================================================
@blp.route("/legal/tyc")
class SuperAdminTyC(MethodView):
    @superadmin_required
    @blp.response(200, TyCGetSchema)
    def get(self):
        """Lee la versión vigente de T&C desde SystemConfig 'tyc_current'."""
        cfg = SystemConfig.query.filter_by(key="tyc_current").first_or_404(
            description="No hay T&C configurados."
        )
        data = SystemConfig.parse_value(cfg.value, "json") or {}
        return {
            "version": data.get("version"),
            "content": data.get("content"),
            "published_at": data.get("published_at"),
        }

    @superadmin_required
    @blp.arguments(TyCPostSchema)
    @blp.response(201, TyCPostResponseSchema)
    def post(self, data):
        """Publica una nueva versión de T&C (incrementa versión)."""
        cfg = SystemConfig.query.filter_by(key="tyc_current").first()
        current = SystemConfig.parse_value(cfg.value, "json") if cfg else {}
        try:
            version = int(current.get("version", 0)) + 1
        except (ValueError, TypeError):
            version = 1
        new_value = {
            "version": version,
            "content": data["content"],
            "published_at": _now_iso(),
        }
        before = {"tyc_current": current}
        if cfg is None:
            cfg = SystemConfig(
                key="tyc_current",
                value_type="json",
                description="Términos y Condiciones vigentes",
            )
            db.session.add(cfg)
        cfg.value = SystemConfig.serialize_value(new_value, "json")
        cfg.updated_by = _actor_id()
        cfg.updated_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "superadmin.tyc.publish", "system_config", cfg.id,
            before, {"tyc_current": new_value}, _client_ip(),
        )
        db.session.commit()
        return {"version": version, "published_at": new_value["published_at"]}


# ==========================================================================
# OVERRIDE (supervisión forzada)
# ==========================================================================
@blp.route("/override/user")
class SuperAdminOverrideUser(MethodView):
    @superadmin_required
    @blp.arguments(OverrideUserSchema)
    @blp.response(200)
    def post(self, data):
        """Aplica acción forzada sobre un User (reactivate | suspend)."""
        user = db.get_or_404(User, data["user_id"])
        action = data["action"]
        before = {"status": user.status}
        if action == "reactivate":
            new_status = "active"
        else:  # suspend
            new_status = "suspended"
        user.status = new_status
        user.role_version += 1  # revoca tokens del afectado
        write_audit(
            _actor_id(), f"superadmin.override.user.{action}", "user", user.id,
            before, {"status": new_status}, _client_ip(),
        )
        db.session.commit()
        return {"id": user.id, "status": user.status}


@blp.route("/override/contract")
class SuperAdminOverrideContract(MethodView):
    @superadmin_required
    @blp.arguments(OverrideContractSchema)
    @blp.response(200)
    def post(self, data):
        """Aplica acción forzada sobre un Contract (complete | cancel)."""
        contract = db.get_or_404(Contract, data["contract_id"])
        action = data["action"]
        before = {"estado": contract.estado.value}
        if action == "complete":
            new_estado = EstadoContrato.COMPLETADO
        else:  # cancel
            new_estado = EstadoContrato.CANCELADO
        contract.estado = new_estado
        write_audit(
            _actor_id(), f"superadmin.override.contract.{action}", "contract", contract.id,
            before, {"estado": new_estado.value}, _client_ip(),
        )
        db.session.commit()
        return {"id": contract.id, "estado": contract.estado.value}


# ==========================================================================
# IA / TRANSPARENCIA
# ==========================================================================
@blp.route("/ai/params")
class SuperAdminAIParams(MethodView):
    @superadmin_required
    def get(self):
        """Lee los pesos del modelo de IA desde SystemConfig 'ai_weights'."""
        cfg = SystemConfig.query.filter_by(key="ai_weights").first_or_404(
            description="No hay parámetros de IA configurados."
        )
        return SystemConfig.parse_value(cfg.value, "json") or {}

    @superadmin_required
    def patch(self):
        """Actualiza los pesos del modelo de IA ('ai_weights')."""
        weights = request.get_json(silent=True)
        if not isinstance(weights, dict):
            abort(400, message="El body debe ser un objeto JSON de pesos.")
        cfg = SystemConfig.query.filter_by(key="ai_weights").first()
        before = {"ai_weights": SystemConfig.parse_value(cfg.value, "json")} if cfg else None
        if cfg is None:
            cfg = SystemConfig(
                key="ai_weights",
                value_type="json",
                description="Pesos del modelo de recomendación IA",
            )
            db.session.add(cfg)
        cfg.value = SystemConfig.serialize_value(weights, "json")
        cfg.updated_by = _actor_id()
        cfg.updated_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "superadmin.ai.params.update", "system_config", cfg.id,
            before, {"ai_weights": weights}, _client_ip(),
        )
        db.session.commit()
        return SystemConfig.parse_value(cfg.value, "json")


# ==========================================================================
# FEATURE FLAGS
# ==========================================================================
@blp.route("/flags")
class SuperAdminFlagList(MethodView):
    @superadmin_required
    @blp.response(200, FlagListResponseSchema)
    def get(self):
        """Lista todos los feature flags."""
        flags = FeatureFlag.query.order_by(FeatureFlag.key).all()
        return {"items": [f.to_dict() for f in flags]}


@blp.route("/flags/<key>")
class SuperAdminFlagToggle(MethodView):
    @superadmin_required
    @blp.arguments(FlagPatchSchema)
    @blp.response(200)
    def patch(self, data, key):
        """Activa/desactiva un feature flag por su clave."""
        flag = FeatureFlag.query.filter_by(key=key).first_or_404(
            description="Feature flag no encontrado."
        )
        before = {"enabled": flag.enabled}
        flag.enabled = bool(data["enabled"])
        write_audit(
            _actor_id(), "superadmin.flag.toggle", "feature_flag", flag.id,
            before, {"enabled": flag.enabled}, _client_ip(),
        )
        db.session.commit()
        return {"key": flag.key, "enabled": flag.enabled}
