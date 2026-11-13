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
from app.models.user import User
from app.services.support_events import notificar_nuevo_ticket
from app.schemas.admin import (
    TicketCreateSchema,
    TicketCreateResponseSchema,
    MyTicketsResponseSchema,
)

blp = Blueprint("tickets", __name__, description="Tickets de soporte")


@blp.route("/")
class TicketCreate(MethodView):
    @jwt_required()
    @blp.arguments(TicketCreateSchema)
    @blp.response(201, TicketCreateResponseSchema)
    def post(self, data):
        """Crea un ticket de soporte.

        Cualquier usuario autenticado crea el suyo. El staff
        (soporte/admin/superadmin) puede crearlo a nombre de otro usuario
        enviando `user_id`.
        """
        actor_id = int(get_jwt_identity())
        actor = db.session.get(User, actor_id)
        user_id = data.get("user_id") or actor_id

        if user_id != actor_id:
            roles_staff = {"soporte", "admin", "superadmin"}
            if actor is None or actor.rol.value not in roles_staff:
                abort(403, message="Solo el equipo de soporte puede crear tickets a nombre de otro usuario.")
            if db.session.get(User, user_id) is None:
                abort(404, message="El usuario indicado no existe.")

        ticket = Ticket(
            user_id=user_id,
            subject=data["subject"].strip(),
            body=data["body"].strip(),
            category=data.get("category", "otro"),
        )
        db.session.add(ticket)
        db.session.commit()

        user = db.session.get(User, user_id)
        if user is not None:
            notificar_nuevo_ticket(ticket, user)

        return {
            "id": ticket.id,
            "status": ticket.status,
            "category": ticket.category,
        }


@blp.route("/mios")
class MyTickets(MethodView):
    @jwt_required()
    @blp.doc(summary="Tickets del usuario autenticado")
    @blp.response(200, MyTicketsResponseSchema)
    def get(self):
        """Lista los tickets del usuario (más recientes primero)."""
        user_id = int(get_jwt_identity())
        tickets = (
            Ticket.query
            .filter_by(user_id=user_id)
            .order_by(Ticket.created_at.desc())
            .limit(50)
            .all()
        )
        return {"items": tickets, "total": len(tickets)}
