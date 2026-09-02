"""Service layer: badge management and awarding logic (P2-5)."""

from app.extensions import db
from app.models.user import User, Profile
from app.models.contract import Contract, EstadoContrato
from app.models.badges import BadgeType
from app.models.payment import Payment, EstadoPago


def _has_badge(profile: Profile, badge: BadgeType) -> bool:
    """Check if profile already has the badge."""
    badges = profile.badges or []
    return badge.value in badges


def award_badge(user_id: int, badge: BadgeType) -> bool:
    """Award a badge to a user if not already present. Returns True if awarded."""
    profile = db.session.get(Profile, user_id)
    if profile is None:
        return False
    if _has_badge(profile, badge):
        return False
    badges = profile.badges or []
    badges.append(badge.value)
    profile.badges = badges
    db.session.flush()
    return True


def check_and_award_contract_badges(user_id: int) -> list:
    """Check contract count and award相应 badges."""
    awarded = []
    count = Contract.query.filter(
        Contract.proveedor_id == user_id,
        Contract.estado == EstadoContrato.COMPLETADO,
    ).count()

    if count >= 1:
        if award_badge(user_id, BadgeType.PRIMER_CONTRATO):
            awarded.append(BadgeType.PRIMER_CONTRATO.value)
    if count >= 10:
        if award_badge(user_id, BadgeType.DIEZ_CONTRATOS):
            awarded.append(BadgeType.DIEZ_CONTRATOS.value)
    if count >= 100:
        if award_badge(user_id, BadgeType.CIEN_CONTRATOS):
            awarded.append(BadgeType.CIEN_CONTRATOS.value)

    return awarded


def check_and_award_all(user_id: int) -> list:
    """Full check of all badge conditions for a user. Returns list of awarded badges."""
    awarded = []

    # Contract-based badges
    awarded.extend(check_and_award_contract_badges(user_id))

    # Profile completeness
    profile = db.session.get(Profile, user_id)
    if profile:
        # Check profile completeness
        cats = profile.categorias or []
        habs = profile.habilidades or []
        if (isinstance(cats, list) and len(cats) > 0) or (
            isinstance(habs, list) and len(habs) > 0
        ):
            if award_badge(user_id, BadgeType.PERFIL_COMPLETO):
                awarded.append(BadgeType.PERFIL_COMPLETO.value)

        # Check verified
        if profile.verificado:
            if award_badge(user_id, BadgeType.VERIFICADO):
                awarded.append(BadgeType.VERIFICADO.value)

        # Check top rated (4.5+ with at least 5 ratings)
        if profile.calificacion_promedio >= 4.5:
            from app.models.solicitud import Rating

            rating_count = Rating.query.filter_by(calificado_id=user_id).count()
            if rating_count >= 5:
                if award_badge(user_id, BadgeType.TOP_RATED):
                    awarded.append(BadgeType.TOP_RATED.value)

        # Check sin disputas (completed contracts with no disputes)
        from app.models.contract import Dispute

        completed_count = Contract.query.filter(
            Contract.proveedor_id == user_id,
            Contract.estado == EstadoContrato.COMPLETADO,
        ).count()
        dispute_count = (
            Dispute.query.join(Contract)
            .filter(Contract.proveedor_id == user_id)
            .count()
        )
        if completed_count >= 1 and dispute_count == 0:
            if award_badge(user_id, BadgeType.SIN_DISPUTAS):
                awarded.append(BadgeType.SIN_DISPUTAS.value)

        # Check monedero_activo (has completed payments)
        payment_count = (
            Payment.query.join(Contract)
            .filter(
                Contract.proveedor_id == user_id,
                Payment.estado == EstadoPago.COMPLETADO,
            )
            .count()
        )
        if payment_count > 0:
            if award_badge(user_id, BadgeType.MONEDERO_ACTIVO):
                awarded.append(BadgeType.MONEDERO_ACTIVO.value)

    return awarded


def get_user_badges(user_id: int) -> list:
    """Get all badge types with awarded status for a user."""
    profile = db.session.get(Profile, user_id)
    earned = set(profile.badges or []) if profile else set()

    result = []
    for badge_type in BadgeType:
        result.append({
            "type": badge_type.value,
            "name": badge_type.value.replace("_", " ").title(),
            "awarded": badge_type.value in earned,
        })
    return result


def check_and_award_first_service(user_id: int) -> list:
    """Check and award first service badge (PRIMER_SERVICIO)."""
    awarded = []
    completed = Contract.query.filter(
        Contract.proveedor_id == user_id,
        Contract.estado == EstadoContrato.COMPLETADO,
    ).count()
    if completed >= 1:
        if award_badge(user_id, BadgeType.PRIMER_SERVICIO):
            awarded.append(BadgeType.PRIMER_SERVICIO.value)
    return awarded
