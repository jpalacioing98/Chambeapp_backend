"""Admin blueprint (RBAC Fase 1): gestión de usuarios, verificaciones y stats.

Todos los endpoints requieren rol admin O superadmin (ver @admin_required).
Registrado en /api/v1/admin.
"""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.auth.decorators import admin_required
from app.models.user import User, RolUsuario, Verification
from app.models.service import Service
from app.models.order import Order
from app.models.payment import Payment, EstadoPago
from app.models.audit import write_audit
from app.schemas.admin import (
    UserListSchema,
    UserDetailSchema,
    UserListResponseSchema,
    RolePatchSchema,
    StatusPatchSchema,
    RejectSchema,
    VerificationListSchema,
    VerificationListResponseSchema,
    VerificationActionSchema,
    StatsOverviewSchema,
)

blp = Blueprint("admin", __name__, description="Panel administrativo (RBAC)")


def _actor_id() -> int:
    return int(get_jwt_identity())


def _client_ip() -> str:
    return request.remote_addr or "127.0.0.1"


@blp.route("/users")
class AdminUserList(MethodView):
    @admin_required
    @blp.response(200, UserListResponseSchema)
    def get(self):
        """Lista usuarios con filtros (rol, status, q) — máx 50."""
        query = User.query
        role = request.args.get("role")
        if role:
            query = query.filter(User.rol == RolUsuario(role))
        status = request.args.get("status")
        if status:
            query = query.filter(User.status == status)
        q = request.args.get("q")
        if q:
            like = f"%{q}%"
            query = query.filter(
                (User.email.ilike(like)) | (User.nombre.ilike(like))
            )
        total = query.count()
        users = query.order_by(User.id).limit(50).all()
        return {"items": users, "total": total}


@blp.route("/users/<int:user_id>")
class AdminUserDetail(MethodView):
    @admin_required
    @blp.response(200, UserDetailSchema)
    def get(self, user_id):
        """Detalle de un usuario."""
        user = db.get_or_404(User, user_id)
        return UserDetailSchema().dump(user)


@blp.route("/users/<int:user_id>/role")
class AdminUserRole(MethodView):
    @admin_required
    @blp.arguments(RolePatchSchema)
    @blp.response(200, UserDetailSchema)
    def patch(self, data, user_id):
        """Cambia el rol de un usuario (revoca tokens vía role_version++)."""
        user = db.get_or_404(User, user_id)
        new_role = data["role"]
        # Solo superadmin puede otorgar superadmin (el decorador ya admite admin).
        if new_role == "superadmin":
            abort(403, message="Solo un superadmin puede asignar el rol superadmin.")
        before = {"rol": user.rol.value}
        user.rol = RolUsuario(new_role)
        user.role_version += 1
        write_audit(
            _actor_id(), "user.role.update", "user", user.id,
            before, {"rol": new_role}, _client_ip(),
        )
        db.session.commit()
        return user


@blp.route("/users/<int:user_id>/status")
class AdminUserStatus(MethodView):
    @admin_required
    @blp.arguments(StatusPatchSchema)
    @blp.response(200, UserDetailSchema)
    def patch(self, data, user_id):
        """Suspende / bloquea / reactiva una cuenta."""
        user = db.get_or_404(User, user_id)
        new_status = data["status"]
        before = {"status": user.status}
        user.status = new_status
        user.role_version += 1  # revoca tokens activos
        write_audit(
            _actor_id(), "user.status.update", "user", user.id,
            before, {"status": new_status}, _client_ip(),
        )
        db.session.commit()
        return user


@blp.route("/stats/overview")
class AdminStats(MethodView):
    @admin_required
    @blp.response(200, StatsOverviewSchema)
    def get(self):
        """Métricas generales para el dashboard admin."""
        users_total = User.query.count()
        users_active = User.query.filter(User.status == "active").count()
        services_total = Service.query.count()
        orders_total = Order.query.count()
        revenue_total = (
            db.session.query(db.func.sum(Payment.monto))
            .filter(Payment.estado == EstadoPago.LIBERADO)
            .scalar()
            or 0
        )
        # No existe estado 'disputa' en el modelo Order actual → 0.
        disputes_open = 0
        return {
            "users_total": users_total,
            "users_active": users_active,
            "services_total": services_total,
            "orders_total": orders_total,
            "revenue_total": int(revenue_total),
            "disputes_open": disputes_open,
        }


@blp.route("/verifications")
class AdminVerificationList(MethodView):
    @admin_required
    @blp.response(200, VerificationListResponseSchema)
    def get(self):
        """Lista solicitudes de verificación (filtra por status, def. pending)."""
        status = request.args.get("status", "pending")
        verifs = (
            Verification.query.filter(Verification.status == status)
            .order_by(Verification.created_at.desc())
            .all()
        )
        items = []
        for v in verifs:
            user = db.session.get(User, v.user_id)
            d = VerificationListSchema().dump(v)
            d["nombre"] = user.nombre if user else None
            items.append(d)
        return {"items": items, "total": len(items)}


@blp.route("/verifications/<int:verif_id>/approve")
class AdminVerificationApprove(MethodView):
    @admin_required
    @blp.response(200, VerificationActionSchema)
    def post(self, verif_id):
        """Aprueba una verificación (KYC)."""
        v = db.get_or_404(Verification, verif_id)
        before = {"status": v.status}
        v.status = "approved"
        v.reviewed_by = _actor_id()
        v.reviewed_at = datetime.now(timezone.utc)
        write_audit(
            _actor_id(), "verification.approve", "verification", v.id,
            before, {"status": "approved"}, _client_ip(),
        )
        db.session.commit()
        return {"id": v.id, "status": v.status}


@blp.route("/verifications/<int:verif_id>/reject")
class AdminVerificationReject(MethodView):
    @admin_required
    @blp.arguments(RejectSchema)
    @blp.response(200, VerificationActionSchema)
    def post(self, data, verif_id):
        """Rechaza una verificación con motivo."""
        v = db.get_or_404(Verification, verif_id)
        before = {"status": v.status}
        v.status = "rejected"
        v.reviewed_by = _actor_id()
        v.reviewed_at = datetime.now(timezone.utc)
        v.reason = data["reason"]
        write_audit(
            _actor_id(), "verification.reject", "verification", v.id,
            before, {"status": "rejected", "reason": data["reason"]}, _client_ip(),
        )
        db.session.commit()
        return {"id": v.id, "status": v.status}
