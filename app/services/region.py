"""Servicio de división regional — derivación de región desde la ubicación.

Regla de negocio (Fase 4):
  - La región de un usuario se deriva automáticamente de su ubicación
    (Profile.zona o la `ubicacion` de sus solicitudes) comparando el texto
    contra los departamentos de cada región del catálogo.
  - El personal interno (admin/verificador/soporte/superadmin) NO se
    reasigna automáticamente: su región la decide el superadmin.
  - Si no hay coincidencia la región queda en NULL (sin asignar).

También se define aquí la REGLA DE PROPIEDAD para controlar el doble
conteo: un contrato/disputa pertenece a la región del SOLICITANTE
(comprador), por lo que cada caso se cuenta y se modera en una sola
región.
"""

from app.extensions import db
from app.models.region import Region
from app.models.user import User, RolUsuario

_STAFF_ROLES = {
    RolUsuario.ADMIN.value,
    RolUsuario.SUPERADMIN.value,
    RolUsuario.VERIFICADOR.value,
    RolUsuario.SOPORTE.value,
}


def match_region_from_text(text: str | None) -> Region | None:
    """Devuelve la primera región cuyo departamento aparezca en el texto.

    Ej.: "Valledupar, Cesar" -> Región Caribe (contiene "Cesar").
    """
    if not text:
        return None
    t = text.lower()
    for region in Region.query.order_by(Region.id).all():
        for dept in region.departamentos or []:
            if dept and dept.lower() in t:
                return region
    return None


def assign_region(user, text: str | None = None) -> bool:
    """Asigna la región del usuario derivada de su ubicación (si cambia).

    `text`: ubicación a evaluar; si es None usa Profile.zona.
    Devuelve True si la región cambió. Nunca reasigna personal interno.
    """
    if user is None:
        return False
    if user.rol.value in _STAFF_ROLES:
        return False
    source = text or (user.profile.zona if user.profile else None) or ""
    region = match_region_from_text(source)
    if region is None:
        return False
    if user.region_id != region.id:
        user.region_id = region.id
        return True
    return False


def contract_owned_by_region(contract, scope: int | None) -> bool:
    """True si el contrato pertenece a la región del solicitante.

    Regla de propiedad anti doble-conteo: la región del solicitante es la
    única dueña del contrato (y de sus disputas/pagos).
    """
    if scope is None:
        return True
    if contract is None:
        return False
    solicitante = db.session.get(User, contract.solicitante_id)
    return bool(solicitante and solicitante.region_id == scope)