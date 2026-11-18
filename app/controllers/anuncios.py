"""Anuncios blueprint: ofertas laborales de negocios.

Los anuncios son banners de CONTACTO, independientes de las solicitudes.
PDS y solicitantes pueden postularse; el negocio gestiona el contacto,
marca un único perfil seleccionado y cierra el anuncio (con motivo si no
seleccionó a nadie). Las postulaciones NUNCA generan contratos.
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.services.realtime import safe_emit
from app.models.user import User, RolUsuario
from app.models.anuncio import (
    AnuncioLaboral,
    EstadoAnuncio,
    ModalidadAnuncio,
    AnuncioPostulacion,
    EstadoPostulacionAnuncio,
)
from app.schemas.anuncio import (
    AnuncioCreateSchema,
    AnuncioEstadoSchema,
    AnuncioPostulacionCreateSchema,
    AnuncioPostulacionSchema,
    AnuncioSchema,
    PostulacionEstadoSchema,
)
from app.controllers.notifications import crear_notificacion

blp = Blueprint("anuncios", __name__, description="Anuncios laborales de negocios")

ROL_NEGOCIO = RolUsuario.MERCHANT.value  # "merchant"
ROLES_POSTULANTES = (RolUsuario.PDS.value, RolUsuario.SOLICITANTE.value)


def _emit_anuncio(event: str, anuncio: AnuncioLaboral, target_user_id: int) -> None:
    """Emite el anuncio COMPLETO a la sala del usuario destinatario."""
    payload = AnuncioSchema().dump(_anuncio_con_negocio(anuncio))
    payload["postulaciones_count"] = len(anuncio.postulaciones)
    safe_emit(event, payload, room=f"user:{target_user_id}")


def _anuncio_con_negocio(anuncio: AnuncioLaboral) -> AnuncioLaboral:
    anuncio.negocio_nombre = (
        anuncio.negocio.nombre or f"Negocio #{anuncio.negocio_id}"
    )
    anuncio.vacantes_disponibles = anuncio.vacantes or 0
    return anuncio


@blp.route("/")
class AnuncioRoot(MethodView):
    @jwt_required()
    @blp.arguments(AnuncioCreateSchema)
    @blp.response(201, AnuncioSchema)
    def post(self, data):
        """El negocio publica un anuncio laboral (contacto o vinculante)."""
        user_id = int(get_jwt_identity())
        if get_jwt().get("role") != ROL_NEGOCIO:
            abort(403, message="Solo un negocio puede publicar anuncios laborales.")

        from app.services.verificacion import exigir_verificado

        exigir_verificado(
            user_id, "REQUIRE_KYC_TO_MERCHANT", "publicar anuncios laborales"
        )

        tipo = data.get("tipo") or "empleo"
        if data.get("modalidad") == ModalidadAnuncio.CONTRATO.value:
            abort(
                400,
                message="Los anuncios son solo de contacto: no generan contratos.",
            )
        presupuesto = data.get("presupuesto") if tipo != "empleo" else None

        anuncio = AnuncioLaboral(
            negocio_id=user_id,
            titulo=data["titulo"],
            descripcion=data["descripcion"],
            categoria=data["categoria"],
            tipo=tipo,
            visible_mapa=bool(data.get("visible_mapa", True)),
            ubicacion=data.get("ubicacion"),
            latitud=data.get("latitud"),
            longitud=data.get("longitud"),
            vacantes=data.get("vacantes") if tipo == "empleo" else None,
            modalidad=ModalidadAnuncio.CONTACTO,
            presupuesto=presupuesto,
            fecha_deseada=None,
            horario=None,
            contract_ids=[],
            estado=EstadoAnuncio.PUBLICADO,
        )
        db.session.add(anuncio)
        db.session.flush()

        # Cobro en monedas por publicar (después de validar KYC y datos).
        from app.services.cobros import cobrar_monedas, costo_anuncio

        costo = costo_anuncio("publicar")
        if costo > 0:
            try:
                cobrar_monedas(
                    user_id,
                    costo,
                    f"ANUNCIO-PUB-{anuncio.id}",
                    f"Publicación de anuncio #{anuncio.id}",
                )
            except ValueError:
                db.session.rollback()
                abort(
                    400,
                    message=(
                        f"MONEDAS_INSUFICIENTES:{costo}:Necesitas {costo} "
                        "monedas para publicar el anuncio. Recarga tu "
                        "billetera y vuelve a intentarlo."
                    ),
                )

        db.session.commit()
        payload = AnuncioSchema().dump(_anuncio_con_negocio(anuncio))
        safe_emit("anuncio:actualizado", payload, room=f"user:{user_id}")
        # Solo a clientes con un feed de anuncios montado (mapa/listado),
        # no a todos los conectados de la plataforma.
        safe_emit("anuncio:nuevo", payload, room="anuncios")
        return _anuncio_con_negocio(anuncio)

    @blp.response(200)
    def get(self):
        """Feed público de anuncios visibles en el mapa (todos los roles)."""
        query = AnuncioLaboral.query.filter_by(estado=EstadoAnuncio.PUBLICADO)
        query = query.filter(AnuncioLaboral.visible_mapa.is_(True))
        query = query.order_by(AnuncioLaboral.creado_en.desc())
        categoria = request.args.get("categoria")
        if categoria:
            query = query.filter(AnuncioLaboral.categoria == categoria)
        anuncios = query.all()
        for a in anuncios:
            _anuncio_con_negocio(a)
        return AnuncioSchema(many=True).dump(anuncios)


@blp.route("/negocio/<int:uid>")
class AnunciosDelNegocio(MethodView):
    @jwt_required(optional=True)
    @blp.response(200)
    def get(self, uid):
        """Anuncios del negocio (dueño ve todos + contadores; otros solo publicados)."""
        identity = get_jwt_identity()
        user_id = int(identity) if identity is not None else None
        es_dueño = user_id == uid
        query = AnuncioLaboral.query.filter_by(negocio_id=uid)
        if not es_dueño:
            query = query.filter_by(estado=EstadoAnuncio.PUBLICADO)
        anuncios = query.order_by(AnuncioLaboral.creado_en.desc()).all()
        for a in anuncios:
            _anuncio_con_negocio(a)
        dump = AnuncioSchema(many=True).dump(anuncios)
        if es_dueño:
            for a, item in zip(anuncios, dump):
                item["postulaciones_count"] = len(a.postulaciones)
        return dump


@blp.route("/<int:anuncio_id>")
class AnuncioDetail(MethodView):
    @jwt_required(optional=True)
    @blp.response(200)
    def get(self, anuncio_id):
        """Detalle del anuncio (postulaciones solo para el dueño)."""
        identity = get_jwt_identity()
        user_id = int(identity) if identity is not None else None
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        es_dueño = user_id is not None and anuncio.negocio_id == user_id
        dump = AnuncioSchema().dump(_anuncio_con_negocio(anuncio))
        if es_dueño:
            for postulacion in anuncio.postulaciones:
                postulacion.pds_nombre = (
                    postulacion.pds.nombre or f"Postulante #{postulacion.pds_id}"
                )
            dump["postulaciones"] = AnuncioPostulacionSchema(many=True).dump(
                anuncio.postulaciones
            )
        else:
            dump["postulaciones"] = []
        dump["postulaciones_count"] = len(anuncio.postulaciones)
        return dump


@blp.route("/<int:anuncio_id>/estado")
class AnuncioEstado(MethodView):
    @jwt_required()
    @blp.arguments(AnuncioEstadoSchema)
    @blp.response(200, AnuncioSchema)
    def patch(self, data, anuncio_id):
        """El negocio cierra/reabre su anuncio."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño puede gestionar el anuncio.")
        accion = data["accion"]
        if accion == "cerrar":
            if anuncio.estado == EstadoAnuncio.CERRADO:
                abort(400, message="El anuncio ya está cerrado.")
            seleccionada = AnuncioPostulacion.query.filter_by(
                anuncio_id=anuncio.id, seleccionado=True
            ).first()
            motivo = (data.get("motivo") or "").strip()
            if seleccionada is None and not motivo:
                abort(
                    400,
                    message=(
                        "Selecciona un postulante antes de cerrar o indica el "
                        "motivo por el que cierras sin selección."
                    ),
                )
            anuncio.motivo_cierre = motivo or None
            anuncio.estado = EstadoAnuncio.CERRADO
        else:
            if anuncio.estado == EstadoAnuncio.PUBLICADO:
                abort(400, message="El anuncio ya está publicado.")
            anuncio.motivo_cierre = None
            # Reactivar tiene costo en monedas.
            import time

            from app.services.cobros import cobrar_monedas, costo_anuncio

            costo = costo_anuncio("reactivar")
            if costo > 0:
                try:
                    cobrar_monedas(
                        user_id,
                        costo,
                        f"ANUNCIO-REACT-{anuncio.id}-{int(time.time())}",
                        f"Reactivación de anuncio #{anuncio.id}",
                    )
                except ValueError:
                    abort(
                        400,
                        message=(
                            f"MONEDAS_INSUFICIENTES:{costo}:Necesitas {costo} "
                            "monedas para reactivar el anuncio. Recarga tu "
                            "billetera y vuelve a intentarlo."
                        ),
                    )
            anuncio.estado = EstadoAnuncio.PUBLICADO
        db.session.commit()
        payload = AnuncioSchema().dump(_anuncio_con_negocio(anuncio))
        safe_emit("anuncio:actualizado", payload, room=f"user:{user_id}")
        safe_emit("anuncio:cambio_estado", payload, room="anuncios")
        return _anuncio_con_negocio(anuncio)


