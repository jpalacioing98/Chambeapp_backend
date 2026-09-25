"""Users blueprint: perfil propio y público (RF-02, RF-03.4)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User, Profile
from app.models.solicitud import Rating
from app.schemas.users import (
    ProfileUpdateSchema,
    PublicProfileSchema,
    FotoPerfilSchema,
    FotoPerfilResponseSchema,
)
from app.schemas.auth import ProfileSchema

blp = Blueprint("users", __name__, description="Perfiles de usuario")


@blp.route("/me/foto-perfil")
class MyFotoPerfil(MethodView):
    @jwt_required()
    @blp.arguments(FotoPerfilSchema)
    @blp.response(200, FotoPerfilResponseSchema)
    def post(self, data):
        """Sube (o reemplaza) la foto de perfil del usuario autenticado.

        Recibe la imagen en base64, la optimiza a WebP (storage) y guarda
        la URL en Profile.foto_perfil.
        """
        user = db.get_or_404(User, int(get_jwt_identity()))
        profile = user.profile

        import base64
        import binascii

        b64 = data.get("archivo_base64", "")
        try:
            file_bytes = base64.b64decode(b64)
        except (binascii.Error, ValueError):
            abort(400, message="Imagen base64 inválida.")

        if not file_bytes:
            abort(400, message="La imagen está vacía.")

        filename = (data.get("nombre_archivo") or "foto.png").replace("/", "_")
        from app.services.storage import storage as storage_svc
        if storage_svc is None:
            abort(502, message="Servicio de almacenamiento no disponible.")
        try:
            url = storage_svc.upload_avatar(file_bytes, str(user.id), filename)
        except ValueError as e:
            abort(400, message=str(e))
        except Exception:
            abort(502, message="No se pudo subir la imagen.")

        profile.foto_perfil = url
        db.session.commit()

        return {"foto_perfil": url, "message": "Foto de perfil actualizada."}

    @jwt_required()
    @blp.response(200, FotoPerfilResponseSchema)
    def delete(self):
        """Elimina la foto de perfil del usuario autenticado."""
        user = db.get_or_404(User, int(get_jwt_identity()))
        user.profile.foto_perfil = None
        db.session.commit()
        return {"foto_perfil": None, "message": "Foto de perfil eliminada."}


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
        """RF-02: actualiza perfil; marca perfil_completo si hay categoría/habilidad.

        Soporta edición de datos de cuenta (nombre/teléfono), ubicación
        (zona + coordenadas) y los campos profesionales del perfil.
        """
        user = db.get_or_404(User, int(get_jwt_identity()))
        profile = user.profile

        for field in ("habilidades", "experiencia", "zona", "categorias", "portafolio"):
            if field in data:
                setattr(profile, field, data[field])

        # Datos de cuenta (User) y ubicación geo (Profile)
        if "nombre" in data:
            user.nombre = data["nombre"] or None
        if "telefono" in data:
            user.telefono = data["telefono"] or None
        if "latitud" in data:
            profile.latitud = data["latitud"]
        if "longitud" in data:
            profile.longitud = data["longitud"]

        cats = profile.categorias or []
        habs = profile.habilidades or []
        if (isinstance(cats, list) and len(cats) > 0) or (
            isinstance(habs, list) and len(habs) > 0
        ):
            profile.perfil_completo = True

        # División regional: deriva la región del usuario desde su zona.
        try:
            from app.services.region import assign_region
            assign_region(user, text=profile.zona)
        except Exception:
            pass

        db.session.commit()

        # P2-5: Badge awarding after profile update
        try:
            from app.services.badges import check_and_award_all
            check_and_award_all(user.id)
            db.session.commit()
        except Exception:
            pass

        return profile


@blp.route("/badges")
class UserBadges(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self):
        """P2-5: returns all badge types with awarded status for current user."""
        from app.services.badges import get_user_badges
        user_id = int(get_jwt_identity())
        return get_user_badges(user_id)


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

        # Habilidades con su RUTA de niveles + cuáles certificó este usuario.
        from app.models.habilidad import Habilidad, HabilidadNivel
        habilidades_detalle = []
        for nombre in (profile.habilidades or []):
            hab = Habilidad.query.filter(
                Habilidad.nombre.ilike(nombre.strip())
            ).first()
            if not hab:
                continue
            completados = {
                n.nivel_index
                for n in HabilidadNivel.query.filter_by(
                    user_id=user_id, habilidad_id=hab.id
                ).all()
            }
            habilidades_detalle.append({
                "habilidad_id": hab.id,
                "nombre": hab.nombre,
                "descripcion": hab.descripcion,
                "competencias": hab.habilidades or [],
                "niveles": [
                    {
                        "nombre": n.get("nombre", f"Nivel {i + 1}"),
                        "tipo": n.get("tipo", "certificacion"),
                        "certificado": i in completados,
                    }
                    for i, n in enumerate(hab.niveles or [])
                ],
            })

# Formación técnica certificada (Vista 3: sellos SENA / Maestro).
        from app.models.habilidad import CertificacionTecnica as _CertTec
        certificaciones = [
            {
                "titulo": c.titulo,
                "institucion": c.institucion,
                "anio": c.anio,
                "estado": c.estado,
                "codigo_verificacion": c.codigo_verificacion,
            }
            for c in _CertTec.query.filter_by(user_id=user_id).order_by(
                _CertTec.creado_en.desc()
            ).all()
        ]

        return {
            "id": user.id,
"email": user.email,
              "nombre": user.nombre,
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
            "foto_perfil": profile.foto_perfil,
            "habilidades_detalle": habilidades_detalle,
            "certificaciones": certificaciones,
            "ratings_recientes": ratings,
            "sin_calificaciones": len(ratings) == 0,
        }
