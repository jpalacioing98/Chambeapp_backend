"""pytest suite — integracion de pago con Nequi (RF-08 reemplazo pasarela)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.contract import Contract, EstadoContrato
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.payment import Payment, EstadoPago
from app.models.user import User, RolUsuario


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


def _crear_servicio(client, headers):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={"titulo": "Reparar grifo", "categoria": "plomeria", "descripcion": "arreglar", "ubicacion": "Valledupar"},
        headers=headers,
    )
    return resp.get_json()["id"]


def _contrato_completado(client, emp_h, tr_h, tr_id):
    """Crea servicio, contrato, acepta y completa (con confirmación dual). Devuelve contract_id."""
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": tr_id},
        headers=emp_h,
    ).get_json()["id"]
    client.patch(
        f"/api/v1/contracts/{oid}/estado", json={"estado": "aceptar"}, headers=tr_h
    )
    client.patch(
        f"/api/v1/contracts/{oid}/estado", json={"estado": "completar"}, headers=tr_h
    )
    # RF-23: Confirmación dual - solicitante confirma
    client.patch(
        f"/api/v1/contracts/{oid}/estado", json={"estado": "confirmar"}, headers=emp_h
    )
    return oid


def test_crear_pago_nequi(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    resp = client.post(
        "/api/v1/payments/",
        json={"contract_id": oid, "monto": 100000, "pasarela": "nequi"},
        headers=emp_h,
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["pasarela"] == "nequi"
    assert d["referencia_pasarela"] is not None
    assert d["referencia_pasarela"].startswith("NEQ-")


def test_crear_pago_sin_pasarela_default_nequi(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    resp = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["pasarela"] == "nequi"
    assert d["referencia_pasarela"].startswith("NEQ-")


def test_get_nequi_info(client):
    resp = client.get("/api/v1/payments/nequi")
    assert resp.status_code == 200
    d = resp.get_json()
    assert "numero" in d
    assert "titular" in d
    assert d["numero"] == "3000000000"
    assert d["titular"] == "ChambeApp"
