"""Region blueprint: catálogo de regiones para la división administrativa.

GET /api/v1/regions              -> lista de regiones (JWT requerido).
GET /api/v1/regions/detectar      -> región derivada de una ubicación.
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint
from flask_jwt_extended import jwt_required

from app.models.region import Region
from app.services.region import match_region_from_text

blp = Blueprint("regions", __name__, description="Division regional")


@blp.route("")
class RegionList(MethodView):
    @jwt_required()
    def get(self):
        """Lista todas las regiones registradas."""
        regions = Region.query.order_by(Region.id).all()
        return {"items": [r.to_dict() for r in regions]}, 200


@blp.route("/detectar")
class RegionDetect(MethodView):
    @jwt_required()
    def get(self):
        """Deriva la región desde un texto de ubicación (departamento/ciudad)."""
        ubicacion = request.args.get("ubicacion", "")
        region = match_region_from_text(ubicacion)
        return {"region": region.to_dict() if region else None}, 200