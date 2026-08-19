"""Blueprint KYC documental por rol (Politica_KYC.md).

Endpoints (JWT requerido):
  GET  /api/v1/kyc/documentos-requeridos -> catálogo filtrado por rol del usuario.
  GET  /api/v1/kyc/mis-documentos        -> estado de los documentos del usuario.
  POST /api/v1/kyc/documentos           -> envía (upsert) un documento del usuario.
"""

from datetime import datetime, timezone

from flask import jsonify, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.kyc import DocumentoRequerido, DocumentoUsuario

blp = Blueprint("kyc", __name__, description="KYC documental por rol")


def _current_user() -> User:
    return db.get_or_404(User, int(get_jwt_identity()))


@blp.route("/documentos-requeridos")
class DocumentosRequeridos(MethodView):
    @jwt_required()
    def get(self):
        """Lista los documentos KYC requeridos para el rol del usuario."""
        user = _current_user()
        docs = (
            DocumentoRequerido.query.filter_by(rol=user.rol.value)
            .order_by(DocumentoRequerido.orden)
            .all()
        )
        return (
            jsonify(
                {
                    "rol": user.rol.value,
                    "documentos": [
                        {
                            "clave": d.clave,
                            "nombre": d.nombre,
                            "descripcion": d.descripcion,
                            "obligatorio": d.obligatorio,
                            "grupo": d.grupo,
                            "orden": d.orden,
                        }
                        for d in docs
                    ],
                }
            ),
            200,
        )


@blp.route("/mis-documentos")
class MisDocumentos(MethodView):
    @jwt_required()
    def get(self):
        """Estado de los documentos KYC del usuario, unido con el catálogo."""
        user = _current_user()
        requeridos = DocumentoRequerido.query.filter_by(rol=user.rol.value).all()
        enviados = {
            du.documento_clave: du
            for du in DocumentoUsuario.query.filter_by(user_id=user.id).all()
        }
        documentos = []
        for d in requeridos:
            du = enviados.get(d.clave)
            documentos.append(
                {
                    "clave": d.clave,
                    "nombre": d.nombre,
                    "descripcion": d.descripcion,
                    "obligatorio": d.obligatorio,
                    "grupo": d.grupo,
                    "estado": du.estado if du else "no_enviado",
                    "url": du.url if du else None,
                    "fecha_envio": (
                        du.fecha_envio.isoformat() if du and du.fecha_envio else None
                    ),
                }
            )
        return jsonify({"documentos": documentos}), 200


@blp.route("/documentos")
class Documentos(MethodView):
    @jwt_required()
    def post(self):
        """Envía (upsert) un documento KYC válido para el rol del usuario."""
        user = _current_user()
        data = request.get_json(silent=True) or {}
        clave = data.get("clave")
        if not clave:
            abort(400, message="El campo 'clave' es obligatorio.")

        req = DocumentoRequerido.query.filter_by(
            rol=user.rol.value, clave=clave
        ).first()
        if not req:
            abort(400, message="La clave de documento no es válida para su rol.")

        du = DocumentoUsuario.query.filter_by(
            user_id=user.id, documento_clave=clave
        ).first()
        now = datetime.now(timezone.utc)
        if du is None:
            du = DocumentoUsuario(
                user_id=user.id,
                documento_clave=clave,
                rol=user.rol.value,
            )
            db.session.add(du)
        du.estado = "enviado"
        du.fecha_envio = now
        du.url = data.get("url")
        db.session.commit()

        return (
            jsonify(
                {
                    "user_id": du.user_id,
                    "documento_clave": du.documento_clave,
                    "rol": du.rol,
                    "estado": du.estado,
                    "url": du.url,
                    "fecha_envio": du.fecha_envio.isoformat(),
                }
            ),
            200,
        )
