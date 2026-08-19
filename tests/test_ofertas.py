"""pytest suite — ofertas (negociación pds/solicitante).

Convenciones del repo: pds = rol 'trabajador', solicitante = rol 'empleador'
(dueño vía Solicitud.solicitante_id). El rename conceptual pds/solicitante
aún no está reflejado en el enum RolUsuario.
"""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.order import Order


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


def _register(client, email, rol="trabajador", password="secret123"):
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


def _user(client, email, rol="trabajador"):
    _register(client, email=email, rol=rol)
    return _headers(client, email)


def _crear_solicitud(client, headers):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "categoria": "carpinteria",
            "descripcion": "armar mueble",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )
    return resp.get_json()["id"]


# ---------------- pds crea oferta en solicitud ajena ----------------
def test_pds_crea_oferta_ajena_201(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    pds_h = _user(client, "pds@example.com", rol="trabajador")
    sid = _crear_solicitud(client, emp_h)
    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000, "mensaje": "lo hago"},
        headers=pds_h,
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["estado"] == "pendiente"
    assert d["pds_id"] == 2  # pds es el 2º usuario registrado
    assert d["solicitud_id"] == sid


# ---------------- pds NO oferta en su propia solicitud ----------------
def test_pds_no_oferta_propia_403(client):
    pds_h = _user(client, "pds@example.com", rol="trabajador")
    sid = _crear_solicitud(client, pds_h)  # pds es dueño
    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    )
    assert resp.status_code == 403


# ---------------- solicitante lista ofertas de su solicitud ----------------
def test_solicitante_lista_ofertas_200(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    pds_h = _user(client, "pds@example.com", rol="trabajador")
    sid = _crear_solicitud(client, emp_h)
    client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    )
    resp = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=emp_h)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


# ---------------- no participante lista ofertas -> 403 ----------------
def test_no_participante_lista_403(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    pds_h = _user(client, "pds@example.com", rol="trabajador")
    outsider_h = _user(client, "out@example.com", rol="empleador")
    sid = _crear_solicitud(client, emp_h)
    client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    )
    resp = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=outsider_h)
    assert resp.status_code == 403


# ---------------- solicitante acepta oferta ----------------
def test_solicitante_acepta_crea_order_y_rechaza_otras(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    pds1_h = _user(client, "pds1@example.com", rol="trabajador")
    pds2_h = _user(client, "pds2@example.com", rol="trabajador")
    sid = _crear_solicitud(client, emp_h)

    o1 = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds1_h,
    ).get_json()
    o2 = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 90000},
        headers=pds2_h,
    ).get_json()

    resp = client.post(
        f"/api/v1/ofertas/{o1['id']}/responder",
        json={"accion": "aceptar"},
        headers=emp_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "aceptada"

    # Order creada
    orders = client.get("/api/v1/orders/mine", headers=emp_h).get_json()
    assert len(orders) == 1
    assert orders[0]["proveedor_id"] == o1["pds_id"]
    assert orders[0]["solicitante_id"] == 1
    assert orders[0]["service_id"] == sid
    assert orders[0]["estado"] == "pendiente"

    # Solicitud queda 'asignada'
    svc = client.get(f"/api/v1/solicitudes/{sid}").get_json()
    assert svc["estado"] == "asignada"

    # La otra oferta queda 'rechazada'
    lista = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=emp_h).get_json()
    estados = {o["id"]: o["estado"] for o in lista}
    assert estados[o1["id"]] == "aceptada"
    assert estados[o2["id"]] == "rechazada"


# ---------------- contraofertar + pds acepta contraoferta ----------------
def test_contraofertar_y_pds_acepta_contraoferta(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    pds_h = _user(client, "pds@example.com", rol="trabajador")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]

    # solicitante contraoferta
    r1 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 95000, "contra_mensaje": "bajo"},
        headers=emp_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "contraoferta"
    assert r1.get_json()["contra_monto"] == 95000

    # pds acepta contraoferta
    r2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar_contraoferta"},
        headers=pds_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["estado"] == "aceptada"

    orders = client.get("/api/v1/orders/mine", headers=emp_h).get_json()
    assert len(orders) == 1


# ---------------- pds no puede aceptar (solo solicitante) ----------------
def test_pds_no_acepta_403(client):
    emp_h = _user(client, "emp@example.com", rol="empleador")
    pds_h = _user(client, "pds@example.com", rol="trabajador")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]
    resp = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=pds_h,
    )
    assert resp.status_code == 403
