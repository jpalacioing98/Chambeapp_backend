"""Chambas blueprint: Módulo de Gestión de Chamba (ciclo de vida de ejecución).

Hitos (modulo chambas.md): contrato firmado → inicio de obra (geo) →
ejecución/adendas/novedades → solicitud de cierre → liquidación (pago
directo) → finalización (calificación).
"""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.chamba import Chamba, EstadoChamba
from app.models.contract import Contract
from app.controllers.notifications import crear_notificacion
from app.schemas.chambas import (
    AdendaSchema,
    AdendaUpdateSchema,
    CalificacionSchema,
    ChambaCreateSchema,
    ChambaEstadoSchema,
    ChambaSchema,
    EvidenciaSchema,
    EvidenciaUploadResponseSchema,
    EvidenciaUploadSchema,
    NovedadSchema,
    PagoSchema,
    ValidacionSchema,
)
from app.schemas.marana import MaranaCreateSchema, MaranaSchema
from app.services.chamba import (
    RADIO_VALIDACION_KM,
    agregar_adenda,
    agregar_novedad,
    confirmar_pago,
    emitir_actualizacion,
    finalizar_chamba,
    registrar_evidencia,
    validar_transicion,
    verificar_geoposicion,
)
from app.services.pagination import paginate_query

blp = Blueprint("chambas", __name__, description="Gestión de Chamba (ciclo de vida de ejecución)")


def _participante(chamba: Chamba, user_id: int) -> bool:
    return user_id in (chamba.contract.solicitante_id, chamba.contract.proveedor_id)


def _contraparte(chamba: Chamba, user_id: int) -> int:
    if user_id == chamba.contract.solicitante_id:
        return chamba.contract.proveedor_id
    return chamba.contract.solicitante_id


def _notificar(chamba: Chamba, user_id: int, tipo: str, mensaje: str) -> None:
    crear_notificacion(_contraparte(chamba, user_id), tipo, mensaje)


@blp.route("/<int:chamba_id>/marana")
class ChambaMarana(MethodView):
    @jwt_required()
    @blp.arguments(MaranaCreateSchema)
    @blp.response(201, MaranaSchema)
    def post(self, data, chamba_id):
        """Lanza una maraña (rebusque) desde una adenda de la chamba.

        El solicitante deriva el trabajo extra de otro perfil a otros PDS.
        El monto_extra de la adenda SE MUEVE a la maraña.
        """
        from app.models.marana import Marana, EstadoMarana

        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.solicitante_id:
            abort(403, message="Solo el solicitante de la chamba puede lanzar marañas.")
        if chamba.estado == EstadoChamba.FINALIZADA:
            abort(400, message="La chamba finalizada no admite nuevas marañas.")

        idx = data["adenda_idx"]
        # Copia profunda: JSON simple no rastrea mutaciones in-place.
        adendas = [dict(a) for a in (chamba.adendas or [])]
        if idx < 0 or idx >= len(adendas):
            abort(400, message="La adenda indicada no existe.")
        adenda = adendas[idx]
        if adenda.get("derivada"):
            abort(400, message="Esta adenda ya fue lanzada como maraña.")

        presupuesto = data.get("presupuesto")
        if presupuesto is None:
            presupuesto = adenda.get("monto_extra")

        marana = Marana(
            chamba_id=chamba.id,
            adenda_idx=idx,
            solicitante_id=user_id,
            titulo=data["titulo"],
            categoria=data["categoria"],
            descripcion=data["descripcion"],
            presupuesto=presupuesto,
            ubicacion=(
                chamba.contract.service.ubicacion
                if chamba.contract.service
                else None
            ),
            fecha_deseada=data.get("fecha_deseada"),
            horario=data.get("horario"),
            estado=EstadoMarana.PUBLICADO,
        )
        db.session.add(marana)
        db.session.flush()  # obtiene marana.id para la referencia en la adenda

        # La adenda queda derivada y su monto sale de la liquidación de la chamba.
        # (Lista nueva → SQLAlchemy detecta el cambio en la columna JSON.)
        adendas[idx] = {
            **adenda,
            "derivada": True,
            "marana_id": marana.id,
            "monto_extra": None,
            "tiempo_extra": None,
        }
        chamba.adendas = adendas

        db.session.commit()
        return marana


