"""Solicitudes blueprint: crear/listar/detalle/estado/ratings (RF-03, RF-04)."""

import logging

from flask import request, current_app
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.extensions import db
from app.services.realtime import safe_emit
from app.services.verificacion import esta_verificado
from app.models.user import User, Profile, RolUsuario
from app.models.solicitud import Solicitud, Rating, EstadoSolicitud, UrgenciaSolicitud
from app.models.contract import Contract
from app.models.chamba import Chamba
from app.models.marana import Marana, EstadoMarana
from app.services.categorias import categoria_norm_expr
from app.services.descubrimiento import categorias_de_perfil
from app.ai.geo import haversine_km
from app.models.config import SystemConfig
from app.schemas.solicitud import (
    SolicitudCreateSchema,
    SolicitudEstadoSchema,
    SolicitudListSchema,
    SolicitudMapaSchema,
    SolicitudSchema,
)
from app.schemas.rating import RatingCreateSchema, RatingSchema

blp = Blueprint("solicitudes", __name__, description="Solicitudes y calificaciones")

logger = logging.getLogger(__name__)

# Ciudad base de operación (geofence de solicitudes). Configurable vía
# SystemConfig key="ciudad_base"; Valledupar es el valor por defecto del producto.
CIUDAD_BASE_DEFAULT = "Valledupar"

# Radio (km) del mapa del PDS: solo se envían puntos de su zona, no la
# ciudad completa (escala con el número de solicitudes).
RADIO_MAPA_KM = 20.0

# Categoría padre de cada oficio: una maraña de "construccion" es relevante
# para un plomero o carpintero aunque el slug exacto no coincida.
PADRE_CATEGORIA = {
    "plomeria": "construccion",
    "carpinteria": "construccion",
    "electricidad": "construccion",
    "albanileria": "construccion",
    "pintura": "construccion",
    "yeso": "construccion",
    "limpieza": "domesticos",
    "calentadores": "climatizacion",
    "aire_acondicionado": "climatizacion",
}


def _ciudad_base() -> str:
    """Devuelve la ciudad base configurada (o Valledupar por defecto)."""
    cfg = SystemConfig.query.filter_by(key="ciudad_base").first()
    if cfg and cfg.value:
        return cfg.value
    return CIUDAD_BASE_DEFAULT


def _recalcular_promedio(calificado_id: int) -> None:
    """Recalcula calificacion_promedio del perfil calificado."""
    ratings = Rating.query.filter_by(calificado_id=calificado_id).all()
    profile = db.session.get(Profile, calificado_id)
    if profile is None:
        return
    profile.calificacion_promedio = (
        sum(r.puntaje for r in ratings) / len(ratings) if ratings else 0.0
    )


# ── Tiempo real (Socket.IO) ──────────────────────────────────────────

def _emit_solicitud(event: str, solicitud: Solicitud, target_user_id: int) -> None:
    """Emite la solicitud actualizada (payload completo) a una sala de usuario."""
    safe_emit(
        event,
        SolicitudSchema().dump(solicitud),
        room=f"user:{target_user_id}",
    )


def _anotar_distancias(items: list[dict], solicitudes: list, user_id: int) -> None:
    """Añade `distancia_km` a cada item: distancia real del PDS a la solicitud.

    No se exponen las coordenadas (privacidad del solicitante); sólo el
    número de kilómetros, que es lo que el mapa necesita para filtrar.
    Las solicitudes sin geolocalización quedan con `distancia_km = None`.
    """
    perfil = db.session.get(Profile, user_id)
    if perfil is None or perfil.latitud is None or perfil.longitud is None:
        return

    from app.ai.geo import haversine_km

    lat_pds, lng_pds = perfil.latitud, perfil.longitud
    for item, sol in zip(items, solicitudes):
        if sol.latitud is None or sol.longitud is None:
            item["distancia_km"] = None
            continue
        item["distancia_km"] = round(
            haversine_km(lat_pds, lng_pds, sol.latitud, sol.longitud), 2
        )



