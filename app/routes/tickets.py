"""Tickets blueprint (RBAC Fase 2): creación de tickets por cualquier usuario.

El POST /api/v1/tickets es público para usuarios autenticados (NO admin_required).
La gestión de tickets (listar/actualizar) vive en el blueprint admin.

Registrado en /api/v1/tickets.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.ticket import Ticket
from app.schemas.admin import TicketCreateSchema, TicketCreateResponseSchema

blp = Blueprint("tickets", __name__, description="Tickets de soporte")


@blp.route("/")
class TicketCreate(MethodView):
    @jwt_required()
    @blp.arguments(TicketCreateSchema)
    @blp.response(201, TicketCreateResponseSchema)
    def post(self, data):
        """Crea un ticket de soporte (cualquier usuario autenticado)."""
        user_id = int(get_jwt_identity())
        ticket = Ticket(
            user_id=user_id,
            subject=data["subject"],
            body=data["body"],
        )
        db.session.add(ticket)
        db.session.commit()
        return {"id": ticket.id, "status": ticket.status}
