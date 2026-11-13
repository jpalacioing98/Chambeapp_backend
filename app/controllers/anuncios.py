"""Anuncios blueprint: ofertas laborales de negocios.

Dos modalidades:
  - "contacto" (por defecto): banner publicitario visible en el mapa de
    negocios para todos los roles. Permite postulaciones de PDS y gestión
    de contacto del negocio (contactar/descartar). Sin contratos.
  - "contrato": el negocio elige una postulación y se genera un Contract
    vinculante (con su solicitud y chamba) que ambas partes firman.
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
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato
from app.schemas.anuncio import (
    AnuncioCreateSchema,
    AnuncioEstadoSchema,
    AnuncioPostulacionCreateSchema,
    AnuncioPostulacionSchema,
    AnuncioSchema,
    PostulacionEstadoSchema,
    ContratarPostulacionSchema,
)
from app.schemas.contracts import ContractSchema
from app.controllers.notifications import crear_notificacion

blp = Blueprint("anuncios", __name__, description="Anuncios laborales de negocios")

ROL_NEGOCIO = RolUsuario.MERCHANT.value  # "merchant"
ROL_PDS = RolUsuario.PDS.value  # "pds"

# Presupuesto mínimo (COP) de un anuncio vinculante.
PRESUPUESTO_MINIMO_CONTRATO = 50000


def _emit_anuncio(event: str, anuncio: AnuncioLaboral, target_user_id: int) -> None:
    """Emite el anuncio COMPLETO a la sala del usuario destinatario."""
    payload = AnuncioSchema().dump(_anuncio_con_negocio(anuncio))
    payload["postulaciones_count"] = len(anuncio.postulaciones)
    safe_emit(event, payload, room=f"user:{target_user_id}")


def _anuncio_con_negocio(anuncio: AnuncioLaboral) -> AnuncioLaboral:
    anuncio.negocio_nombre = (
        anuncio.negocio.nombre or f"Negocio #{anuncio.negocio_id}"
    )
    if anuncio.modalidad == ModalidadAnuncio.CONTRATO:
        anuncio.vacantes_disponibles = _vacantes_disponibles(anuncio)
    else:
        anuncio.vacantes_disponibles = anuncio.vacantes or 0
    return anuncio


def _contratos_del_anuncio(anuncio: AnuncioLaboral) -> list[Contract]:
    """Contratos generados desde este anuncio (incluye los cancelados)."""
    ids = list(anuncio.contract_ids or [])
    if not ids:
        return []
    return (
        Contract.query.filter(Contract.id.in_(ids))
        .order_by(Contract.creado_en.desc())
        .all()
    )


def _vacantes_disponibles(anuncio: AnuncioLaboral) -> int:
    """Vacantes que todavía se pueden contratar.

    Los contratos cancelados liberan su vacante: el negocio puede volver
    a contratar a otro postulante.
    """
    total = anuncio.vacantes or 0
    ocupados = len(
        [
            c
            for c in _contratos_del_anuncio(anuncio)
            if c.estado != EstadoContrato.CANCELADO
        ]
    )
    return max(total - ocupados, 0)


def _crear_contrato_desde_anuncio(
    anuncio: AnuncioLaboral,
    postulacion: AnuncioPostulacion,
    data: dict,
) -> Contract:
    """Genera el contrato vinculante de una postulación de un anuncio.

    `Contract.service_id` apunta siempre a una Solicitud (de ahí cuelgan la
    chamba, los hitos y el cálculo de comisión). Por eso la contratación
    materializa la solicitud del trabajo anunciado y la deja ASIGNADA:
    nunca aparece como solicitud publicada en el feed.
    """
    monto = data.get("monto")
    if monto is None:
        monto = anuncio.presupuesto
    fecha_deseada = data.get("fecha_deseada") or anuncio.fecha_deseada
    horario = data.get("horario") or anuncio.horario

    condiciones = [
        {
            "texto": f"Contrato generado desde el anuncio #{anuncio.id}: {anuncio.titulo}",
            "autor": "negocio",
        }
    ]
    for texto in data.get("condiciones") or []:
        texto = (texto or "").strip()
        if texto:
            condiciones.append({"texto": texto, "autor": "negocio"})

    solicitud = Solicitud(
        solicitante_id=anuncio.negocio_id,
        titulo=anuncio.titulo,
        categoria=anuncio.categoria,
        descripcion=anuncio.descripcion,
        ubicacion=anuncio.ubicacion or "Valledupar",
        latitud=anuncio.latitud,
        longitud=anuncio.longitud,
        presupuesto=int(round(monto)) if monto is not None else None,
        fecha_deseada=fecha_deseada,
        horario=horario,
        estado=EstadoSolicitud.ASIGNADA,
    )
    db.session.add(solicitud)
    db.session.flush()

    contract = Contract(
        service_id=solicitud.id,
        proveedor_id=postulacion.pds_id,
        solicitante_id=anuncio.negocio_id,
        estado=EstadoContrato.PENDIENTE.value,
        monto=monto,
        condiciones=condiciones,
        fecha_deseada=fecha_deseada,
        horario=horario,
    )
    db.session.add(contract)
    db.session.flush()

    postulacion.estado = EstadoPostulacionAnuncio.CONTRATADO
    postulacion.contract_id = contract.id

    ids = list(anuncio.contract_ids or [])
    if contract.id not in ids:
        ids.append(contract.id)
    anuncio.contract_ids = ids

    return contract


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
        modalidad = (
            ModalidadAnuncio(data.get("modalidad") or ModalidadAnuncio.CONTACTO)
            if tipo == "empleo"
            else ModalidadAnuncio.CONTACTO
        )
        presupuesto = data.get("presupuesto")
        if tipo == "empleo" and modalidad == ModalidadAnuncio.CONTRATO:
            if presupuesto is None:
                abort(
                    400,
                    message="Un anuncio vinculante requiere el presupuesto del trabajo.",
                )
            if presupuesto < PRESUPUESTO_MINIMO_CONTRATO:
                abort(
                    400,
                    message=(
                        "El presupuesto de un anuncio vinculante debe ser de al menos "
                        f"{PRESUPUESTO_MINIMO_CONTRATO} COP."
                    ),
                )

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
            modalidad=modalidad,
            presupuesto=presupuesto,
            fecha_deseada=data.get("fecha_deseada") if tipo == "empleo" else None,
            horario=data.get("horario") if tipo == "empleo" else None,
            contract_ids=[],
            estado=EstadoAnuncio.PUBLICADO,
        )
        db.session.add(anuncio)
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
            anuncio.estado = EstadoAnuncio.CERRADO
        else:
            if anuncio.estado == EstadoAnuncio.PUBLICADO:
                abort(400, message="El anuncio ya está publicado.")
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
        if get_jwt().get("role") != ROL_PDS:
            abort(403, message="Solo un pds puede postularse a un anuncio laboral.")

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

        # Contacto por defecto desde los datos del PDS (telefono vive en User).
        user = User.query.get(user_id)
        postulacion = AnuncioPostulacion(
            anuncio_id=anuncio.id,
            pds_id=user_id,
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
            f"Un prestador se postuló a tu anuncio: {anuncio.titulo}.",
        )
        _emit_anuncio("anuncio:postulacion", anuncio, anuncio.negocio_id)
        postulacion.pds_nombre = postulacion.pds.nombre or f"Prestador #{user_id}"
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
            p.pds_nombre = p.pds.nombre or f"Prestador #{p.pds_id}"
        return AnuncioPostulacionSchema(many=True).dump(postulaciones)


@blp.route("/<int:anuncio_id>/postulaciones/<int:postulacion_id>")
class AnuncioPostulacionItem(MethodView):
    @jwt_required()
    @blp.arguments(PostulacionEstadoSchema)
    @blp.response(200, AnuncioPostulacionSchema)
    def patch(self, data, anuncio_id, postulacion_id):
        """Gestión de contacto: contactar / descartar (negocio dueño)."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño gestiona las postulaciones.")
        postulacion = db.get_or_404(AnuncioPostulacion, postulacion_id)
        if postulacion.anuncio_id != anuncio.id:
            abort(400, message="La postulación no pertenece a este anuncio.")
        if postulacion.estado == EstadoPostulacionAnuncio.CONTRATADO:
            abort(400, message="El postulante ya fue contratado.")

        accion = data["accion"]
        if accion == "contactar":
            postulacion.estado = EstadoPostulacionAnuncio.CONTACTADO
            crear_notificacion(
                postulacion.pds_id,
                "anuncio_contactado",
                f"El negocio {anuncio.titulo} te contactó por tu postulación.",
            )
            _emit_anuncio("anuncio:contactado", anuncio, postulacion.pds_id)
        else:
            postulacion.estado = EstadoPostulacionAnuncio.DESCARTADO

        db.session.commit()
        postulacion.pds_nombre = postulacion.pds.nombre or f"Prestador #{postulacion.pds_id}"
        return postulacion


