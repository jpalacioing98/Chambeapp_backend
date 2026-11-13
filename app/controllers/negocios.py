"""Blueprint Negocios: CRUD, mapa, búsqueda, horarios, ratings, reportes, stats, imagenes upload."""

from datetime import datetime, timezone

from marshmallow import Schema, fields

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import text

from app.extensions import db
from app.ai.geo import haversine_km, is_postgis
from app.models.user import User, RolUsuario
from app.models.negocio import (
    Negocio, NegocioHorario, NegocioRating, NegocioReporte, NegocioRuta,
    TipoNegocio, EstadoNegocio, ModalidadNegocio, EstadoReporte, TipoReporte,
)
from app.schemas.negocios import (
    NegocioCreateSchema,
    NegocioUpdateSchema,
    NegocioResponseSchema,
    NegocioRutaCreateSchema,
    NegocioRutaUpdateSchema,
    NegocioRutaResponseSchema,
    HorarioSchema,
    NegocioReporteSchema,
    NegocioReporteResponseSchema,
    NegocioRatingCreateSchema,
    NegocioRatingResponseSchema,
    NegocioMapResponseSchema,
)
from app.services.negocio_utils import calcular_estado_horario, generar_slug
from app.services.realtime import safe_emit
from app.data.categorias_negocio import CATEGORIAS_NEGOCIO

blp = Blueprint("negocios", __name__, description="Directorio de negocios y comerciantes")


# ── Helpers ────────────────────────────────────────────────────────────

def _get_negocio_or_404(negocio_id: int) -> Negocio:
    negocio = db.session.get(Negocio, negocio_id)
    if not negocio:
        abort(404, message="Negocio no encontrado.")
    return negocio


def _get_negocio_by_slug_or_404(slug: str) -> Negocio:
    negocio = Negocio.query.filter_by(slug=slug).first()
    if not negocio:
        abort(404, message="Negocio no encontrado.")
    return negocio


def _ensure_owner(negocio: Negocio, user_id: int):
    """Verifica que el usuario sea owner del negocio o admin."""
    user = db.session.get(User, user_id)
    if not user:
        abort(401, message="Usuario no autenticado.")
    if negocio.owner_id != user_id and user.rol not in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN):
        abort(403, message="No tienes permiso para modificar este negocio.")


def _ensure_merchant(user_id: int) -> User:
    """Verifica que el usuario tenga rol merchant."""
    user = db.session.get(User, user_id)
    if not user or user.rol != RolUsuario.MERCHANT:
        abort(403, message="Solo los merchants pueden crear negocios.")
    return user


# ── Tiempo real (Socket.IO) ──────────────────────────────────────────

def _pin_negocio(negocio: Negocio) -> dict:
    """Pin mínimo del negocio para refrescar el mapa en vivo."""
    return {
        "id": negocio.id,
        "owner_id": negocio.owner_id,
        "nombre": negocio.nombre,
        "slug": negocio.slug,
        "lat": negocio.latitud,
        "lng": negocio.longitud,
        "categoria": negocio.categoria_principal,
        "calificacion": negocio.calificacion_promedio,
        "verificado": negocio.verificado,
        "abierto": calcular_estado_horario(negocio.horarios).get("esta_abierto", False),
        "logo_url": negocio.logo_url,
        "modalidad": negocio.modalidad,
    }


def _ruta_map_payload(ruta: NegocioRuta, negocio: Negocio | None = None) -> dict:
    """Ruta mínima para pintar la estela en el mapa público."""
    return {
        "id": ruta.id,
        "negocio_id": ruta.negocio_id,
        "negocio_nombre": (
            negocio.nombre if negocio is not None else ruta.negocio.nombre
        ),
        "nombre": ruta.nombre,
        "puntos": ruta.puntos or [],
        "calles": ruta.calles or [],
        "color": ruta.color,
        "progreso": ruta.progreso or 0.0,
    }


def _emit_ruta(event: str, negocio: Negocio, ruta: NegocioRuta | None,
               *, eliminar: bool = False) -> None:
    """Notifica rutas: al owner y a la sala del mapa (estela en vivo)."""
    payload = {
        "negocio_id": negocio.id,
        "ruta_id": ruta.id if ruta is not None else None,
        "eliminada": eliminar,
        "ruta": _ruta_map_payload(ruta, negocio) if ruta is not None else None,
        "en_curso": bool(ruta.en_curso) if ruta is not None else False,
    }
    safe_emit(event, payload, room=f"user:{negocio.owner_id}")
    safe_emit(event, payload, room="mapa")


