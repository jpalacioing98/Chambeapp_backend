"""Blueprint público de Términos y Condiciones (sin JWT).

GET /api/v1/legal/tyc -> lee SystemConfig 'tyc_current' (value_type=json).
"""

from flask import jsonify
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.extensions import db
from app.models.config import SystemConfig

blp = Blueprint("legal", __name__, description="Términos y Condiciones públicos")


@blp.route("/tyc")
class TyCPublic(MethodView):
    def get(self):
        """Retorna la versión vigente de T&C (público, sin autenticación)."""
        cfg = SystemConfig.query.filter_by(key="tyc_current").first()
        if not cfg:
            abort(404, message="No hay T&C configurados")
        data = SystemConfig.parse_value(cfg.value, "json") or {}
        return (
            jsonify(
                {
                    "version": data.get("version"),
                    "content": data.get("content"),
                    "published_at": data.get("published_at"),
                }
            ),
            200,
        )