@blp.route("/<int:anuncio_id>/postulaciones")
class AnuncioPostulacionList(MethodView):
    @jwt_required()
    @blp.arguments(AnuncioPostulacionCreateSchema)
    @blp.response(201, AnuncioPostulacionSchema)
    def post(self, data, anuncio_id):
        """Un PDS se postula (contacto en anuncios libres; contrato en los vinculantes)."""
        user_id = int(get_jwt_identity())
        rol = get_jwt().get("role")
        if rol not in ROLES_POSTULANTES:
            abort(
                403,
                message=(
                    "Solo un PDS o un solicitante puede postularse a un "
                    "anuncio laboral."
                ),
            )

        from app.services.verificacion import exigir_verificado

        exigir_verificado(
            user_id, "REQUIRE_KYC_TO_OFFER", "postularte a un anuncio"
        )

        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id == user_id:
            abort(403, message="No puedes postularte a tu propio anuncio.")
        if anuncio.estado != EstadoAnuncio.PUBLICADO:
            abort(400, message="El anuncio ya no acepta postulaciones.")
        ya = AnuncioPostulacion.query.filter_by(
            anuncio_id=anuncio.id, pds_id=user_id
        ).first()
        if ya:
            abort(400, message="Ya te postulaste a este anuncio.")

        # Contacto por defecto desde los datos del postulante.
        user = db.session.get(User, user_id)
        postulacion = AnuncioPostulacion(
            anuncio_id=anuncio.id,
            pds_id=user_id,
            postulante_rol=rol,
            mensaje=data.get("mensaje"),
            telefono_contacto=data.get("telefono_contacto") or (user.telefono if user else None),
            email_contacto=data.get("email_contacto") or (user.email if user else None),
            estado=EstadoPostulacionAnuncio.PENDIENTE,
        )
        db.session.add(postulacion)
        db.session.commit()
        crear_notificacion(
            anuncio.negocio_id,
            "anuncio_postulacion",
            f"Un postulante se postuló a tu anuncio: {anuncio.titulo}.",
        )
        _emit_anuncio("anuncio:postulacion", anuncio, anuncio.negocio_id)
        postulacion.pds_nombre = postulacion.pds.nombre or f"Postulante #{user_id}"
        return postulacion

    @jwt_required()
    @blp.response(200)
    def get(self, anuncio_id):
        """Postulaciones del anuncio (gestión de contacto del negocio)."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño gestiona las postulaciones.")
        postulaciones = (
            AnuncioPostulacion.query.filter_by(anuncio_id=anuncio.id)
            .order_by(AnuncioPostulacion.created_at.asc())
            .all()
        )
        for p in postulaciones:
            p.pds_nombre = p.pds.nombre or f"Postulante #{p.pds_id}"
        return AnuncioPostulacionSchema(many=True).dump(postulaciones)


@blp.route("/<int:anuncio_id>/postulaciones/<int:postulacion_id>")
class AnuncioPostulacionItem(MethodView):
    @jwt_required()
    @blp.arguments(PostulacionEstadoSchema)
    @blp.response(200, AnuncioPostulacionSchema)
    def patch(self, data, anuncio_id, postulacion_id):
        """Gestión del negocio: contactar, descartar o seleccionar perfil."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño gestiona las postulaciones.")
        postulacion = db.get_or_404(AnuncioPostulacion, postulacion_id)
        if postulacion.anuncio_id != anuncio.id:
            abort(400, message="La postulación no pertenece a este anuncio.")
        accion = data["accion"]
        if accion == "seleccionar":
            if anuncio.estado != EstadoAnuncio.PUBLICADO:
                abort(400, message="Reabre el anuncio para cambiar la selección.")
            if postulacion.estado == EstadoPostulacionAnuncio.DESCARTADO:
                abort(400, message="No puedes seleccionar una postulación descartada.")
            AnuncioPostulacion.query.filter_by(
                anuncio_id=anuncio.id, seleccionado=True
            ).update({"seleccionado": False})
            postulacion.seleccionado = True
            crear_notificacion(
                postulacion.pds_id,
                "anuncio_seleccionado",
                f"El negocio seleccionó tu perfil para: {anuncio.titulo}.",
            )
        elif accion == "deseleccionar":
            postulacion.seleccionado = False
        elif accion == "contactar":
            postulacion.estado = EstadoPostulacionAnuncio.CONTACTADO
            crear_notificacion(
                postulacion.pds_id,
                "anuncio_contactado",
                f"El negocio {anuncio.titulo} te contactó por tu postulación.",
            )
            _emit_anuncio("anuncio:contactado", anuncio, postulacion.pds_id)
        else:
            postulacion.estado = EstadoPostulacionAnuncio.DESCARTADO
            postulacion.seleccionado = False

        db.session.commit()
        postulacion.pds_nombre = postulacion.pds.nombre or f"Postulante #{postulacion.pds_id}"
        return postulacion
