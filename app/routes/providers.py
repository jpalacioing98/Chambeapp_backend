"""Providers blueprint: search and discover PDS profiles (P2-1)."""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint

from app.extensions import db
from app.models.user import User, Profile, RolUsuario
from app.schemas.providers import (
    ProviderSearchSchema,
    ProviderSearchItemSchema,
    ProviderSearchResponseSchema,
)
from app.services.pagination import paginate_query

blp = Blueprint("providers", __name__, description="Búsqueda de proveedores (P2-1)")


@blp.route("/search")
class ProviderSearch(MethodView):
    @blp.arguments(ProviderSearchSchema, location="query")
    @blp.response(200, ProviderSearchResponseSchema)
    def get(self, args):
        """P2-1: busca proveedores (PDS) activos con filtros y paginación.

        Query params: q, categoria, zona, min_rating, verificado, page, per_page
        """
        query = (
            User.query.join(Profile, User.id == Profile.user_id)
            .filter(User.rol == RolUsuario.PDS, User.status == "active")
        )

        q = args.get("q")
        if q:
            query = query.filter(
                db.or_(
                    User.nombre.ilike(f"%{q}%"),
                    Profile.experiencia.ilike(f"%{q}%"),
                )
            )

        categoria = args.get("categoria")
        if categoria:
            query = query.filter(
                Profile.categorias.ilike(f"%{categoria}%")
            )

        zona = args.get("zona")
        if zona:
            query = query.filter(Profile.zona.ilike(f"%{zona}%"))

        min_rating = args.get("min_rating")
        if min_rating is not None:
            query = query.filter(Profile.calificacion_promedio >= min_rating)

        verificado = args.get("verificado")
        if verificado is not None:
            query = query.filter(Profile.verificado == verificado)

        query = query.order_by(Profile.calificacion_promedio.desc())

        page = args.get("page")
        per_page = args.get("per_page")
        result = paginate_query(query, page=page, per_page=per_page)

        # If backward compatible (no pagination params), wrap in response format
        if isinstance(result, list):
            items = []
            for user in result:
                p = user.profile
                items.append({
                    "id": user.id,
                    "email": user.email,
                    "nombre": user.nombre,
                    "rol": user.rol,
                    "habilidades": p.habilidades,
                    "experiencia": p.experiencia,
                    "zona": p.zona,
                    "categorias": p.categorias,
                    "portafolio": p.portafolio,
                    "calificacion_promedio": p.calificacion_promedio,
                    "verificado": p.verificado,
                    "badges": p.badges,
                    "perfil_completo": p.perfil_completo,
                })
            return {"items": items, "total": len(items), "page": 1, "per_page": len(items), "pages": 1}
        else:
            items = []
            for user in result["items"]:
                p = user.profile
                items.append({
                    "id": user.id,
                    "email": user.email,
                    "nombre": user.nombre,
                    "rol": user.rol,
                    "habilidades": p.habilidades,
                    "experiencia": p.experiencia,
                    "zona": p.zona,
                    "categorias": p.categorias,
                    "portafolio": p.portafolio,
                    "calificacion_promedio": p.calificacion_promedio,
                    "verificado": p.verificado,
                    "badges": p.badges,
                    "perfil_completo": p.perfil_completo,
                })
            result["items"] = items
            return result
