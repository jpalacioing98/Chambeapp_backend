"""Salas Socket.IO del staff que revisa KYC.

Cada verificador/admin se une a la sala de su región; el superadmin y el
staff sin región asignada reciben eventos globales. Estas salas son
exclusivas del personal interno (no se exponen a clientes públicos).
"""

from app.models.user import RolUsuario

KYC_STAFF_ROLES = frozenset(
    {
        RolUsuario.VERIFICADOR,
        RolUsuario.ADMIN,
        RolUsuario.SUPERADMIN,
    }
)


def staff_kyc_room(user) -> str:
    """Sala a la que pertenece un usuario staff para eventos KYC."""
    if user.rol == RolUsuario.SUPERADMIN:
        return "staff:superadmin"
    if user.region_id is not None:
        return f"staff:region:{user.region_id}"
    return "staff:global"


def staff_kyc_rooms_for_region(region_id) -> list[str]:
    """Salas que deben recibir un documento KYC de una región concreta."""
    rooms = ["staff:superadmin", "staff:global"]
    if region_id is not None:
        rooms.append(f"staff:region:{region_id}")
    return rooms