@blp.route("/")
class SolicitudList(MethodView):
    @jwt_required()
    @blp.arguments(SolicitudCreateSchema, location="json")
    @blp.response(201, SolicitudSchema)
    def post(self, data):
        """RF-04: crea una solicitud (solicitante o comerciante = usuario JWT).

        Contrato (cambio 2026-09-17): el rol merchant también puede publicar
        chambas (pantalla merchant-solicitudes del diseño) para recibir ofertas
        de los PDS. El aislamiento se mantiene: cada solicitud queda ligada a
        su creador vía solicitante_id y solo el dueño la modifica/elimina.
        """
        user_id = int(get_jwt_identity())
        role = get_jwt().get("role")
        if role not in (RolUsuario.SOLICITANTE.value, RolUsuario.MERCHANT.value):
            abort(403, message="Solo el solicitante o el comerciante puede publicar solicitudes.")

        # Verificación de identidad: un solicitante o merchant sin KYC
        # aprobado no publica. El criterio se calcula contra los documentos
        # reales (Profile.verificado puede estar obsoleto en datos sembrados).
        config_key = {
            RolUsuario.SOLICITANTE.value: "REQUIRE_KYC_TO_PUBLISH",
            RolUsuario.MERCHANT.value: "REQUIRE_KYC_TO_MERCHANT",
        }.get(role)
        if config_key and current_app.config.get(config_key, True):
            usuario = db.session.get(User, user_id)
            if usuario is None:
                abort(404, message="Usuario no encontrado.")
            if not esta_verificado(usuario):
                abort(
                    403,
                    message=(
                        "Verifica tu identidad antes de publicar: necesitas "
                        "tener aprobados tus documentos KYC. Entra a "
                        "Verificación de identidad para completarlos."
                    ),
                )
            # Mantiene el flag al día sin un commit extra.
            perfil = db.session.get(Profile, user_id)
            if perfil is not None and not perfil.verificado:
                perfil.verificado = True

        for campo in ("titulo", "categoria", "descripcion", "ubicacion"):
            valor = data.get(campo)
            if not valor or not str(valor).strip():
                abort(400, message=f"El campo '{campo}' es requerido.")

        presupuesto = data.get("presupuesto")
        if presupuesto is not None and presupuesto < 50000:
            abort(400, message="El presupuesto mínimo es 50000.")

        solicitud = Solicitud(
            solicitante_id=user_id,
            titulo=data["titulo"],
            categoria=data["categoria"],
            descripcion=data["descripcion"],
            ubicacion=data["ubicacion"],
            presupuesto=presupuesto,  # None => "a convenir"
            fecha_deseada=data.get("fecha_deseada"),
            urgencia=data.get("urgencia"),
            especificaciones_tecnicas=data.get("especificaciones_tecnicas"),
            imagen_360=data.get("imagen_360"),
            horario=data.get("horario"),
            imagenes=data.get("imagenes"),
            latitud=data.get("latitud"),
            longitud=data.get("longitud"),
            direccion=data.get("direccion"),
            radio_km=data.get("radio_km", 5.0),
            estado=EstadoSolicitud.PUBLICADO,
        )
        solicitud.advertencia = None
        ciudad_base = _ciudad_base()
        if solicitud.ubicacion != ciudad_base:
            solicitud.advertencia = (
                f"La ubicación está fuera de {ciudad_base}; verifica "
                "disponibilidad del pds."
            )

        db.session.add(solicitud)
        # División regional: deriva la región del solicitante desde su ubicación.
        try:
            from app.services.region import assign_region
            owner = db.session.get(User, user_id)
            assign_region(owner, text=solicitud.ubicacion)
        except Exception:
            pass
        db.session.commit()
        _emit_solicitud("solicitud:creada", solicitud, user_id)

        # ── Aviso a los PDS elegibles (tiempo real) ──────────────────────
        # Sin esto, el PDS sólo se enteraba al recargar la página: el
        # evento `solicitud:creada` anterior sólo se emitía al dueño de la
        # solicitud. Se avisa a quienes realmente califican (perfil
        # completo + categoría coincidente + dentro del radio), no a todo
        # el mundo.
        try:
            from app.services.descubrimiento import notificar_pds_elegibles

            notificados = notificar_pds_elegibles(solicitud)
            db.session.commit()
            logger.info(
                "Solicitud %s: %s PDS elegibles notificados", solicitud.id, notificados
            )
        except Exception:  # noqa: BLE001 — el aviso nunca tumba el alta
            db.session.rollback()
            logger.exception(
                "No se pudo notificar a los PDS elegibles de la solicitud %s",
                solicitud.id,
            )

        # ── Cascada geoespacial (expansión de radio si nadie postula) ────
        try:
            from app.services.cascade import CascadeManager

            CascadeManager.start_cascade(solicitud_id=solicitud.id)
        except Exception:  # noqa: BLE001 — la cascada es best-effort
            logger.exception(
                "No se pudo iniciar la cascada de la solicitud %s", solicitud.id
            )

        return solicitud

    @jwt_required(optional=True)
    @blp.response(200)
    def get(self):
        """RF-04: lista solicitudes con filtros opcionales.

        Nunca se exponen las coordenadas exactas (latitud/longitud/direccion)
        en listados: se hace dump manual y se eliminan esos campos.

        Supports optional page/per_page query params for pagination (P2-4).
        If no params, returns all items (backward compatible).
        """
        query = Solicitud.query
        # Identidad del solicitante: se necesita para calcular la distancia
        # real al PDS (`distancia_km`), no sólo para el filtro de elegibles.
        uid = get_jwt_identity()
        # Solo lo publicado es visible en el listado público. `?estado=todos`
        # conserva el comportamiento histórico (útil para admin/debug).
        estado = request.args.get("estado", EstadoSolicitud.PUBLICADO.value)
        if estado and estado != "todos":
            try:
                query = query.filter(Solicitud.estado == EstadoSolicitud(estado))
            except ValueError:
                abort(400, message=f"Estado inválido: {estado}")
        # P2: elegibilidad del PDS. Con `?elegibles=1` solo se listan las
        # chambas cuya categoria coincide con las habilidades/categorias del
        # perfil del PDS autenticado (evita mostrar chambas no postulables).
        # Sin habilidades registradas no se filtra: el panel no queda vacio.
        elegibles = request.args.get("elegibles", "").lower() in (
            "1", "true", "yes", "si", "sí",
        )
        if elegibles:
            if uid is not None:
                prof = db.session.get(Profile, int(uid))
                if prof is not None:
                    from app.services.categorias import (
                        categoria_norm_expr,
                        normalizar_categoria,
                    )

                    allowed = {
                        normalizar_categoria(c)
                        for c in (
                            list(prof.categorias or [])
                            + list(prof.habilidades or [])
                        )
                        if c and normalizar_categoria(c)
                    }
                    if allowed:
                        query = query.filter(
                            categoria_norm_expr(Solicitud.categoria).in_(
                                sorted(allowed)
                            )
                        )
        categoria = request.args.get("categoria")
        ubicacion = request.args.get("ubicacion")
        q = request.args.get("q")
        if categoria:
            query = query.filter(Solicitud.categoria == categoria)
        if ubicacion:
            query = query.filter(Solicitud.ubicacion == ubicacion)
        if q:
            query = query.filter(Solicitud.descripcion.ilike(f"%{q}%"))
        query = query.order_by(Solicitud.creado_en.desc())

        from app.services.pagination import paginate_query
        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        model_items = result if isinstance(result, list) else result["items"]
        items = SolicitudListSchema(many=True).dump(model_items)

        # Conteo de ofertas en UNA query (las tarjetas ya no piden /ofertas).
        from sqlalchemy import func as _func
        from app.models.oferta import Oferta

        ids = [s.id for s in model_items]
        conteos = {}
        if ids:
            filas = (
                db.session.query(Oferta.solicitud_id, _func.count(Oferta.id))
                .filter(Oferta.solicitud_id.in_(ids))
                .group_by(Oferta.solicitud_id)
                .all()
            )
            conteos = {sid: n for sid, n in filas}
        for item in items:
            item["ofertas_count"] = conteos.get(item["id"], 0)

        # ── Distancia real al PDS autenticado ────────────────────────────
        # El mapa del Chambeador filtra por radio de búsqueda, pero el
        # listado no expone lat/lng (privacidad). `radio_km` es el radio que
        # PIDIÓ el cliente, no la distancia: usarlo como proxy descartaba
        # chambas que estaban a 1 km. Se calcula la distancia real aquí.
        if uid is not None:
            _anotar_distancias(items, model_items, int(uid))

        if isinstance(result, list):
            return items
        result["items"] = items
        return result