@blp.route("/")
class ChambaList(MethodView):
    @jwt_required()
    @blp.arguments(ChambaCreateSchema)
    @blp.response(201, ChambaSchema)
    def post(self, data):
        """Hito 1: crea la chamba a partir de un contrato firmado."""
        user_id = int(get_jwt_identity())
        contract = db.session.get(Contract, data["contract_id"])
        if contract is None:
            abort(404, message="El contrato no existe.")
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")
        if Chamba.query.filter_by(contract_id=contract.id).first() is not None:
            abort(400, message="El contrato ya tiene una chamba asociada.")

        chamba = Chamba(
            contract_id=contract.id,
            estado=EstadoChamba.PROGRAMADA,
            fecha_activacion=datetime.now(timezone.utc),
            evidencia_entrada=[],
            evidencia_salida=[],
            adendas=[],
            novedades=[],
            habilidades_validadas=[],
        )
        db.session.add(chamba)
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>")
class ChambaDetail(MethodView):
    @jwt_required()
    @blp.response(200, ChambaSchema)
    def get(self, chamba_id):
        """Detalle del expediente de la chamba (solo participantes)."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if not _participante(chamba, user_id):
            abort(403, message="No participas en esta chamba.")
        return chamba


@blp.route("/<int:chamba_id>/estado")
class ChambaEstado(MethodView):
    @jwt_required()
    @blp.arguments(ChambaEstadoSchema)
    @blp.response(200, ChambaSchema)
    def patch(self, data, chamba_id):
        """Transición de estado de la chamba (hitos 2-5)."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if not _participante(chamba, user_id):
            abort(403, message="No participas en esta chamba.")

        nuevo = EstadoChamba(data["estado"])
        if not validar_transicion(chamba.estado, nuevo):
            abort(
                400,
                message=f"No se puede pasar de '{chamba.estado.value}' a '{nuevo.value}'.",
            )

        # Reanudación de chamba pausada: vuelve al estado previo sin
        # re-validar GPS ni hitos ya cumplidos.
        if chamba.estado == EstadoChamba.PAUSADA and nuevo in (
            EstadoChamba.EN_PROCESO,
            EstadoChamba.EN_EJECUCION,
        ):
            _notificar(
                chamba,
                user_id,
                "chamba_reanudada",
                "La chamba fue reanudada.",
            )
            chamba.estado = nuevo
            chamba.estado_previo = None
            db.session.commit()
            emitir_actualizacion(chamba)
            return chamba

        # Hito 2: inicio de obra — solo el prestador, con validación de GPS.
        if nuevo == EstadoChamba.EN_PROCESO:
            if user_id != chamba.contract.proveedor_id:
                abort(403, message="Solo el prestador puede iniciar la obra.")
            lat = data.get("latitud")
            lng = data.get("longitud")
            if lat is None or lng is None:
                abort(400, message="Se requieren las coordenadas GPS del prestador.")
            solicitud = chamba.contract.service
            if solicitud is None or solicitud.latitud is None or solicitud.longitud is None:
                abort(400, message="La solicitud no tiene ubicación registrada.")
            if not verificar_geoposicion(lat, lng, solicitud.latitud, solicitud.longitud):
                abort(
                    400,
                    message=(
                        f"Ubicación fuera del radio permitido "
                        f"({RADIO_VALIDACION_KM * 1000} m del sitio de trabajo)."
                    ),
                )
            chamba.fecha_inicio_obra = datetime.now(timezone.utc)

        # Hito 4: solicitud de cierre — solo el prestador y REQUIERE al menos
        # una evidencia final (foto/360° de la obra entregada).
        elif nuevo == EstadoChamba.PENDIENTE_VALIDACION:
            if user_id != chamba.contract.proveedor_id:
                abort(403, message="Solo el prestador puede solicitar el cierre.")
            if not (chamba.evidencia_salida or []):
                abort(
                    400,
                    message=(
                        "Registra al menos una evidencia final "
                        "(foto/360° de la obra entregada) antes de solicitar el cierre."
                    ),
                )
            chamba.fecha_solicitud_cierre = datetime.now(timezone.utc)
            _notificar(
                chamba,
                user_id,
                "chamba_cierre_solicitado",
                "El prestador finalizó el trabajo y solicita la validación del cliente.",
            )

        # Hito 5: liquidación — solo el solicitante, requiere pago confirmado por ambas partes.
        elif nuevo == EstadoChamba.LIQUIDACION_CONFIRMADA:
            if user_id != chamba.contract.solicitante_id:
                abort(403, message="Solo el solicitante puede confirmar la liquidación.")
            if not chamba.pago_directo_confirmado:
                abort(
                    400,
                    message="Ambas partes deben confirmar el pago directo antes de liquidar.",
                )
            chamba.fecha_liquidacion = datetime.now(timezone.utc)

        # Pánico / incidencia: cualquiera de las partes puede pausar.
        elif nuevo == EstadoChamba.PAUSADA:
            chamba.estado_previo = chamba.estado
            _notificar(
                chamba,
                user_id,
                "chamba_pausada",
                "Una de las partes pausó la chamba por una incidencia.",
            )

        chamba.estado = nuevo
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/validacion")
class ChambaValidacion(MethodView):
    @jwt_required()
    @blp.arguments(ValidacionSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 4 (revisión y validación): el solicitante marca las
        habilidades DEMOSTRADAS del prestador al inspeccionar la entrega.

        La liquidación queda solo para la notificación/check-in del pago.
        """
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.solicitante_id:
            abort(403, message="Solo el solicitante valida las habilidades.")
        if chamba.estado != EstadoChamba.PENDIENTE_VALIDACION:
            abort(
                400,
                message="La revisión y validación ocurre tras la entrega del trabajo.",
            )
        chamba.habilidades_validadas = list(data.get("habilidades") or [])
        chamba.fecha_validacion = datetime.now(timezone.utc)
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/evidencia-entrada")
class ChambaEvidenciaEntrada(MethodView):
    @jwt_required()
    @blp.arguments(EvidenciaSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 2: registro de evidencia fotográfica inicial del área de trabajo."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.proveedor_id:
            abort(403, message="Solo el prestador registra la evidencia de entrada.")
        if chamba.estado not in (EstadoChamba.EN_PROCESO, EstadoChamba.EN_EJECUCION):
            abort(400, message="La evidencia de entrada solo aplica durante la ejecución.")
        registrar_evidencia(chamba, "entrada", data["urls"])
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/evidencia-salida")
class ChambaEvidenciaSalida(MethodView):
    @jwt_required()
    @blp.arguments(EvidenciaSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 4: evidencia final de la obra terminada."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.proveedor_id:
            abort(403, message="Solo el prestador registra la evidencia de salida.")
        if chamba.estado not in (EstadoChamba.EN_EJECUCION, EstadoChamba.PENDIENTE_VALIDACION):
            abort(400, message="La evidencia de salida solo aplica al cierre del trabajo.")
        registrar_evidencia(chamba, "salida", data["urls"])
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/adenda")
class ChambaAdenda(MethodView):
    @jwt_required()
    @blp.arguments(AdendaSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 3: adenda al contrato negociada durante la ejecución."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if not _participante(chamba, user_id):
            abort(403, message="No participas en esta chamba.")
        if chamba.estado in (EstadoChamba.FINALIZADA,):
            abort(400, message="La chamba finalizada no admite adendas.")
        # Si el PRESTADOR propone trabajo de otro perfil, queda como
        # SUGERENCIA: la decisión de lanzar la maraña es del solicitante.
        es_pds = user_id == chamba.contract.proveedor_id
        cubierta_por = data.get("cubierta_por", "pds_actual")
        sugerida = es_pds and cubierta_por == "otro_pds"
        agregar_adenda(
            chamba,
            data["descripcion"],
            monto_extra=data.get("monto_extra"),
            tiempo_extra=data.get("tiempo_extra"),
            tiempo_extra_unidad=data.get("tiempo_extra_unidad", "minutos"),
            cubierta_por=cubierta_por,
            categoria_requerida=data.get("categoria_requerida"),
            sugerida_por_pds=sugerida,
        )
        _notificar(
            chamba,
            user_id,
            "chamba_adenda",
            "Se registró una adenda al contrato de la chamba.",
        )
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/adenda/<int:adenda_idx>")
class ChambaAdendaItem(MethodView):
    @jwt_required()
    @blp.arguments(AdendaUpdateSchema)
    @blp.response(200, ChambaSchema)
    def patch(self, data, chamba_id, adenda_idx):
        """Edita cobertura/perfil de una adenda NO derivada (solicitante)."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.solicitante_id:
            abort(403, message="Solo el solicitante puede editar la adenda.")
        adendas = [dict(a) for a in (chamba.adendas or [])]
        if adenda_idx < 0 or adenda_idx >= len(adendas):
            abort(404, message="La adenda indicada no existe.")
        if adendas[adenda_idx].get("derivada"):
            abort(400, message="Una adenda derivada a maraña no se puede editar.")
        # Merge parcial conservando el resto de campos.
        adendas[adenda_idx] = {**adendas[adenda_idx], **{k: v for k, v in data.items() if v is not None}}
        chamba.adendas = adendas
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba

    @jwt_required()
    @blp.response(200, ChambaSchema)
    def delete(self, chamba_id, adenda_idx):
        """Elimina una adenda NO derivada (solo solicitante)."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.solicitante_id:
            abort(403, message="Solo el solicitante puede eliminar la adenda.")
        adendas = [dict(a) for a in (chamba.adendas or [])]
        if adenda_idx < 0 or adenda_idx >= len(adendas):
            abort(404, message="La adenda indicada no existe.")
        if adendas[adenda_idx].get("derivada"):
            abort(400, message="Una adenda derivada a maraña no se puede eliminar.")
        del adendas[adenda_idx]
        chamba.adendas = adendas
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/novedad")
class ChambaNovedad(MethodView):
    @jwt_required()
    @blp.arguments(NovedadSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 3: registro de novedades / botón de pánico."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if not _participante(chamba, user_id):
            abort(403, message="No participas en esta chamba.")
        if chamba.estado in (EstadoChamba.FINALIZADA,):
            abort(400, message="La chamba finalizada no admite novedades.")
        agregar_novedad(chamba, data["tipo"], data["descripcion"])
        _notificar(
            chamba,
            user_id,
            "chamba_novedad",
            f"Se registró una novedad ({data['tipo']}) en la chamba.",
        )
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/pago")
class ChambaPago(MethodView):
    @jwt_required()
    @blp.arguments(PagoSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 5: check-in de pago directo (cada parte confirma por separado).

        Válido en la validación (pendiente) y en la liquidación, donde
        además se puede actualizar el monto final.
        """
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if not _participante(chamba, user_id):
            abort(403, message="No participas en esta chamba.")
        if chamba.estado not in (
            EstadoChamba.PENDIENTE_VALIDACION,
            EstadoChamba.LIQUIDACION_CONFIRMADA,
        ):
            abort(400, message="El pago directo solo se confirma tras la entrega del trabajo.")
        confirmar_pago(chamba, user_id, monto_final=data.get("monto_final"))
        _notificar(
            chamba,
            user_id,
            "chamba_pago_confirmado",
            "Una de las partes confirmó el pago directo de la chamba.",
        )
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/<int:chamba_id>/calificacion")
class ChambaCalificacion(MethodView):
    @jwt_required()
    @blp.arguments(CalificacionSchema)
    @blp.response(200, ChambaSchema)
    def post(self, data, chamba_id):
        """Hito 6: calificación final, reseña y habilidades validadas en sitio."""
        user_id = int(get_jwt_identity())
        chamba = db.get_or_404(Chamba, chamba_id)
        if user_id != chamba.contract.solicitante_id:
            abort(403, message="Solo el solicitante califica la chamba.")
        if chamba.estado != EstadoChamba.LIQUIDACION_CONFIRMADA:
            abort(400, message="Solo se califica una chamba liquidada.")
        finalizar_chamba(
            chamba,
            data["estrellas"],
            comentario=data.get("comentario"),
            habilidades=data.get("habilidades"),
        )
        _notificar(
            chamba,
            user_id,
            "chamba_finalizada",
            "La chamba fue finalizada y calificada.",
        )
        db.session.commit()
        emitir_actualizacion(chamba)
        return chamba


@blp.route("/evidencia/upload")
class ChambaEvidenciaUpload(MethodView):
    @jwt_required()
    @blp.arguments(EvidenciaUploadSchema)
    @blp.response(200, EvidenciaUploadResponseSchema)
    def post(self, data):
        """Sube una evidencia (foto/360) a MinIO y devuelve la URL.

        El cliente adjunta la URL devuelta en evidencia-entrada/salida.
        """
        import base64
        import binascii

        b64 = data.get("archivo_base64", "")
        try:
            file_bytes = base64.b64decode(b64)
        except (binascii.Error, ValueError):
            abort(400, message="Imagen base64 inválida.")

        if not file_bytes:
            abort(400, message="La imagen está vacía.")

        filename = (data.get("nombre_archivo") or "evidencia.jpg").replace("/", "_")
        from app.services.storage import storage as storage_svc
        if storage_svc is None:
            abort(502, message="Servicio de almacenamiento no disponible.")
        try:
            url = storage_svc.upload_avatar(
                file_bytes, f"chamba-{int(get_jwt_identity())}", filename
            )
        except ValueError as e:
            abort(400, message=str(e))
        except Exception:
            abort(502, message="No se pudo subir la evidencia.")

        return {"url": url}


@blp.route("/solicitante/<int:uid>")
class ChambasSolicitante(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, uid):
        """Lista las chambas donde el usuario es solicitante (filtro por estado)."""
        user_id = int(get_jwt_identity())
        if user_id != uid:
            abort(403, message="Solo puedes ver tus propias chambas.")
        query = (
            Chamba.query.join(Contract)
            .filter(Contract.solicitante_id == uid)
            .order_by(Chamba.creado_en.desc())
        )
        estado = request.args.get("estado")
        if estado:
            if estado not in EstadoChamba.values():
                abort(400, message="Estado inválido.")
            query = query.filter(Chamba.estado == EstadoChamba(estado))
        return _paginar(query)


@blp.route("/prestador/<int:uid>")
class ChambasPrestador(MethodView):
    @jwt_required()
    @blp.response(200)
    def get(self, uid):
        """Lista las chambas donde el usuario es prestador (filtro por estado)."""
        user_id = int(get_jwt_identity())
        if user_id != uid:
            abort(403, message="Solo puedes ver tus propias chambas.")
        query = (
            Chamba.query.join(Contract)
            .filter(Contract.proveedor_id == uid)
            .order_by(Chamba.creado_en.desc())
        )
        estado = request.args.get("estado")
        if estado:
            if estado not in EstadoChamba.values():
                abort(400, message="Estado inválido.")
            query = query.filter(Chamba.estado == EstadoChamba(estado))
        return _paginar(query)


def _paginar(query):
    """Serializa con paginación opcional (mismo patrón que contracts)."""
    page = request.args.get("page")
    per_page = request.args.get("per_page")
    result = paginate_query(query, page=page, per_page=per_page)
    if isinstance(result, list):
        return ChambaSchema(many=True).dump(result)
    result["items"] = ChambaSchema(many=True).dump(result["items"])
    return result