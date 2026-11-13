"""Plantillas de texto configurables: KYC, tickets y veredictos de disputa.

Antes vivían duplicadas en el frontend (y se perdían al recargar). Ahora son
configuración del servidor, editables por el superadmin y legibles por los
roles operativos.

Registrado en /api/v1/plantillas.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity
from marshmallow import Schema, fields, validate

from app.extensions import db
from app.auth.decorators import role_required, superadmin_required
from app.models.config import SystemConfig
from app.models.audit import write_audit

blp = Blueprint("plantillas", __name__, description="Plantillas de texto")

_CLAVE = "plantillas_soporte"

# Tipo → (descripción, textos por defecto)
TIPOS = {
    "kyc_rechazo": (
        "Motivos de rechazo de documentos KYC",
        [
            "El documento está ilegible o cortado.",
            "El documento está vencido.",
            "Los datos del documento no coinciden con el perfil.",
            "Falta una cara o página del documento.",
            "La imagen parece editada o es una captura de pantalla.",
        ],
    ),
    "ticket_respuesta": (
        "Respuestas rápidas para tickets de soporte",
        [
            "Estamos revisando tu caso y te respondemos pronto.",
            "Necesitamos más información para continuar.",
            "Tu caso fue resuelto. Cualquier duda, responde a este ticket.",
        ],
    ),
    "disputa_veredicto": (
        "Plantillas de veredicto para disputas",
        [
            "Se libera el pago al proveedor por entrega conforme.",
            "Se reembolsa al solicitante por incumplimiento.",
            "Se reconoce el trabajo parcial y se divide el monto.",
        ],
    ),
}


class PlantillaUpdateSchema(Schema):
    items = fields.List(
        fields.String(validate=validate.Length(min=3, max=300)),
        required=True,
        validate=validate.Length(min=1, max=30),
    )


class PlantillasResponseSchema(Schema):
    kyc_rechazo = fields.List(fields.String())
    ticket_respuesta = fields.List(fields.String())
    disputa_veredicto = fields.List(fields.String())


def _leer() -> dict:
    """Plantillas guardadas, completando con los defaults de cada tipo."""
    cfg = SystemConfig.query.filter_by(key=_CLAVE).first()
    guardadas = SystemConfig.parse_value(cfg.value, "json") if cfg else {}
    guardadas = guardadas if isinstance(guardadas, dict) else {}
    salida = {}
    for tipo, (_descripcion, defecto) in TIPOS.items():
        valor = guardadas.get(tipo)
        salida[tipo] = [str(item) for item in valor] if isinstance(valor, list) else list(defecto)
    return salida


@blp.route("/")
class PlantillasList(MethodView):
    @role_required(["verificador", "soporte", "admin", "superadmin"])
    @blp.response(200, PlantillasResponseSchema)
    def get(self):
        """Plantillas vigentes para todos los roles operativos."""
        return _leer()


@blp.route("/<string:tipo>")
class PlantillaDetail(MethodView):
    @superadmin_required
    @blp.arguments(PlantillaUpdateSchema)
    @blp.response(200, PlantillasResponseSchema)
    def put(self, data, tipo):
        """Reemplaza las plantillas de un tipo (solo superadmin)."""
        if tipo not in TIPOS:
            abort(404, message=f"Tipo de plantilla desconocido: {tipo}.")

        actuales = _leer()
        antes = {tipo: actuales.get(tipo)}
        # Limpia espacios y descarta entradas vacías.
        items = [texto.strip() for texto in data["items"] if texto.strip()]
        if not items:
            abort(400, message="Debes enviar al menos una plantilla con texto.")

        actuales[tipo] = items
        cfg = SystemConfig.query.filter_by(key=_CLAVE).first()
        if cfg is None:
            cfg = SystemConfig(
                key=_CLAVE,
                value_type="json",
                description="Plantillas de texto (KYC, tickets, disputas)",
            )
            db.session.add(cfg)
        cfg.value = SystemConfig.serialize_value(actuales, "json")
        cfg.updated_by = int(get_jwt_identity())
        write_audit(
            int(get_jwt_identity()),
            f"plantillas.update.{tipo}",
            "system_config",
            cfg.id,
            antes,
            {tipo: items},
        )
        db.session.commit()
        return actuales