@blp.route("/<int:anuncio_id>/postulaciones/<int:postulacion_id>/contratar")
class AnuncioPostulacionContratar(MethodView):
    @jwt_required()
    @blp.arguments(ContratarPostulacionSchema)
    @blp.response(201, ContractSchema)
    def post(self, data, anuncio_id, postulacion_id):
        """El negocio contrata a un postulante: genera el contrato vinculante."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño puede contratar postulantes.")

        from app.services.verificacion import exigir_verificado

        exigir_verificado(
            user_id, "REQUIRE_KYC_TO_MERCHANT", "contratar postulantes"
        )
        if anuncio.modalidad != ModalidadAnuncio.CONTRATO:
            abort(
                400,
                message="Este anuncio no es vinculante: no genera contratos.",
            )
        if anuncio.estado != EstadoAnuncio.PUBLICADO:
            abort(400, message="El anuncio ya no admite contrataciones.")

        postulacion = db.get_or_404(AnuncioPostulacion, postulacion_id)
        if postulacion.anuncio_id != anuncio.id:
            abort(400, message="La postulación no pertenece a este anuncio.")
        if postulacion.estado == EstadoPostulacionAnuncio.DESCARTADO:
            abort(400, message="La postulación fue descartada.")
        if postulacion.contract_id is not None:
            previo = db.session.get(Contract, postulacion.contract_id)
            if previo is not None and previo.estado != EstadoContrato.CANCELADO:
                abort(400, message="Este postulante ya fue contratado.")
            # El contrato anterior fue cancelado: el vacante queda libre y el
            # postulante puede volver a ser contratado.
            postulacion.contract_id = None
            postulacion.estado = EstadoPostulacionAnuncio.PENDIENTE

        if _vacantes_disponibles(anuncio) <= 0:
            abort(400, message="No hay vacantes disponibles en este anuncio.")

        contract = _crear_contrato_desde_anuncio(anuncio, postulacion, data)

        # Al agotar los vacantes el anuncio se cierra solo.
        if _vacantes_disponibles(anuncio) <= 0:
            anuncio.estado = EstadoAnuncio.CERRADO

        crear_notificacion(
            postulacion.pds_id,
            "anuncio_contratado",
            f"Te contrataron para el anuncio: {anuncio.titulo}. Firma el contrato para activarlo.",
        )
        crear_notificacion(
            anuncio.negocio_id,
            "anuncio_contratado",
            f"Contrato creado con el postulante de {anuncio.titulo}. Fírmalo para activarlo.",
        )
        db.session.commit()

        _emit_anuncio("anuncio:actualizado", anuncio, anuncio.negocio_id)
        _emit_anuncio("anuncio:contratado", anuncio, postulacion.pds_id)
        safe_emit(
            "contrato:creado",
            ContractSchema().dump(contract),
            room=f"user:{postulacion.pds_id}",
        )
        safe_emit(
            "contrato:creado",
            ContractSchema().dump(contract),
            room=f"user:{anuncio.negocio_id}",
        )
        return contract


@blp.route("/<int:anuncio_id>/contratos")
class AnuncioContratos(MethodView):
    @jwt_required()
    @blp.response(200, ContractSchema(many=True))
    def get(self, anuncio_id):
        """Contratos generados por este anuncio (negocio dueño)."""
        user_id = int(get_jwt_identity())
        anuncio = db.get_or_404(AnuncioLaboral, anuncio_id)
        if anuncio.negocio_id != user_id:
            abort(403, message="Solo el negocio dueño consulta los contratos.")
        return _contratos_del_anuncio(anuncio)