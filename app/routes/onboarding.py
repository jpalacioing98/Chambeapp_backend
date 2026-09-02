"""Onboarding blueprint: guided profile setup for new users (P2-2)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, Profile
from app.schemas.onboarding import (
    OnboardingStatusSchema,
    OnboardingStepSchema,
)
from app.schemas.auth import ProfileSchema

blp = Blueprint("onboarding", __name__, description="Onboarding guiado (P2-2)")


@blp.route("/status")
class OnboardingStatus(MethodView):
    @jwt_required()
    @blp.response(200, OnboardingStatusSchema)
    def get(self):
        """P2-2: obtiene el estado del onboarding del usuario."""
        user_id = int(get_jwt_identity())
        user = db.get_or_404(User, user_id)
        profile = user.profile
        if profile is None:
            profile = Profile(user_id=user_id)
            db.session.add(profile)
            db.session.flush()
        return {
            "completed": profile.onboarding_completed,
            "step": profile.onboarding_step,
            "profile": ProfileSchema().dump(profile),
        }


@blp.route("/step")
class OnboardingStep(MethodView):
    @jwt_required()
    @blp.arguments(OnboardingStepSchema)
    @blp.response(200, OnboardingStatusSchema)
    def patch(self, data):
        """P2-2: guarda datos de un paso del onboarding."""
        user_id = int(get_jwt_identity())
        user = db.get_or_404(User, user_id)
        profile = user.profile
        if profile is None:
            profile = Profile(user_id=user_id)
            db.session.add(profile)
            db.session.flush()

        step = data["step"]
        step_data = data.get("data") or {}

        profile.onboarding_step = max(profile.onboarding_step, step)

        # Apply common onboarding fields
        if "habilidades" in step_data:
            profile.habilidades = step_data["habilidades"]
        if "categorias" in step_data:
            profile.categorias = step_data["categorias"]
        if "experiencia" in step_data:
            profile.experiencia = step_data["experiencia"]
        if "zona" in step_data:
            profile.zona = step_data["zona"]

        # Check if profile is now complete
        cats = profile.categorias or []
        habs = profile.habilidades or []
        if (isinstance(cats, list) and len(cats) > 0) or (
            isinstance(habs, list) and len(habs) > 0
        ):
            profile.perfil_completo = True

        db.session.commit()
        return {
            "completed": profile.onboarding_completed,
            "step": profile.onboarding_step,
            "profile": ProfileSchema().dump(profile),
        }


@blp.route("/complete")
class OnboardingComplete(MethodView):
    @jwt_required()
    @blp.response(200, OnboardingStatusSchema)
    def post(self):
        """P2-2: marca el onboarding como completado."""
        user_id = int(get_jwt_identity())
        user = db.get_or_404(User, user_id)
        profile = user.profile
        if profile is None:
            profile = Profile(user_id=user_id)
            db.session.add(profile)
            db.session.flush()

        profile.onboarding_completed = True
        profile.onboarding_step = 999  # All steps done

        # Check completeness
        cats = profile.categorias or []
        habs = profile.habilidades or []
        if (isinstance(cats, list) and len(cats) > 0) or (
            isinstance(habs, list) and len(habs) > 0
        ):
            profile.perfil_completo = True

        # Check badge awarding
        try:
            from app.services.badges import check_and_award_all
            check_and_award_all(user_id)
        except Exception:
            pass

        db.session.commit()
        return {
            "completed": profile.onboarding_completed,
            "step": profile.onboarding_step,
            "profile": ProfileSchema().dump(profile),
        }
