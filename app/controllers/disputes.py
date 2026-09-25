"""Disputes blueprint: creación y gestión de disputas por usuarios (P1)."""

from datetime import datetime, timezone

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.contract import Contract, Dispute, EstadoContrato
from app.schemas.contracts import DisputeCreateSchema, DisputeSchema

blp = Blueprint("disputes", __name__, description="Disputas de contrato (P1)")


@blp.route("/contracts/<int:contract_id>/disputes")
class DisputeList(MethodView):
    @jwt_required()
    @blp.arguments(DisputeCreateSchema)
    @blp.response(201, DisputeSchema)
    def post(self, data, contract_id):
        """Crea una disputa para un contrato. Solo participantes pueden crear."""
        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)
        
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")
        
        # No se pueden crear disputas en contratos finalizados o cancelados
        if contract.estado in (EstadoContrato.COMPLETADO, EstadoContrato.CANCELADO):
            abort(400, message="No se pueden crear disputas en contratos finalizados.")
        
        # Verificar que no exista ya una disputa abierta
        existing = Dispute.query.filter_by(
            contract_id=contract_id,
            status="abierta",
        ).first()
        if existing:
            abort(400, message="Ya existe una disputa abierta para este contrato.")
        
        dispute = Dispute(
            contract_id=contract_id,
            reason=data["reason"],
            status="abierta",
        )
        db.session.add(dispute)
        db.session.commit()
        
        return dispute

    @jwt_required()
    @blp.response(200, DisputeSchema(many=True))
    def get(self, contract_id):
        """Lista disputas de un contrato. Solo participantes pueden ver."""
        user_id = int(get_jwt_identity())
        contract = db.get_or_404(Contract, contract_id)
        
        if user_id not in (contract.solicitante_id, contract.proveedor_id):
            abort(403, message="No participas en este contrato.")
        
        return Dispute.query.filter_by(contract_id=contract_id).order_by(
            Dispute.created_at.desc()
        ).all()


@blp.route("/my-disputes")
class MyDisputes(MethodView):
    @jwt_required()
    @blp.response(200, DisputeSchema(many=True))
    def get(self):
        """Lista disputas donde el usuario es participante."""
        user_id = int(get_jwt_identity())
        
        # Obtener contratos del usuario
        contract_ids = [
            c.id for c in Contract.query.filter(
                (Contract.solicitante_id == user_id) | (Contract.proveedor_id == user_id)
            ).all()
        ]
        
        return Dispute.query.filter(
            Dispute.contract_id.in_(contract_ids)
        ).order_by(Dispute.created_at.desc()).all()
