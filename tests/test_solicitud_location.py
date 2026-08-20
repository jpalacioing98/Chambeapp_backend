"""pytest suite — ubicación geográfica en Solicitud (gating de coordenadas).

RF-04 (geo): latitud/longitud/direccion solo se exponen al dueño solicitante
o al pds premiado (Contract). En listados nunca se filtra la coordenada exacta.
"""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.contract import Contract


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


def _crear_solicitud(client, headers, **extra):
    payload = {
        "titulo": "Reparar grifo",
        "categoria": "plomeria",
        "descripcion": "arreglar",
        "ubicacion": "Valledupar",
    }
    payload.update(extra)
    return client.post("/api/v1/solicitudes/", json=payload, headers=headers)


# ---------------- creación con ubicación ----------------
def test_solicitante_crea_con_ubicacion(client):
    h = _user(client, "emp@example.com", rol="solicitante")
    resp = _crear_solicitud(
        client, h, latitud=10.46, longitud=-73.25, direccion="Calle 1"
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["latitud"] == 10.46
    assert d["longitud"] == -73.25
    assert d["direccion"] == "Calle 1"
    sid = d["id"]
    # detalle como dueño => coords presentes
    det = client.get(f"/api/v1/solicitudes/{sid}", headers=h).get_json()
    assert det["latitud"] == 10.46
    assert det["longitud"] == -73.25
    assert det["direccion"] == "Calle 1"


# ---------------- detalle sin auth => coords None ----------------
def test_detalle_sin_auth_strips_coords(client):
    h = _user(client, "emp@example.com", rol="solicitante")
    resp = _crear_solicitud(
        client, h, latitud=10.46, longitud=-73.25, direccion="Calle 1"
    )
    sid = resp.get_json()["id"]
    det = client.get(f"/api/v1/solicitudes/{sid}").get_json()
    assert det["latitud"] is None
    assert det["longitud"] is None
    assert det["direccion"] is None


# ---------------- detalle pds no relacionado => coords None ----------------
def test_detalle_pds_no_relacionado_strips_coords(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    resp = _crear_solicitud(
        client, emp_h, latitud=10.46, longitud=-73.25, direccion="Calle 1"
    )
    sid = resp.get_json()["id"]
    det = client.get(f"/api/v1/solicitudes/{sid}", headers=pds_h).get_json()
    assert det["latitud"] is None
    assert det["longitud"] is None
    assert det["direccion"] is None


# ---------------- detalle pds premiado (Contract) => coords ----------------
def test_detalle_pds_premiado_ve_coords(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    resp = _crear_solicitud(
        client, emp_h, latitud=10.46, longitud=-73.25, direccion="Calle 1"
    )
    sid = resp.get_json()["id"]
    # pds id = 2 (empleador=1). Crear Contract premiado en db.
    contract = Contract(
        service_id=sid, proveedor_id=2, solicitante_id=1, estado="pendiente"
    )
    db.session.add(contract)
    db.session.commit()
    det = client.get(f"/api/v1/solicitudes/{sid}", headers=pds_h).get_json()
    assert det["latitud"] == 10.46
    assert det["longitud"] == -73.25
    assert det["direccion"] == "Calle 1"


# ---------------- lista nunca expone coordenadas ----------------
def test_lista_strips_coords(client):
    h = _user(client, "emp@example.com", rol="solicitante")
    _crear_solicitud(
        client, h, latitud=10.46, longitud=-73.25, direccion="Calle 1"
    )
    _crear_solicitud(
        client, h, titulo="Otra", latitud=11.0, longitud=-74.0, direccion="Calle 2"
    )
    items = client.get("/api/v1/solicitudes/").get_json()
    assert len(items) == 2
    for it in items:
        assert "latitud" not in it
        assert "longitud" not in it
        assert "direccion" not in it