@blp.route("/mias")
class SolicitudMias(MethodView):
    """RF-04: solicitudes del usuario autenticado (dueño).

    El listado público `GET /solicitudes/` devuelve TODAS las publicadas;
    esta ruta es la que usa el panel del solicitante. Aquí sí se incluyen
    las coordenadas exactas porque el dueño es quien las registró.
    """

    @jwt_required()
    @blp.response(200)
    def get(self):
        user_id = int(get_jwt_identity())
        query = (
            Solicitud.query.filter(Solicitud.solicitante_id == user_id)
            .order_by(Solicitud.creado_en.desc())
        )

        from app.services.pagination import paginate_query
        page = request.args.get("page")
        per_page = request.args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        if isinstance(result, list):
            items = result
            payload = SolicitudSchema(many=True).dump(items)
        else:
            items = result["items"]
            payload = SolicitudSchema(many=True).dump(items)

        # Conteo de ofertas por solicitud en UNA sola query (evita el N+1
        # que haría el frontend al pedir las ofertas de cada tarjeta).
        from sqlalchemy import func as _func
        from app.models.oferta import Oferta

        ids = [s.id for s in items]
        conteos = {}
        if ids:
            filas = (
                db.session.query(Oferta.solicitud_id, _func.count(Oferta.id))
                .filter(Oferta.solicitud_id.in_(ids))
                .group_by(Oferta.solicitud_id)
                .all()
            )
            conteos = {sid: n for sid, n in filas}

        for item in payload:
            item["ofertas_count"] = conteos.get(item["id"], 0)

        if isinstance(result, list):
            return payload
        result["items"] = payload
        return result


