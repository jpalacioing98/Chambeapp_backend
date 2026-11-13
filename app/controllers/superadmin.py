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
from app.models.region import Region
from app.schemas.superadmin import (
    AdminCreateSchema,
    AdminPatchSchema,
    AdminListResponseSchema,
    ConfigPatchSchema,
    ConfigListResponseSchema,
    AuditLogListResponseSchema,
    AuditLogDetailSchema,
    TyCGetSchema,
    TyCDraftSchema,
    TyCHistorySchema,
    TyCRollbackSchema,
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


def _parse_fecha(valor: str | None, fin_de_dia: bool = False):
    """Convierte un parámetro ISO ('2026-11-13' o ISO completo) a datetime UTC.

    `fin_de_dia` extiende una fecha sin hora a 23:59:59.999999, para que el
    filtro `to` incluya todo el día.
    """
    if not valor:
        return None
    texto = valor.strip()
    try:
        fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    if fin_de_dia and len(texto) <= 10:
        fecha = fecha.replace(hour=23, minute=59, second=59, microsecond=999999)
    return fecha


def _resolve_region_id(region_id) -> int | None:
    """Valida que la región exista y devuelve su id (o None)."""
    if region_id is None:
        return None
    region = db.session.get(Region, region_id)
    if region is None:
        abort(400, message="La región indicada no existe.")
    return region.id


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
        """Crea un usuario interno (admin | soporte | verificador).

        `region_id` (opcional): asigna el personal a una región. Los roles
        regionales (admin/verificador/soporte) deberían llevar región para
        acotar su operación.
        """
        if User.query.filter_by(email=data["email"]).first():
            abort(409, message="El email ya está registrado.")
        region_id = _resolve_region_id(data.get("region_id"))
        user = User(
            email=data["email"],
            rol=RolUsuario(data["rol"]),
            nombre=data["nombre"],
            acepto_tyc=True,
            activo=True,
            status="active",
            region_id=region_id,
        )
        user.set_password(data["password"])
        db.session.add(user)
        db.session.flush()
        write_audit(
            _actor_id(), "superadmin.admin.create", "user", user.id,
            None, {"email": user.email, "rol": user.rol.value, "region_id": region_id},
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
        if "region_id" in data:
            user.region_id = _resolve_region_id(data.get("region_id"))
            user.role_version += 1  # revoca tokens (cambió su alcance)
        write_audit(
            _actor_id(), "superadmin.admin.update", "user", user.id,
            before,
            {
                "nombre": user.nombre,
                "rol": user.rol.value,
                "status": user.status,
                "region_id": user.region_id,
            },
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
        """Lista logs de auditoría.

        Filtros: actor_id, entity_type (exacto), action (contiene), q (acción o
        tipo de entidad), from/to (ISO 8601, acepta 'YYYY-MM-DD'), limit y offset.
        """
        query = AuditLog.query

        actor_id = request.args.get("actor_id", type=int)
        if actor_id is not None:
            query = query.filter(AuditLog.actor_id == actor_id)

        entity_type = request.args.get("entity_type")
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)

        action = request.args.get("action")
        if action:
            query = query.filter(AuditLog.action.ilike(f"%{action}%"))

        search = request.args.get("q") or request.args.get("search")
        if search:
            patron = f"%{search}%"
            query = query.filter(
                db.or_(AuditLog.action.ilike(patron), AuditLog.entity_type.ilike(patron))
            )

        desde = _parse_fecha(request.args.get("from"))
        if desde is not None:
            query = query.filter(AuditLog.created_at >= desde)

        hasta = _parse_fecha(request.args.get("to"), fin_de_dia=True)
        if hasta is not None:
            query = query.filter(AuditLog.created_at <= hasta)

        limit = min(request.args.get("limit", default=100, type=int) or 100, 500)
        offset = max(request.args.get("offset", default=0, type=int) or 0, 0)

        total = query.count()
        logs = query.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
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
        """Versión vigente de T&C + borrador sin publicar (si existe)."""
        cfg = SystemConfig.query.filter_by(key="tyc_current").first_or_404(
            description="No hay T&C configurados."
        )
        data = SystemConfig.parse_value(cfg.value, "json") or {}
        draft_cfg = SystemConfig.query.filter_by(key="tyc_draft").first()
        draft = SystemConfig.parse_value(draft_cfg.value, "json") if draft_cfg else None
        return {
            "version": data.get("version"),
            "content": data.get("content"),
            "published_at": data.get("published_at"),
            "draft": draft,
        }

    @superadmin_required
    @blp.arguments(TyCPostSchema)
    @blp.response(201, TyCPostResponseSchema)
    def post(self, data):
        """Publica una nueva versión de T&C (incrementa versión y archiva la anterior)."""
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
            "published_by": _actor_id(),
        }
        before = {"tyc_current": current}

        # Archiva la versión que deja de estar vigente (historial acotado a 20).
        if current.get("content"):
            _archivar_tyc(current)

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

        # Publicar descarta el borrador.
        draft_cfg = SystemConfig.query.filter_by(key="tyc_draft").first()
        if draft_cfg is not None:
            db.session.delete(draft_cfg)

        write_audit(
            _actor_id(), "superadmin.tyc.publish", "system_config", cfg.id,
            before, {"tyc_current": new_value}, _client_ip(),
        )
        db.session.commit()
        return {"version": version, "published_at": new_value["published_at"]}


@blp.route("/legal/tyc/draft")
class SuperAdminTyCDraft(MethodView):
    @superadmin_required
    @blp.response(200, TyCGetSchema)
    def get(self):
        """Devuelve el borrador guardado (o null si no hay)."""
        cfg = SystemConfig.query.filter_by(key="tyc_current").first()
        current = SystemConfig.parse_value(cfg.value, "json") if cfg else {}
        draft_cfg = SystemConfig.query.filter_by(key="tyc_draft").first()
        draft = SystemConfig.parse_value(draft_cfg.value, "json") if draft_cfg else None
        return {
            "version": current.get("version"),
            "content": current.get("content"),
            "published_at": current.get("published_at"),
            "draft": draft,
        }

    @superadmin_required
    @blp.arguments(TyCDraftSchema)
    @blp.response(200, TyCDraftSchema)
    def put(self, data):
        """Guarda (o reemplaza) el borrador de T&C sin publicarlo."""
        cfg = SystemConfig.query.filter_by(key="tyc_draft").first()
        valor = {
            "content": data["content"],
            "updated_at": _now_iso(),
            "updated_by": _actor_id(),
        }
        antes = SystemConfig.parse_value(cfg.value, "json") if cfg else None
        if cfg is None:
            cfg = SystemConfig(
                key="tyc_draft",
                value_type="json",
                description="Borrador de Términos y Condiciones",
            )
            db.session.add(cfg)
        cfg.value = SystemConfig.serialize_value(valor, "json")
        cfg.updated_by = _actor_id()
        cfg.updated_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "superadmin.tyc.draft.save", "system_config", cfg.id,
            {"tyc_draft": antes}, {"tyc_draft": valor}, _client_ip(),
        )
        db.session.commit()
        return valor


