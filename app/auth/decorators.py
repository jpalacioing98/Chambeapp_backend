"""RBAC decorators (Fase 1): control de acceso por rol con revocación de token.

Jerarquía:
  - role_required(allowed_roles): cualquier rol listado.
  - admin_required: admin O superadmin.
  - superadmin_required: solo superadmin.

El token JWT lleva claims `role` y `role_v` (role_version). Si el `role_v`
del token difiere del de la BD (cambio de rol/estado), se revoca (401).
"""

from functools import wraps

from flask_smorest import abort
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from app.extensions import db
from app.models.user import User


def role_required(allowed_roles: list[str]):
    """Decorador: exige JWT y que el rol del claim esté en `allowed_roles`."""

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            role = claims.get("role")
            if role not in allowed_roles:
                abort(403, message="No tienes permiso para realizar esta acción.")

            # Revocación por cambio de rol/estado: el role_version debe coincidir.
            identity = get_jwt_identity()
            user = db.session.get(User, int(identity))
            if user is None:
                abort(401, message="Usuario no encontrado.")
            if claims.get("role_v") != user.role_version:
                abort(401, message="Sesión revocada: el rol o estado cambió.")

            return fn(*args, **kwargs)

        return wrapper

    return decorator


# admin O superadmin (jerarquía corregida respecto al chequeo previo de solo admin).
admin_required = role_required(["admin", "superadmin"])
superadmin_required = role_required(["superadmin"])
