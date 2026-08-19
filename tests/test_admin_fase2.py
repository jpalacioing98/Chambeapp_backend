"""pytest — RBAC Fase 2: moderación admin, disputas/escrow, tickets, contenido."""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud, Rating
from app.models.contract import Contract, EstadoContrato, Dispute
from app.models.payment import Payment, EstadoPago
from app.models.ticket import Ticket


@pytest.fixture
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(email, rol, nombre=None, status="active"):
    u = User(
        email=email,
        rol=rol,
        nombre=nombre,
        acepto_tyc=True,
        activo=True,
        status=status,
    )
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.commit()
    return u


def _headers(user):
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.rol.value, "role_v": user.role_version},
    )
    return {"Authorization": f"Bearer {token}"}


def _make_service(owner, titulo="Servicio demo", estado=EstadoSolicitud.PUBLICADO):
    s = Solicitud(
        solicitante_id=owner.id,
        titulo=titulo,
        categoria="plomería",
        descripcion="Reparación de tubería.",
        ubicacion="Valledupar",
        presupuesto=120000,
        estado=estado,
    )
    db.session.add(s)
    db.session.commit()
    return s


def _make_contract(service, comprador, vendedor, estado=EstadoContrato.COMPLETADO):
    o = Contract(
        service_id=service.id,
        proveedor_id=vendedor.id,
        solicitante_id=comprador.id,
        estado=estado,
    )
    db.session.add(o)
    db.session.commit()
    return o


