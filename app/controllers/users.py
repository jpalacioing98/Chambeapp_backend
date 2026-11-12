"""Users blueprint: perfil propio y público (RF-02, RF-03.4)."""

from flask import request
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


def _verificado_efectivo(user) -> bool:
    """Verificación real según los documentos KYC aprobados del rol.

    GET no debe mutar: se devuelve el cálculo sin tocar el flag. El flag se
    sincroniza al publicar una solicitud o al revisar un documento.
    """
    from app.services.verificacion import esta_verificado

    return esta_verificado(user)


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
            # Bucket PÚBLICO de avatares: la foto se muestra en perfiles
            # públicos, así que la URL debe resolver en el navegador.
            url = storage_svc.upload_public_avatar(file_bytes, str(user.id), filename)
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

        # Mantiene Profile.geom sincronizado: el retrieval PostGIS solo ve
        # proveedores cuya geometría está poblada (y no solo lat/lng).
        if "latitud" in data or "longitud" in data:
            if profile.latitud is not None and profile.longitud is not None:
                profile.geom = (
                    f"SRID=4326;POINT({profile.longitud} {profile.latitud})"
                )
            else:
                profile.geom = None

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


@blp.route("/me/stats")
class MyStats(MethodView):
    """Estadísticas reales del perfil (portafolio del PDS).

    · chambas_completadas → contratos cerrados como proveedor.
    · rating_promedio / rating_count → tabla de calificaciones.
    · tiempo_respuesta_seg → mediana del tiempo entre solicitud y oferta.
    """

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())

        from app.models.chamba import Chamba, EstadoChamba
        from app.models.contract import Contract, EstadoContrato
        from app.models.oferta import Oferta
        from app.models.solicitud import Solicitud

        profile = db.session.get(Profile, user_id)

        # Chambas cerradas: contrato completado o chamba finalizada
        # (puede haber chamba finalizada con el contrato aún en progreso).
        ids_cerradas: set[int] = {
            cid
            for (cid,) in db.session.query(Contract.id).filter_by(
                proveedor_id=user_id, estado=EstadoContrato.COMPLETADO
            )
        }
        ids_cerradas.update(
            cid
            for (cid,) in db.session.query(Chamba.contract_id)
            .join(Contract, Contract.id == Chamba.contract_id)
            .filter(
                Contract.proveedor_id == user_id,
                Chamba.estado == EstadoChamba.FINALIZADA,
            )
        )
        completadas = len(ids_cerradas)

        # Las chambas guardan su propia calificación (Hito 6) y no siempre
        # crean una fila en `ratings`: se combinan ambas fuentes.
        ratings_tabla = Rating.query.filter_by(calificado_id=user_id).all()
        servicios_calificados = {r.service_id for r in ratings_tabla}
        filas_chamba = (
            db.session.query(Chamba.rating_estrellas, Contract.service_id)
            .join(Contract, Contract.id == Chamba.contract_id)
            .filter(
                Contract.proveedor_id == user_id,
                Chamba.rating_estrellas.isnot(None),
            )
            .all()
        )
        puntajes = [int(r.puntaje) for r in ratings_tabla]
        puntajes += [
            int(estrellas)
            for estrellas, service_id in filas_chamba
            if estrellas is not None and service_id not in servicios_calificados
        ]

        rating_count = len(puntajes)
        rating_promedio = (
            round(sum(puntajes) / len(puntajes), 2)
            if puntajes
            else float(profile.calificacion_promedio or 0)
            if profile
            else 0
        )

        rows = (
            db.session.query(Oferta.created_at, Solicitud.creado_en)
            .join(Solicitud, Oferta.solicitud_id == Solicitud.id)
            .filter(Oferta.pds_id == user_id)
            .order_by(Oferta.created_at.desc())
            .limit(100)
            .all()
        )
        deltas: list[float] = []
        for oferta_creada, solicitud_creada in rows:
            if not oferta_creada or not solicitud_creada:
                continue
            try:
                segundos = (oferta_creada - solicitud_creada).total_seconds()
            except TypeError:
                continue
            if segundos >= 0:
                deltas.append(segundos)

        respuesta = (
            round(sum(deltas) / len(deltas)) if deltas else None
        )

        return {
            "chambas_completadas": completadas,
            "rating_promedio": rating_promedio,
            "rating_count": rating_count,
            "tiempo_respuesta_seg": respuesta,
        }


@blp.route("/me/reviews")
class MyReviews(MethodView):
    """Últimos comentarios recibidos (calificaciones al PDS)."""

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        limit = request.args.get("limit", default=5, type=int)
        limit = max(1, min(limit or 5, 20))

        from app.models.solicitud import Solicitud

        rows = (
            db.session.query(Rating, User.nombre, Solicitud.titulo)
            .outerjoin(User, User.id == Rating.autor_id)
            .outerjoin(Solicitud, Solicitud.id == Rating.service_id)
            .filter(Rating.calificado_id == user_id)
            .order_by(Rating.creado_en.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": rating.id,
                "puntaje": rating.puntaje,
                "comentario": rating.comentario,
                "creado_en": rating.creado_en.isoformat()
                if rating.creado_en
                else None,
                "autor": autor or f"Usuario #{rating.autor_id}",
                "servicio": servicio or f"Solicitud #{rating.service_id}",
            }
            for rating, autor, servicio in rows
        ]


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

        # Los perfiles guardan slugs cortos ("plomeria", "limpieza"…) y el
        # catálogo usa nombres largos ("Plomería y Fontanería"). Se resuelve
        # por alias y, si no, por coincidencia parcial.
        ALIAS_HABILIDAD = {
            "plomeria": "Plomería y Fontanería",
            "limpieza": "Aseo, Limpieza General y Mantenimiento de Espacios",
            "carpinteria": "Carpintería en Madera, MDF y RH (Mueble Fijo y RTA)",
            "calentadores": "Mantenimiento e Instalación de Aire Acondicionado y Climatización",
        }

        habilidades_detalle = []
        for nombre in (profile.habilidades or []):
            clave = nombre.strip()
            hab = Habilidad.query.filter(
                Habilidad.nombre.ilike(clave)
            ).first()
            if not hab:
                alias = ALIAS_HABILIDAD.get(clave.lower())
                if alias:
                    hab = Habilidad.query.filter(
                        Habilidad.nombre.ilike(alias)
                    ).first()
            if not hab:
                hab = Habilidad.query.filter(
                    Habilidad.nombre.ilike(f"%{clave}%")
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
            # Estado real (documentos aprobados), no el flag que puede
            # quedar obsoleto en datos sembrados o migrados.
            "verificado": _verificado_efectivo(user),
            "badges": profile.badges,
            "perfil_completo": profile.perfil_completo,
            "foto_perfil": profile.foto_perfil,
            "habilidades_detalle": habilidades_detalle,
            "certificaciones": certificaciones,
            "ratings_recientes": ratings,
            "sin_calificaciones": len(ratings) == 0,
        }