def _emit_negocio(event: str, negocio: Negocio, *, eliminar: bool = False) -> None:
    """Emite el negocio actualizado al owner y el pin a la sala del mapa.

    - `user:<owner_id>` recibe el payload completo del negocio (dashboards).
    - Sala `mapa` recibe solo el pin mínimo (sin datos privados) para que
      los mapas abiertos se actualicen sin recargar. El cliente entra a la
      sala con `join_feed {room: "mapa"}` mientras el mapa está montado;
      antes se hacía broadcast a TODOS los conectados.
    """
    if eliminar:
        payload = {"id": negocio.id}
        safe_emit("negocio:eliminado", payload, room=f"user:{negocio.owner_id}")
        safe_emit("negocio:pin:eliminado", payload, room="mapa")
        return

    safe_emit(
        event,
        NegocioResponseSchema().dump(negocio),
        room=f"user:{negocio.owner_id}",
    )
    safe_emit("negocio:pin", _pin_negocio(negocio), room="mapa")



# ── CRUD de Negocios ──────────────────────────────────────────────────

@blp.route("/")
class NegociosList(MethodView):
    @blp.doc()
    @blp.arguments(NegocioCreateSchema)
    @blp.response(201, NegocioResponseSchema)
    @jwt_required()
    def post(self, data):
        """Crear un nuevo negocio (solo merchant)."""
        user_id = int(get_jwt_identity())
        _ensure_merchant(user_id)

        from app.services.verificacion import exigir_verificado

        exigir_verificado(
            user_id, "REQUIRE_KYC_TO_MERCHANT", "crear tu negocio"
        )

        slug = generar_slug(data["nombre"])

        # Evitar slug duplicado
        existente = Negocio.query.filter_by(slug=slug).first()
        if existente:
            import time
            slug = f"{slug}-{int(time.time())}"

        negocio = Negocio(
            owner_id=user_id,
            slug=slug,
            **{k: v for k, v in data.items()},
        )

        # Generar geometría PostGIS
        if negocio.latitud and negocio.longitud:
            negocio.geom = text(
                f"ST_SetSRID(ST_MakePoint({negocio.longitud}, {negocio.latitud}), 4326)"
            )

        db.session.add(negocio)
        db.session.flush()

        # Crear horarios por defecto (lun-dom, cerrados)
        for dia in range(7):
            h = NegocioHorario(
                negocio_id=negocio.id,
                dia_semana=dia,
                abierto=False,
                hora_apertura=None,
                hora_cierre=None,
            )
            db.session.add(h)

        db.session.commit()
        _emit_negocio("negocio:creado", negocio)
        return negocio

    @blp.doc()
    @blp.response(200, NegocioResponseSchema(many=True))
    def get(self):
        """Listar negocios activos con filtros opcionales."""
        query = Negocio.query.filter(Negocio.estado == EstadoNegocio.ACTIVO.value)

        # Filtros
        categoria = request.args.get("categoria")
        if categoria:
            query = query.filter(Negocio.categoria_principal == categoria)

        verificado = request.args.get("verificado")
        if verificado == "true":
            query = query.filter(Negocio.verificado == True)

        calificacion_min = request.args.get("calificacion_min", type=float)
        if calificacion_min:
            query = query.filter(Negocio.calificacion_promedio >= calificacion_min)

        # Búsqueda fuzzy por texto
        q = request.args.get("q")
        if q:
            query = query.filter(
                db.or_(
                    Negocio.nombre.ilike(f"%{q}%"),
                    Negocio.descripcion.ilike(f"%{q}%"),
                    Negocio.categoria_principal.ilike(f"%{q}%"),
                )
            )

        # Paginación
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        pagination = query.order_by(Negocio.calificacion_promedio.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination.items


@blp.route("/<int:negocio_id>")
class NegocioDetail(MethodView):
    @blp.doc()
    @blp.response(200, NegocioResponseSchema)
    def get(self, negocio_id):
        """Obtener detalle de un negocio por ID."""
        return _get_negocio_or_404(negocio_id)

    @blp.doc()
    @blp.arguments(NegocioUpdateSchema)
    @blp.response(200, NegocioResponseSchema)
    @jwt_required()
    def put(self, data, negocio_id):
        """Actualizar un negocio (solo owner)."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        for key, value in data.items():
            # Se aplica también `None` para poder vaciar campos (WhatsApp,
            # Instagram, descripción…) al guardar la configuración.
            setattr(negocio, key, value)

        # Al volver a estático se detiene cualquier ruta en curso.
        if data.get("modalidad") == ModalidadNegocio.ESTATICO.value:
            for ruta in negocio.rutas:
                ruta.en_curso = False
                ruta.progreso = 0.0

        # Regenerar geom si cambiaron coordenadas
        if "latitud" in data or "longitud" in data:
            if negocio.latitud is not None and negocio.longitud is not None:
                negocio.geom = text(
                    f"ST_SetSRID(ST_MakePoint({negocio.longitud}, {negocio.latitud}), 4326)"
                )

        negocio.actualizado_en = datetime.now(timezone.utc)
        db.session.commit()
        _emit_negocio("negocio:actualizado", negocio)
        return negocio

    @blp.doc()
    @blp.response(204)
    @jwt_required()
    def delete(self, negocio_id):
        """Eliminar un negocio (solo owner)."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        _emit_negocio("negocio:eliminado", negocio, eliminar=True)
        db.session.delete(negocio)
        db.session.commit()
        return "", 204


# ── Endpoint por slug ─────────────────────────────────────────────────

@blp.route("/slug/<string:slug>")
class NegocioBySlug(MethodView):
    @blp.doc()
    @blp.response(200, NegocioResponseSchema)
    def get(self, slug):
        """Obtener detalle de un negocio por slug."""
        return _get_negocio_by_slug_or_404(slug)


# ── Mapa ──────────────────────────────────────────────────────────────

@blp.route("/mapa")
class NegociosMapa(MethodView):
    @blp.doc()
    @blp.response(200, NegocioMapResponseSchema)
    def get(self):
        """Negocios para mapa: pins y clusters."""
        lat = request.args.get("lat", type=float)
        lng = request.args.get("lng", type=float)
        radio = request.args.get("radio", 10, type=float)

        query = Negocio.query.filter(Negocio.estado == EstadoNegocio.ACTIVO.value)

        if lat is not None and lng is not None:
            radio_metros = radio * 1000
            if is_postgis():
                # COALESCE: la geometría puede venir NULL (negocios sembrados
                # antes de existir la columna o importados); se reconstruye
                # desde latitud/longitud para no excluirlos del radio.
                query = query.filter(
                    text("""
                        ST_DWithin(
                            COALESCE(
                                geom::geography,
                                ST_SetSRID(ST_MakePoint(longitud, latitud), 4326)::geography
                            ),
                            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                            :radio_metros
                        )
                    """)
                ).params(lng=lng, lat=lat, radio_metros=radio_metros)
                negocios = query.all()
            else:
                # Sin PostGIS (SQLite en dev/test): Haversine en Python.
                negocios = [
                    n for n in query.all()
                    if n.latitud is not None and n.longitud is not None
                    and haversine_km(lat, lng, n.latitud, n.longitud) <= radio
                ]
        else:
            negocios = query.all()

        pins = []
        for n in negocios:
            horario = calcular_estado_horario(n.horarios)
            pins.append({
                "id": n.id,
                "owner_id": n.owner_id,
                "nombre": n.nombre,
                "slug": n.slug,
                "lat": n.latitud,
                "lng": n.longitud,
                "categoria": n.categoria_principal,
                "calificacion": n.calificacion_promedio,
                "verificado": n.verificado,
                "abierto": horario.get("esta_abierto", False),
                "logo_url": n.logo_url,
                "modalidad": n.modalidad,
            })

        # Clustering simple por celda de grilla (round 2 decimales)
        clusters_map = {}
        single_pins = []
        for pin in pins:
            key = (round(pin["lat"], 2), round(pin["lng"], 2))
            if key not in clusters_map:
                clusters_map[key] = []
            clusters_map[key].append(pin)

        clusters = []
        for (c_lat, c_lng), items in clusters_map.items():
            if len(items) > 1:
                clusters.append({
                    "lat": c_lat,
                    "lng": c_lng,
                    "count": len(items),
                    "items": items,
                })
            else:
                single_pins.extend(items)

        # Rutas en curso (ambulantes): el mapa dibuja solo la estela activa.
        ids = [n.id for n in negocios]
        rutas = []
        if ids:
            en_curso = (
                NegocioRuta.query
                .filter(
                    NegocioRuta.negocio_id.in_(ids),
                    NegocioRuta.en_curso.is_(True),
                    NegocioRuta.activa.is_(True),
                )
                .all()
            )
            nombres = {n.id: n.nombre for n in negocios}
            for ruta in en_curso:
                rutas.append({
                    "id": ruta.id,
                    "negocio_id": ruta.negocio_id,
                    "negocio_nombre": nombres.get(ruta.negocio_id, ""),
                    "nombre": ruta.nombre,
                    "puntos": ruta.puntos or [],
                    "calles": ruta.calles or [],
                    "color": ruta.color,
                    "progreso": ruta.progreso or 0.0,
                })

        return {"clusters": clusters, "pins": single_pins, "rutas": rutas}


# ── Búsqueda fuzzy ────────────────────────────────────────────────────

@blp.route("/buscar")
class NegociosBuscar(MethodView):
    @blp.doc()
    @blp.response(200, NegocioResponseSchema(many=True))
    def get(self):
        """Búsqueda fuzzy de negocios."""
        q = request.args.get("q", "")
        if not q or len(q) < 2:
            abort(400, message="El parámetro 'q' debe tener al menos 2 caracteres.")

        query = Negocio.query.filter(Negocio.estado == EstadoNegocio.ACTIVO.value).filter(
            db.or_(
                Negocio.nombre.ilike(f"%{q}%"),
                Negocio.descripcion.ilike(f"%{q}%"),
                Negocio.categoria_principal.ilike(f"%{q}%"),
                Negocio.categorias_secundarias.cast(db.String).ilike(f"%{q}%"),
                Negocio.palabras_clave.cast(db.String).ilike(f"%{q}%"),
            )
        )

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items


# ── Categorías ────────────────────────────────────────────────────────

@blp.route("/categorias")
class NegociosCategorias(MethodView):
    @blp.doc()
    def get(self):
        """Catálogo completo de categorías + las que están en uso.

        `categorias`: catálogo canónico del producto (app/data/categorias_negocio.py).
        `en_uso`: categorías presentes en negocios activos (compatibilidad con
        el comportamiento anterior).
        """
        result = db.session.query(
            Negocio.categoria_principal
        ).filter(Negocio.estado == EstadoNegocio.ACTIVO.value).distinct().all()
        en_uso = [r[0] for r in result]
        return {"categorias": CATEGORIAS_NEGOCIO, "en_uso": en_uso}


# ── Horarios ──────────────────────────────────────────────────────────

class _HorariosUpdateSchema(Schema):
    horarios = fields.List(fields.Nested(HorarioSchema), required=True)


@blp.route("/<int:negocio_id>/horarios")
class NegocioHorarios(MethodView):
    @blp.doc()
    @blp.arguments(_HorariosUpdateSchema)
    @blp.response(200, HorarioSchema(many=True))
    @jwt_required()
    def put(self, data, negocio_id):
        """Actualizar horarios del negocio."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        horarios_data = data.get("horarios", [])

        # Actualizar horarios existentes
        for h_data in horarios_data:
            dia = h_data.get("dia_semana")
            horario = NegocioHorario.query.filter_by(
                negocio_id=negocio_id, dia_semana=dia
            ).first()

            if horario:
                horario.abierto = h_data.get("abierto", True)
                horario.hora_apertura = h_data.get("hora_apertura")
                horario.hora_cierre = h_data.get("hora_cierre")
            else:
                horario = NegocioHorario(
                    negocio_id=negocio_id,
                    dia_semana=dia,
                    abierto=h_data.get("abierto", True),
                    hora_apertura=h_data.get("hora_apertura"),
                    hora_cierre=h_data.get("hora_cierre"),
                )
                db.session.add(horario)

        db.session.commit()

        horarios = NegocioHorario.query.filter_by(
            negocio_id=negocio_id
        ).order_by(NegocioHorario.dia_semana).all()
        _emit_negocio("negocio:actualizado", negocio)
        return horarios


# ── Imágenes ──────────────────────────────────────────────────────────

class _ImagenAddSchema(Schema):
    url = fields.String(required=True)


@blp.route("/<int:negocio_id>/imagenes")
class NegocioImagenes(MethodView):
    @blp.doc()
    @blp.arguments(_ImagenAddSchema)
    @blp.response(201, NegocioResponseSchema)
    @jwt_required()
    def post(self, data, negocio_id):
        """Agregar imagen a la galería del negocio."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        # Copia nueva: mutar la lista JSON in-place no marca la columna dirty
        # en SQLAlchemy 2.0 (JSON no es mutable-tracked por defecto).
        imagenes = list(negocio.imagenes or [])
        imagenes.append(data["url"])
        negocio.imagenes = imagenes
        db.session.commit()
        _emit_negocio("negocio:actualizado", negocio)
        return negocio


@blp.route("/<int:negocio_id>/imagenes/<int:idx>")
class NegocioImagenDelete(MethodView):
    @blp.doc()
    @blp.response(200, NegocioResponseSchema)
    @jwt_required()
    def delete(self, negocio_id, idx):
        """Eliminar imagen de la galería por índice."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        imagenes = list(negocio.imagenes or [])
        if idx < 0 or idx >= len(imagenes):
            abort(400, message="Índice de imagen inválido.")

        # Reasignar lista NUEVA (no mutar in-place): SQLAlchemy 2.0 no detecta
        # cambios en columnas JSON mutadas por referencia.
        negocio.imagenes = [img for i, img in enumerate(imagenes) if i != idx]
        db.session.commit()
        _emit_negocio("negocio:actualizado", negocio)
        return negocio


# ── Ratings ───────────────────────────────────────────────────────────

@blp.route("/<int:negocio_id>/rating")
class NegocioRatingCreate(MethodView):
    @blp.doc()
    @blp.arguments(NegocioRatingCreateSchema)
    @blp.response(201, NegocioRatingResponseSchema)
    @jwt_required()
    def post(self, data, negocio_id):
        """Crear calificación para un negocio."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)

        # Verificar si ya calificó
        existente = NegocioRating.query.filter_by(
            negocio_id=negocio_id, autor_id=user_id
        ).first()
        if existente:
            abort(409, message="Ya has calificado este negocio.")

        rating = NegocioRating(
            negocio_id=negocio_id,
            autor_id=user_id,
            puntaje=data["puntaje"],
            comentario=data.get("comentario"),
        )
        db.session.add(rating)
        db.session.flush()

        # Recalcular promedio
        ratings = NegocioRating.query.filter_by(negocio_id=negocio_id).all()
        total = len(ratings)
        promedio = sum(r.puntaje for r in ratings) / total if total > 0 else 0
        negocio.calificacion_promedio = round(promedio, 2)
        negocio.total_calificaciones = total

        db.session.commit()
        _emit_negocio("negocio:rating", negocio)
        return rating


@blp.route("/<int:negocio_id>/ratings")
class NegocioRatingsList(MethodView):
    @blp.doc()
    @blp.response(200, NegocioRatingResponseSchema(many=True))
    def get(self, negocio_id):
        """Listar calificaciones de un negocio."""
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        query = NegocioRating.query.filter_by(negocio_id=negocio_id).order_by(
            NegocioRating.creado_en.desc()
        )
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items


# ── Reportes ──────────────────────────────────────────────────────────

@blp.route("/<int:negocio_id>/reportar")
class NegocioReporteCreate(MethodView):
    @blp.doc()
    @blp.arguments(NegocioReporteSchema)
    @blp.response(201, NegocioReporteResponseSchema)
    @jwt_required()
    def post(self, data, negocio_id):
        """Crear reporte/denuncia de un negocio."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)

        reporte = NegocioReporte(
            negocio_id=negocio_id,
            reporter_id=user_id,
            tipo=TipoReporte(data["tipo"]),
            descripcion=data.get("descripcion"),
            estado=EstadoReporte.ABIERTO,
        )
        db.session.add(reporte)

        # Crear ticket automático de soporte
        from app.models.ticket import Ticket
        ticket = Ticket(
            user_id=user_id,
            subject=f"Reporte de negocio: {negocio.nombre}",
            body=f"Tipo: {data['tipo']}\nDescripción: {data.get('descripcion', 'N/A')}",
            status="open",
            priority="high",
        )
        db.session.add(ticket)
        db.session.flush()

        reporte.ticket_id = ticket.id
        db.session.commit()
        _emit_negocio("negocio:reporte", negocio)
        return reporte


# ── Stats del Negocio ──────────────────────────────────────────────────

@blp.route("/<int:negocio_id>/stats")
class NegocioStats(MethodView):
    @blp.doc()
    @blp.response(200)
    @jwt_required()
    def get(self, negocio_id):
        """Estadísticas del dashboard del merchant (rating, reviews, solicitudes, contratos, pagos)."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        # Distribución de estrellas
        distribucion = {str(i): 0 for i in range(1, 6)}
        ratings = NegocioRating.query.filter_by(negocio_id=negocio_id).all()
        for r in ratings:
            key = str(r.puntaje)
            distribucion[key] = distribucion.get(key, 0) + 1

        # Solicitudes en zona (categoría del negocio o cercanas)
        from app.models.solicitud import Solicitud, EstadoSolicitud
        solicitudes_query = Solicitud.query.filter(
            Solicitud.categoria == negocio.categoria_principal,
        )
        total_solicitudes_zona = solicitudes_query.count()
        solicitudes_activas = solicitudes_query.filter(
            Solicitud.estado == EstadoSolicitud.PUBLICADO
        ).count()

        # Contratos completados de este merchant
        from app.models.contract import Contract, EstadoContrato
        contratos_completados = Contract.query.filter(
            Contract.proveedor_id == user_id,
            Contract.estado == EstadoContrato.COMPLETADO,
        ).count()

        # Ingresos totales (pagos recibidos)
        from app.models.payment import Payment, EstadoPago
        from sqlalchemy import func
        ingreso_row = db.session.query(func.coalesce(func.sum(Payment.monto), 0)).join(
            Contract
        ).filter(
            Contract.proveedor_id == user_id,
            Payment.estado == EstadoPago.COMPLETADO,
        ).scalar()
        ingresos_totales = int(ingreso_row or 0)

        # Tasa de respuesta (contratos / solicitudes recibidas)
        tasa = (
            round(contratos_completados / total_solicitudes_zona, 2)
            if total_solicitudes_zona > 0
            else 0.0
        )

        return {
            "negocio_id": negocio_id,
            "periodo": "total",
            "calificacion_promedio": negocio.calificacion_promedio or 0.0,
            "total_calificaciones": negocio.total_calificaciones or 0,
            "distribucion_estrellas": distribucion,
            "total_solicitudes_zona": total_solicitudes_zona,
            "solicitudes_activas": solicitudes_activas,
            "contratos_completados": contratos_completados,
            "ingresos_totales": ingresos_totales,
            "visitas_perfil": 0,  # Placeholder: se implementa con tracking
            "tasa_respuesta": tasa,
        }


# ── Upload de Imagen del Negocio ───────────────────────────────────────

@blp.route("/<int:negocio_id>/imagenes/upload")
class NegocioImagenUpload(MethodView):
    @blp.doc()
    @blp.response(201)
    @jwt_required()
    def post(self, negocio_id):
        """Sube una imagen real del negocio a MinIO (Form-data con campo 'file').

        Query `destino`:
            galeria (default) → se agrega a `imagenes`
            logo              → se guarda en `logo_url`
            banner            → se guarda en `banner_url`

        Logo y banner NO forman parte de la galería del negocio.
        """
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        destino = (request.args.get("destino") or "galeria").lower()
        if destino not in ("galeria", "logo", "banner"):
            abort(400, message="Destino no válido. Usa: galeria, logo o banner.")

        # Validar archivo
        file = request.files.get("file")
        if not file:
            abort(400, message="Campo 'file' requerido.")

        # Validar tipo MIME
        allowed_types = ("image/jpeg", "image/png", "image/webp")
        if file.content_type not in allowed_types:
            abort(400, message="Formato no válido. Aceptados: jpg, png, webp.")

        # Leer bytes
        file_bytes = file.read()
        if not file_bytes:
            abort(400, message="Archivo vacío.")

        # Límite 5MB
        if len(file_bytes) > 5 * 1024 * 1024:
            abort(400, message="El archivo excede el límite de 5MB.")

        # Límite 20 imágenes por negocio (solo galería)
        imagenes_actuales = list(negocio.imagenes or [])
        if destino == "galeria" and len(imagenes_actuales) >= 20:
            abort(400, message="Máximo 20 imágenes por negocio.")

        # Subir a MinIO
        from app.services.storage import storage
        if storage is None:
            abort(500, message="Servicio de almacenamiento no disponible.")

        try:
            import time
            filename = f"negocio_{negocio_id}_{int(time.time())}"
            url = storage.upload_business_image(file_bytes, str(negocio_id), filename)
        except ValueError as e:
            abort(400, message=str(e))
        except Exception as e:
            abort(500, message=f"Error subiendo imagen: {str(e)}")

        # Logo y banner se guardan aparte: no contaminan la galería.
        if destino == "logo":
            negocio.logo_url = url
        elif destino == "banner":
            negocio.banner_url = url
        else:
            imagenes_actuales.append(url)
            negocio.imagenes = imagenes_actuales

        negocio.actualizado_en = datetime.now(timezone.utc)
        db.session.commit()

        _emit_negocio("negocio:actualizado", negocio)
        return {"url": url, "negocio_id": negocio_id, "destino": destino}, 201

# -- Rutas del negocio ambulante ---------------------------------------

def _ruta_of_negocio_or_404(negocio_id: int, ruta_id: int) -> NegocioRuta:
    ruta = NegocioRuta.query.filter_by(
        id=ruta_id, negocio_id=negocio_id
    ).first()
    if ruta is None:
        abort(404, message="Ruta no encontrada.")
    return ruta


def _solo_una_en_curso(negocio_id: int, ruta_id: int) -> None:
    """Deja en curso únicamente la ruta indicada."""
    (
        NegocioRuta.query
        .filter(
            NegocioRuta.negocio_id == negocio_id,
            NegocioRuta.id != ruta_id,
            NegocioRuta.en_curso.is_(True),
        )
        .update({"en_curso": False, "progreso": 0.0}, synchronize_session=False)
    )


@blp.route("/<int:negocio_id>/rutas")
class NegocioRutas(MethodView):
    @blp.doc()
    @blp.response(200, NegocioRutaResponseSchema(many=True))
    def get(self, negocio_id):
        """Lista pública de rutas del negocio (perfil público)."""
        negocio = _get_negocio_or_404(negocio_id)
        return negocio.rutas

    @blp.doc()
    @blp.arguments(NegocioRutaCreateSchema)
    @blp.response(201, NegocioRutaResponseSchema)
    @jwt_required()
    def post(self, data, negocio_id):
        """Crea una ruta (solo owner y negocio ambulante)."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

        if negocio.modalidad != ModalidadNegocio.AMBULANTE.value:
            abort(400, message="Activa la modalidad ambulante para crear rutas.")

        ruta = NegocioRuta(
            negocio_id=negocio_id,
            nombre=data["nombre"].strip(),
            descripcion=data.get("descripcion"),
            puntos=data["puntos"],
            calles=data.get("calles", []),
            color=data.get("color"),
            activa=data.get("activa", True),
        )
        db.session.add(ruta)
        db.session.commit()
        _emit_ruta("negocio:ruta", negocio, ruta)
        return ruta


@blp.route("/<int:negocio_id>/rutas/<int:ruta_id>")
class NegocioRutaDetail(MethodView):
    @blp.doc()
    @blp.arguments(NegocioRutaUpdateSchema)
    @blp.response(200, NegocioRutaResponseSchema)
    @jwt_required()
    def put(self, data, negocio_id, ruta_id):
        """Actualiza una ruta (incluye iniciar/detener y progreso)."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)
        ruta = _ruta_of_negocio_or_404(negocio_id, ruta_id)

        if data.get("en_curso") and negocio.modalidad != ModalidadNegocio.AMBULANTE.value:
            abort(400, message="Activa la modalidad ambulante para iniciar rutas.")

        if data.get("en_curso"):
            _solo_una_en_curso(negocio_id, ruta.id)
            if "progreso" not in data:
                ruta.progreso = 0.0

        for key, value in data.items():
            setattr(ruta, key, value)

        if data.get("en_curso") is False and "progreso" not in data:
            ruta.progreso = 0.0

        db.session.commit()
        _emit_ruta("negocio:ruta", negocio, ruta)
        return ruta

    @blp.doc()
    @blp.response(204)
    @jwt_required()
    def delete(self, negocio_id, ruta_id):
        """Elimina una ruta del negocio."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)
        ruta = _ruta_of_negocio_or_404(negocio_id, ruta_id)

        _emit_ruta("negocio:ruta", negocio, ruta, eliminar=True)
        db.session.delete(ruta)
        db.session.commit()
        return "", 204