def _make_payment(order, estado=EstadoPago.EN_ESCROW):
    p = Payment(
        contract_id=order.id,
        monto=100000,
        comision=12000,
        estado=estado,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _make_dispute(order, status="abierta"):
    d = Dispute(contract_id=order.id, reason="Trabajo no conforme.", status=status)
    db.session.add(d)
    db.session.commit()
    return d


# ---------------- moderación de servicios ----------------

def test_admin_moderar_servicio_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    owner = _make_user("owner@x.com", RolUsuario.EMPLEADOR, "Owner")
    s = _make_service(owner)
    r = client.patch(
        f"/api/v1/admin/solicitudes/{s.id}/moderate",
        headers=_headers(admin),
        json={"action": "hide"},
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "oculto"
    db.session.refresh(s)
    assert s.estado == EstadoSolicitud.OCULTO


def test_admin_listar_servicios_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    owner = _make_user("owner@x.com", RolUsuario.EMPLEADOR, "Owner")
    _make_service(owner, titulo="Fuga agua")
    r = client.get("/api/v1/admin/solicitudes?q=agua", headers=_headers(admin))
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 1
    assert any(i["titulo"] == "Fuga agua" for i in data["items"])


# ---------------- moderación de órdenes ----------------

def test_admin_moderar_orden_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    comprador = _make_user("c@x.com", RolUsuario.EMPLEADOR, "C")
    vendedor = _make_user("v@x.com", RolUsuario.TRABAJADOR, "V")
    s = _make_service(comprador)
    o = _make_contract(s, comprador, vendedor)
    r = client.patch(
        f"/api/v1/admin/contracts/{o.id}/moderate",
        headers=_headers(admin),
        json={"action": "flag"},
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "marcado"
    db.session.refresh(o)
    assert o.estado == EstadoContrato.MARCADO


def test_admin_listar_ordenes_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    comprador = _make_user("c@x.com", RolUsuario.EMPLEADOR, "C")
    vendedor = _make_user("v@x.com", RolUsuario.TRABAJADOR, "V")
    s = _make_service(comprador)
    o = _make_contract(s, comprador, vendedor)
    _make_payment(o)
    r = client.get("/api/v1/admin/contracts", headers=_headers(admin))
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 1
    item = next(i for i in data["items"] if i["id"] == o.id)
    assert item["monto"] == 100000


# ---------------- disputas / escrow ----------------

def test_admin_listar_disputas_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    comprador = _make_user("c@x.com", RolUsuario.EMPLEADOR, "C")
    vendedor = _make_user("v@x.com", RolUsuario.TRABAJADOR, "V")
    s = _make_service(comprador)
    o = _make_contract(s, comprador, vendedor)
    _make_dispute(o)
    r = client.get("/api/v1/admin/disputes?status=abierta", headers=_headers(admin))
    assert r.status_code == 200
    assert r.get_json()["total"] >= 1


def test_admin_detalle_disputa_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    comprador = _make_user("c@x.com", RolUsuario.EMPLEADOR, "C")
    vendedor = _make_user("v@x.com", RolUsuario.TRABAJADOR, "V")
    s = _make_service(comprador)
    o = _make_contract(s, comprador, vendedor)
    p = _make_payment(o)
    d = _make_dispute(o)
    r = client.get(f"/api/v1/admin/disputes/{d.id}", headers=_headers(admin))
    assert r.status_code == 200
    data = r.get_json()
    assert data["contract"]["id"] == o.id
    assert data["payment"]["id"] == p.id


def test_admin_resolver_disputa_release_cambia_pago(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    comprador = _make_user("c@x.com", RolUsuario.EMPLEADOR, "C")
    vendedor = _make_user("v@x.com", RolUsuario.TRABAJADOR, "V")
    s = _make_service(comprador)
    o = _make_contract(s, comprador, vendedor)
    p = _make_payment(o, estado=EstadoPago.EN_ESCROW)
    d = _make_dispute(o)
    r = client.post(
        f"/api/v1/admin/disputes/{d.id}/resolve",
        headers=_headers(admin),
        json={"resolution": "A favor del proveedor", "escrow_action": "release"},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "resuelta"
    assert r.get_json()["escrow_action"] == "release"
    db.session.refresh(p)
    assert p.estado == EstadoPago.LIBERADO
    db.session.refresh(d)
    assert d.status == "resuelta"
    assert d.resolved_by == admin.id


def test_admin_resolver_disputa_refund_reviete_comision(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    comprador = _make_user("c@x.com", RolUsuario.EMPLEADOR, "C")
    vendedor = _make_user("v@x.com", RolUsuario.TRABAJADOR, "V")
    s = _make_service(comprador)
    o = _make_contract(s, comprador, vendedor)
    p = _make_payment(o, estado=EstadoPago.EN_ESCROW)
    d = _make_dispute(o)
    r = client.post(
        f"/api/v1/admin/disputes/{d.id}/resolve",
        headers=_headers(admin),
        json={"resolution": "Reembolso al comprador", "escrow_action": "refund"},
    )
    assert r.status_code == 200
    db.session.refresh(p)
    assert p.estado == EstadoPago.REEMBOLSADO
    assert p.comision == 0  # comisión revertida


# ---------------- tickets ----------------

def test_usuario_crea_ticket_201(client):
    user = _make_user("u@x.com", RolUsuario.TRABAJADOR, "U")
    r = client.post(
        "/api/v1/tickets/",
        headers=_headers(user),
        json={"subject": "No puedo pagar", "body": "Ayuda por favor"},
    )
    assert r.status_code == 201
    assert r.get_json()["status"] == "open"
    t = db.session.get(Ticket, r.get_json()["id"])
    assert t is not None
    assert t.user_id == user.id


def test_admin_lista_y_gestiona_ticket_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    user = _make_user("u@x.com", RolUsuario.TRABAJADOR, "U")
    t = Ticket(user_id=user.id, subject="Problema", body="Detalle")
    db.session.add(t)
    db.session.commit()
    # listar
    r = client.get("/api/v1/admin/tickets", headers=_headers(admin))
    assert r.status_code == 200
    assert r.get_json()["total"] >= 1
    # gestionar
    r2 = client.patch(
        f"/api/v1/admin/tickets/{t.id}",
        headers=_headers(admin),
        json={"status": "pending", "priority": "high", "assigned_to": admin.id},
    )
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "pending"
    db.session.refresh(t)
    assert t.priority == "high"
    assert t.assigned_to == admin.id


# ---------------- moderación de contenido ----------------

def test_admin_moderar_contenido_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    autor = _make_user("a@x.com", RolUsuario.TRABAJADOR, "A")
    calificado = _make_user("b@x.com", RolUsuario.TRABAJADOR, "B")
    owner = _make_user("o@x.com", RolUsuario.EMPLEADOR, "O")
    s = _make_service(owner)
    rating = Rating(
        service_id=s.id, autor_id=autor.id, calificado_id=calificado.id,
        puntaje=1, comentario="Malo",
    )
    db.session.add(rating)
    db.session.commit()
    # lista
    r = client.get("/api/v1/admin/content/reports", headers=_headers(admin))
    assert r.status_code == 200
    assert r.get_json()["total"] >= 1
    # ocultar (soft)
    r2 = client.patch(
        f"/api/v1/admin/content/{rating.id}/moderate",
        headers=_headers(admin),
        json={"action": "hide"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["action"] == "hide"
    db.session.refresh(rating)
    assert rating.reportado is True


# ---------------- control de acceso 403 ----------------

@pytest.mark.parametrize(
    "rol",
    [RolUsuario.TRABAJADOR, RolUsuario.EMPLEADOR],
)
def test_no_admin_403_en_endpoints_admin(client, rol):
    u = _make_user("u@x.com", rol, "U")
    endpoints = [
        ("GET", "/api/v1/admin/solicitudes"),
        ("GET", "/api/v1/admin/contracts"),
        ("GET", "/api/v1/admin/disputes"),
        ("GET", "/api/v1/admin/tickets"),
        ("GET", "/api/v1/admin/content/reports"),
    ]
    for method, url in endpoints:
        r = client.open(url, method=method, headers=_headers(u))
        assert r.status_code == 403, f"{method} {url} -> {r.status_code}"