@blp.route("/mapa")
class SolicitudMapa(MethodView):
    @jwt_required()
    @blp.response(200, SolicitudMapaSchema(many=True))
    def get(self):
        """Puntos anónimos de solicitudes y marañas relevantes al PDS.

        No expone id, título ni dirección: el cliente solo recibe lat/lng
        aproximadas (4 decimales), la categoría y el tipo (chamba/maraña).
        Filtra por las categorías del perfil y por `radio` (km, 10–100;
        default 20) para que el mapa no crezca con toda la ciudad.
        """
        user_id = int(get_jwt_identity())
        perfil = db.session.get(Profile, user_id)
        permitidas = categorias_de_perfil(perfil) if perfil else set()

        # Radio del mapa: lo manda el slider del cliente (10–100 km). Se
        # acota para que un valor absurdo no traiga toda la región.
        radio_arg = request.args.get("radio", type=float)
        radio_km = (
            RADIO_MAPA_KM
            if radio_arg is None
            else max(1.0, min(float(radio_arg), 100.0))
        )

        def _dentro(sol: Solicitud) -> bool:
            """Dentro del radio del PDS (si tiene coordenadas)."""
            if (
                perfil is None
                or perfil.latitud is None
                or perfil.longitud is None
            ):
                return True
            return (
                haversine_km(
                    perfil.latitud,
                    perfil.longitud,
                    sol.latitud,
                    sol.longitud,
                )
                <= radio_km
            )

        query = Solicitud.query.filter(
            Solicitud.estado == EstadoSolicitud.PUBLICADO,
            Solicitud.latitud.isnot(None),
            Solicitud.longitud.isnot(None),
        )
        if permitidas:
            query = query.filter(
                categoria_norm_expr(Solicitud.categoria).in_(sorted(permitidas))
            )
        filas = query.order_by(Solicitud.creado_en.desc()).limit(300).all()
        filas = [s for s in filas if _dentro(s)][:200]

        puntos = [
            {
                "lat": round(float(s.latitud), 4),
                "lng": round(float(s.longitud), 4),
                "categoria": s.categoria,
                "tipo": "chamba",
            }
            for s in filas
        ]

        # Marañas publicadas: solo las del perfil del PDS y su zona. Se
        # incluye la categoría padre del oficio (construccion, domesticos…).
        permitidas_marana = set(permitidas) | {
            PADRE_CATEGORIA[c]
            for c in permitidas
            if c in PADRE_CATEGORIA
        }
        mq = (
            db.session.query(Marana, Solicitud)
            .join(Chamba, Chamba.id == Marana.chamba_id)
            .join(Contract, Contract.id == Chamba.contract_id)
            .join(Solicitud, Solicitud.id == Contract.service_id)
            .filter(
                Marana.estado == EstadoMarana.PUBLICADO,
                Solicitud.latitud.isnot(None),
                Solicitud.longitud.isnot(None),
            )
        )
        if permitidas_marana:
            mq = mq.filter(
                categoria_norm_expr(Marana.categoria).in_(
                    sorted(permitidas_marana)
                )
            )
        filas_marana = mq.limit(200).all()
        filas_marana = [(m, s) for m, s in filas_marana if _dentro(s)][:100]

        puntos += [
            {
                "lat": round(float(s.latitud), 4),
                "lng": round(float(s.longitud), 4),
                "categoria": m.categoria,
                "tipo": "marana",
            }
            for m, s in filas_marana
        ]

        return puntos


