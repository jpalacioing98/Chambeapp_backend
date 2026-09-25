"""Scope regional para el panel administrativo.

Un usuario del staff (admin, verificador, soporte) pertenece a una región
(User.region_id). Su alcance operativo queda limitado a esa región.

Reglas:
  - superadmin: sin región (None) → ve todo (global).
  - Personal sin región asignada: None → comportamiento global (backward
    compatible con usuarios internos creados antes de la división regional).
  - Personal con región: acotado a su región.
"""

from app.models.user import RolUsuario


def region_scope_id(user) -> int | None:
    """Devuelve la región que acota a un actor staff (None = sin límite)."""
    if user is None:
        return None
    if user.rol == RolUsuario.SUPERADMIN:
        return None
    return user.region_id


def apply_scope(query, model_user_col, scope_id):
    """Aplica el filtro regional a una query ya unida con User.

    query: query de SQLAlchemy (ya incluye un join a User en `model_user_col`).
    scope_id: id de región del actor (None = sin filtro).
    """
    if scope_id is None:
        return query
    return query.filter(model_user_col == scope_id)