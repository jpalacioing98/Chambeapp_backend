"""pytest suite — notificaciones (RF-10: centro de notificaciones + formalización)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.user import User
from app.models.contract import Contract, EstadoContrato
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.notification import Notification


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


def _register(client, email, rol="pds", password="secret123"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )


def _login(client, email, password="secret123"):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).get_json()


def _headers(client, email, password="secret123"):
    return {"Authorization": f"Bearer {_login(client, email, password)['access_token']}"}


def _user(client, email, rol="pds"):
    _register(client, email=email, rol=rol)
    return _headers(client, email)


def _uid(client, email):
    with client.application.app_context():
        return User.query.filter_by(email=email).first().id


def _crear_servicio(client, headers):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": "Reparar grifo",
            "categoria": "plomeria",
            "descripcion": "arreglar",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )
    return resp.get_json()["id"]


def _crear_y_completar_contrato(client):
    """Crea servicio+solicitante, pds, contrato y lo lleva a COMPLETADO.
    Retorna (emp_h, tr_h, oid, sid)."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = (
        client.post(
            "/api/v1/contracts/",
            json={"service_id": sid, "proveedor_id": 2},
            headers=emp_h,
        )
        .get_json()["id"]
    )
    client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=tr_h,
    )
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "completar"},
        headers=tr_h,
    )
    assert resp.status_code == 200
    return emp_h, tr_h, oid, sid


# ---------------- CRUD notificaciones ----------------
def test_listar_y_conteo(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    uid = _uid(client, "emp@example.com")
    with client.application.app_context():
        db.session.add(Notification(user_id=uid, tipo="sistema", mensaje="hola"))
        db.session.commit()
    resp = client.get("/api/v1/notifications/", headers=emp_h)
    assert resp.status_code == 200
    notifs = resp.get_json()
    assert len(notifs) == 1
    assert notifs[0]["tipo"] == "sistema"
    assert notifs[0]["leida"] is False

    resp2 = client.get("/api/v1/notifications/no-leidas", headers=emp_h)
    assert resp2.status_code == 200
    assert resp2.get_json()["count"] >= 1


def test_marcar_leida_baja_conteo(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    uid = _uid(client, "emp@example.com")
    with client.application.app_context():
        n = Notification(user_id=uid, tipo="sistema", mensaje="hola")
        db.session.add(n)
        db.session.commit()
        nid = n.id
    r = client.post(f"/api/v1/notifications/{nid}/marcar-leida", headers=emp_h)
    assert r.status_code == 200
    assert r.get_json()["leida"] is True
    resp = client.get("/api/v1/notifications/no-leidas", headers=emp_h)
    assert resp.get_json()["count"] == 0


def test_marcar_todas_leidas(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    uid = _uid(client, "emp@example.com")
    with client.application.app_context():
        for i in range(3):
            db.session.add(Notification(user_id=uid, tipo="sistema", mensaje=f"m{i}"))
        db.session.commit()
    r = client.post("/api/v1/notifications/marcar-todas-leidas", headers=emp_h)
    assert r.status_code == 200
    resp = client.get("/api/v1/notifications/no-leidas", headers=emp_h)
    assert resp.get_json()["count"] == 0


def test_marcar_leida_ajena_404(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    other_h = _user(client, "other@example.com", rol="solicitante")
    uid = _uid(client, "emp@example.com")
    with client.application.app_context():
        n = Notification(user_id=uid, tipo="sistema", mensaje="hola")
        db.session.add(n)
        db.session.commit()
        nid = n.id
    r = client.post(f"/api/v1/notifications/{nid}/marcar-leida", headers=other_h)
    assert r.status_code == 404


# ---------------- Disparador formalización ----------------
def test_formalizacion_al_completar(client):
    emp_h, tr_h, oid, sid = _crear_y_completar_contrato(client)
    resp_emp = client.get("/api/v1/notifications/", headers=emp_h).get_json()
    resp_tr = client.get("/api/v1/notifications/", headers=tr_h).get_json()
    assert any(n["tipo"] == "formalizacion" for n in resp_emp)
    assert any(n["tipo"] == "formalizacion" for n in resp_tr)

    fn = next(n for n in resp_emp if n["tipo"] == "formalizacion")
    assert fn["titulo"] == "Solicitud completada: considera formalizar"
    assert "formalización" in fn["mensaje"]
    assert fn["datos"]["contract_id"] == oid
    assert fn["datos"]["service_id"] == sid


def test_formalizacion_idempotente(client):
    emp_h, tr_h, oid, sid = _crear_y_completar_contrato(client)
    resp_emp = client.get("/api/v1/notifications/", headers=emp_h).get_json()
    form = [n for n in resp_emp if n["tipo"] == "formalizacion"]
    assert len(form) == 1