@blp.route("/<int:solicitud_id>")
class SolicitudDetail(MethodView):
    @jwt_required(optional=True)
    @blp.response(200)
    def get(self, solicitud_id):
        """RF-04: detalle de solicitud + ratings.

        Gating de coordenadas: solo el dueño solicitante o el pds premiado
        (existe Contract con service_id==solicitud_id y proveedor_id==uid)
        reciben latitud/longitud/direccion. El resto las ve en None.
        """
        solicitud = db.get_or_404(Solicitud, solicitud_id)
        data = SolicitudSchema().dump(solicitud)
        uid = get_jwt_identity()
        autorizado = False
        if uid is not None:
            uid = int(uid)
            if solicitud.solicitante_id == uid:
                autorizado = True
            elif Contract.query.filter_by(
                service_id=solicitud_id, proveedor_id=uid
            ).first():
                autorizado = True
        if not autorizado:
            data["latitud"] = None
            data["longitud"] = None
            data["direccion"] = None
        return data


@blp.route("/<int:solicitud_id>/estado")
class SolicitudEstado(MethodView):
    @jwt_required()
    @blp.arguments(SolicitudEstadoSchema)
    @blp.response(200, SolicitudSchema)
    def patch(self, data, solicitud_id):
        """Cambia estado; solo el dueño (solicitante_id)."""
        user_id = int(get_jwt_identity())
        solicitud = db.get_or_404(Solicitud, solicitud_id)
        if solicitud.solicitante_id != user_id:
            abort(403, message="Solo el dueño puede cambiar el estado.")
        solicitud.estado = EstadoSolicitud(data["estado"])
        db.session.commit()
        _emit_solicitud("solicitud:actualizada", solicitud, user_id)
        return solicitud


@blp.route("/<int:solicitud_id>/ratings")
class SolicitudRatings(MethodView):
    @jwt_required()
    @blp.arguments(RatingCreateSchema)
    @blp.response(201, RatingSchema)
    def post(self, data, solicitud_id):
        """RF-03: crea Rating. Requiere solicitud completada y autor único."""
        user_id = int(get_jwt_identity())
        solicitud = db.get_or_404(Solicitud, solicitud_id)

        if solicitud.estado != EstadoSolicitud.COMPLETADO:
            abort(409, message="solicitud no completada")

        if Rating.query.filter_by(service_id=solicitud_id, autor_id=user_id).first():
            abort(409, message="Ya calificaste esta solicitud.")

        calificado_id = data["calificado_id"]
        if not db.session.get(User, calificado_id):
            abort(404, message="El usuario calificado no existe.")

        rating = Rating(
            service_id=solicitud_id,
            autor_id=user_id,
            calificado_id=calificado_id,
            puntaje=data["puntaje"],
            comentario=data.get("comentario"),
        )
        db.session.add(rating)
        db.session.flush()
        _recalcular_promedio(calificado_id)
        db.session.commit()
        return rating

    @blp.response(200, RatingSchema(many=True))
    def get(self, solicitud_id):
        """RF-03: lista ratings de la solicitud."""
        db.get_or_404(Solicitud, solicitud_id)
        return Rating.query.filter_by(service_id=solicitud_id).order_by(
            Rating.creado_en.desc()
        ).all()
