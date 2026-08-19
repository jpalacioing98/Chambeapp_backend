"""Users blueprint: perfil propio y público (RF-02, RF-03.4)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, Profile
from app.models.solicitud import Rating
from app.schemas.users import ProfileUpdateSchema, PublicProfileSchema
from app.schemas.auth import ProfileSchema

blp = Blueprint("users", __name__, description="Perfiles de usuario")


@blp.route("/me/profile")
class MyProfile(MethodView):
    @jwt_required()
    @blp.response(200, ProfileSchema)
    def get(self):
        """RF-02: perfil del usuario autenticado."""
        user = db.get_or_404(User, int(get_jwt_identity()))
        return user.profile

    @jwt_required()
    @blp.arguments(ProfileUpdateSchema)
    @blp.response(200, ProfileSchema)
    def put(self, data):
        """RF-02: actualiza perfil; marca perfil_completo si hay categoría/habilidad."""
        user = db.get_or_404(User, int(get_jwt_identity()))
        profile = user.profile
        for field in ("habilidades", "experiencia", "zona", "categorias", "portafolio"):
            if field in data:
                setattr(profile, field, data[field])

        cats = profile.categorias or []
        habs = profile.habilidades or []
        if (isinstance(cats, list) and len(cats) > 0) or (
            isinstance(habs, list) and len(habs) > 0
        ):
            profile.perfil_completo = True

        db.session.commit()
        return profile


@blp.route("/<int:user_id>/profile")
class PublicProfile(MethodView):
    @blp.response(200, PublicProfileSchema)
    def get(self, user_id):
        """RF-03.4: perfil público + calificación promedio + ratings recientes."""
        user = db.get_or_404(User, user_id)
        profile = user.profile

        ratings = (
            Rating.query.filter_by(calificado_id=user_id)
            .order_by(Rating.creado_en.desc())
            .limit(10)
            .all()
        )

        return {
            "id": user.id,
            "email": user.email,
            "rol": user.rol,
            "habilidades": profile.habilidades,
            "experiencia": profile.experiencia,
            "zona": profile.zona,
            "categorias": profile.categorias,
            "portafolio": profile.portafolio,
            "calificacion_promedio": profile.calificacion_promedio,
            "verificado": profile.verificado,
            "badges": profile.badges,
            "perfil_completo": profile.perfil_completo,
            "ratings_recientes": ratings,
            "sin_calificaciones": len(ratings) == 0,
        }
