"""pytest suite — merchant como PDS (hace ofertas en solicitudes ajenas).

El merchant puede ofrecer servicios igual que un pds: crea ofertas, negocia
(contraofertas) y termina firmando contratos como proveedor.
"""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig


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
    from app.models.user import User
    from app.models.wallet import Coin, TipoMoneda, Wallet

    u = User.query.filter_by(email=email).first()
    wallet = Wallet.query.filter_by(user_id=u.id).first()
    if wallet is None:
        wallet = Wallet(user_id=u.id, monedas_saldo=1000)
        db.session.add(wallet)
    else:
        wallet.monedas_saldo = 1000
    db.session.add(Coin(user_id=u.id, cantidad=1000, tipo=TipoMoneda.GANADA))
    db.session.commit()
    return _headers(client, email)


def _crear_solicitud(client, headers, titulo="Armar mueble"):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": titulo,
            "categoria": "carpinteria",
            "descripcion": "armar mueble",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )
    return resp.get_json()["id"]


# ---------------- merchant crea oferta en solicitud ajena ----------------
def test_merchant_crea_oferta_201(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, sol_h)

    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 150000, "mensaje": "lo hacemos nosotros"},
        headers=neg_h,
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["estado"] == "pendiente"
    assert d["solicitud_id"] == sid
    assert d["monto"] == 150000
    # El merchant queda registrado como proveedor de la negociación.
    assert d["pds_id"] == 2


def test_merchant_no_oferta_en_su_propia_solicitud(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, neg_h)
    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=neg_h,
    )
    assert resp.status_code == 403


def test_solicitante_sigue_sin_poder_ofertar(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    sid = _crear_solicitud(client, sol_h)
    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=sol_h,
    )
    assert resp.status_code == 403


# ---------------- merchant negocia ----------------
def test_merchant_contraoferta_y_cierre(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, sol_h)

    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 150000},
        headers=neg_h,
    ).get_json()["id"]

    # El solicitante contraoferta.
    r1 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 120000},
        headers=sol_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "contraoferta"

    # El merchant ajusta el precio (contra-contraoferta).
    r2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 130000},
        headers=neg_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["contra_monto"] == 130000

    # El solicitante acepta: se cierra el acuerdo.
    r3 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=sol_h,
    )
    assert r3.status_code == 200
    assert r3.get_json()["estado"] == "aceptada"


def test_merchant_acepta_valor_y_crea_contrato(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, sol_h)

    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 150000},
        headers=neg_h,
    ).get_json()["id"]

    # El solicitante acepta (el merchant ya aceptó al proponer).
    resp = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "aceptada"

    # El contrato tiene al merchant como proveedor.
    contratos = client.get("/api/v1/contracts/mine", headers=neg_h).get_json()
    assert len(contratos) == 1
    contrato = contratos[0]
    assert contrato["proveedor_id"] == 2  # el merchant
    assert contrato["solicitante_id"] == 1  # el solicitante dueño
    assert contrato["service_id"] == sid
    assert contrato["estado"] == "pendiente"
    assert contrato["monto"] == 150000


def test_merchant_firma_contrato_como_proveedor(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, sol_h)

    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 150000},
        headers=neg_h,
    ).get_json()["id"]
    client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=sol_h,
    )

    cid = client.get("/api/v1/contracts/mine", headers=neg_h).get_json()[0]["id"]

    # El merchant firma como proveedor.
    resp = client.patch(
        f"/api/v1/contracts/{cid}/estado",
        json={"estado": "aceptar", "firma": {"nombre": "Negocio"}},
        headers=neg_h,
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["firma_proveedor"] is True
    assert d["firma_solicitante"] is False

    # El solicitante firma: el contrato se activa.
    resp2 = client.patch(
        f"/api/v1/contracts/{cid}/estado",
        json={"estado": "aceptar", "firma": {"nombre": "Solicitante"}},
        headers=sol_h,
    )
    assert resp2.status_code == 200
    d2 = resp2.get_json()
    assert d2["firma_proveedor"] is True
    assert d2["firma_solicitante"] is True
    assert d2["estado"] == "en_progreso"


# ---------------- listings ----------------
def test_mis_ofertas_incluye_las_del_merchant(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, sol_h)
    client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 150000},
        headers=neg_h,
    )

    lista = client.get("/api/v1/mis-ofertas", headers=neg_h)
    assert lista.status_code == 200
    items = lista.get_json()
    assert len(items) == 1
    assert items[0]["solicitud_id"] == sid


def test_merchant_ve_las_ofertas_de_la_solicitud_where_participa(client):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    neg_h = _user(client, "neg@example.com", rol="merchant")
    sid = _crear_solicitud(client, sol_h)
    client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 150000},
        headers=neg_h,
    )
    resp = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=neg_h)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1
