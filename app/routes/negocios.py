"""Blueprint Negocios: CRUD, mapa, búsqueda, horarios, ratings, reportes."""

from datetime import datetime, timezone

from marshmallow import Schema, fields

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import text

from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.negocio import (
    Negocio, NegocioHorario, NegocioRating, NegocioReporte,
    TipoNegocio, EstadoNegocio, EstadoReporte, TipoReporte,
)
from app.schemas.negocios import (
    NegocioCreateSchema,
    NegocioUpdateSchema,
    NegocioResponseSchema,
    HorarioSchema,
    NegocioReporteSchema,
    NegocioReporteResponseSchema,
    NegocioRatingCreateSchema,
    NegocioRatingResponseSchema,
    NegocioMapResponseSchema,
)
from app.services.negocio_utils import calcular_estado_horario, generar_slug

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
        return negocio

    @blp.doc()
    @blp.response(200, NegocioResponseSchema(many=True))
    def get(self):
        """Listar negocios activos con filtros opcionales."""
        query = Negocio.query.filter_by(estado=EstadoNegocio.ACTIVO)

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
            if value is not None:
                setattr(negocio, key, value)

        # Regenerar geom si cambiaron coordenadas
        if "latitud" in data or "longitud" in data:
            negocio.geom = text(
                f"ST_SetSRID(ST_MakePoint({negocio.longitud}, {negocio.latitud}), 4326)"
            )

        negocio.actualizado_en = datetime.now(timezone.utc)
        db.session.commit()
        return negocio

    @blp.doc()
    @blp.response(204)
    @jwt_required()
    def delete(self, negocio_id):
        """Eliminar un negocio (solo owner)."""
        user_id = int(get_jwt_identity())
        negocio = _get_negocio_or_404(negocio_id)
        _ensure_owner(negocio, user_id)

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

        query = Negocio.query.filter_by(estado=EstadoNegocio.ACTIVO)

        if lat and lng:
            radio_metros = radio * 1000
            query = query.filter(
                text("""
                    ST_DWithin(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                        :radio_metros
                    )
                """)
            ).params(lng=lng, lat=lat, radio_metros=radio_metros)

        negocios = query.all()

        pins = []
        for n in negocios:
            horario = calcular_estado_horario(n.horarios)
            pins.append({
                "id": n.id,
                "nombre": n.nombre,
                "slug": n.slug,
                "lat": n.latitud,
                "lng": n.longitud,
                "categoria": n.categoria_principal,
                "calificacion": n.calificacion_promedio,
                "verificado": n.verificado,
                "abierto": horario.get("esta_abierto", False),
                "logo_url": n.logo_url,
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

        return {"clusters": clusters, "pins": single_pins}


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

        query = Negocio.query.filter_by(estado=EstadoNegocio.ACTIVO).filter(
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
        """Categorías disponibles (distinct de categorías activas)."""
        result = db.session.query(
            Negocio.categoria_principal
        ).filter_by(estado=EstadoNegocio.ACTIVO).distinct().all()
        return {"categorias": [r[0] for r in result]}


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

        imagenes = negocio.imagenes or []
        imagenes.append(data["url"])
        negocio.imagenes = imagenes
        db.session.commit()
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

        imagenes = negocio.imagenes or []
        if idx < 0 or idx >= len(imagenes):
            abort(400, message="Índice de imagen inválido.")

        imagenes.pop(idx)
        negocio.imagenes = imagenes
        db.session.commit()
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
        return reporte