@blp.route("/legal/tyc/history")
class SuperAdminTyCHistory(MethodView):
    @superadmin_required
    @blp.response(200, TyCHistorySchema)
    def get(self):
        """Historial de versiones publicadas (más reciente primero)."""
        cfg = SystemConfig.query.filter_by(key="tyc_history").first()
        items = SystemConfig.parse_value(cfg.value, "json") if cfg else []
        return {"items": list(reversed(items or []))}


@blp.route("/legal/tyc/rollback")
class SuperAdminTyCRollback(MethodView):
    @superadmin_required
    @blp.arguments(TyCRollbackSchema)
    @blp.response(200, TyCPostResponseSchema)
    def post(self, data):
        """Restaura una versión del historial como vigente (deja rastro en auditoría)."""
        version = data["version"]
        historial = _leer_historial_tyc()
        elegida = next((v for v in historial if int(v.get("version", -1)) == version), None)
        if elegida is None:
            abort(404, message="Esa versión no está en el historial.")

        cfg = SystemConfig.query.filter_by(key="tyc_current").first()
        current = SystemConfig.parse_value(cfg.value, "json") if cfg else {}
        if current.get("content"):
            _archivar_tyc(current)

        restaurada = {
            "version": version,
            "content": elegida.get("content"),
            "published_at": _now_iso(),
            "published_by": _actor_id(),
        }
        if cfg is None:
            cfg = SystemConfig(
                key="tyc_current",
                value_type="json",
                description="Términos y Condiciones vigentes",
            )
            db.session.add(cfg)
        cfg.value = SystemConfig.serialize_value(restaurada, "json")
        cfg.updated_by = _actor_id()
        cfg.updated_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "superadmin.tyc.rollback", "system_config", cfg.id,
            {"tyc_current": current}, {"tyc_current": restaurada}, _client_ip(),
        )
        db.session.commit()
        return {"version": version, "published_at": restaurada["published_at"]}


def _leer_historial_tyc() -> list:
    cfg = SystemConfig.query.filter_by(key="tyc_history").first()
    if cfg is None:
        return []
    return SystemConfig.parse_value(cfg.value, "json") or []


def _archivar_tyc(version: dict) -> None:
    """Añade una versión al historial (máximo 20 entradas)."""
    historial = _leer_historial_tyc()
    historial.append(version)
    historial = historial[-20:]
    cfg = SystemConfig.query.filter_by(key="tyc_history").first()
    if cfg is None:
        cfg = SystemConfig(
            key="tyc_history",
            value_type="json",
            description="Historial de versiones de Términos y Condiciones",
        )
        db.session.add(cfg)
    cfg.value = SystemConfig.serialize_value(historial, "json")
    cfg.updated_by = _actor_id()
    cfg.updated_at = datetime.now(timezone.utc)


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
            before,
            {"status": new_status, "justificacion": data.get("justificacion")},
            _client_ip(),
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
            before,
            {"estado": new_estado.value, "justificacion": data.get("justificacion")},
            _client_ip(),
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


# ==========================================================================
# DIVISIÓN REGIONAL — Reindexación de región desde la ubicación
# ==========================================================================
@blp.route("/regions/reindex")
class SuperAdminRegionsReindex(MethodView):
    @superadmin_required
    @blp.response(200)
    def post(self):
        """Reasigna la región de los usuarios a partir de su ubicación.

        Recorre los usuarios públicos y deriva su región desde Profile.zona
        (o la ubicación de su última solicitud). El personal interno no se
        toca. Idempotente: solo actualiza cuando la región cambia.
        """
        from app.services.region import assign_region
        from app.models.solicitud import Solicitud

        processed = 0
        updated = 0
        for user in User.query.all():
            if user.rol.value not in ("pds", "solicitante", "merchant"):
                continue
            processed += 1
            source = user.profile.zona if user.profile and user.profile.zona else None
            if not source:
                ultima = (
                    Solicitud.query.filter_by(solicitante_id=user.id)
                    .order_by(Solicitud.creado_en.desc())
                    .first()
                )
                source = ultima.ubicacion if ultima else None
            if assign_region(user, text=source):
                updated += 1

        write_audit(
            _actor_id(), "superadmin.regions.reindex", "system", None,
            None,
            {"processed": processed, "updated": updated},
            _client_ip(),
        )
        db.session.commit()
        return {"processed": processed, "updated": updated}
