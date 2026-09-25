"""Tests: métodos de pago vinculados (MetodoPago).

La billetera virtual creada por el sistema es SIEMPRE el primer método;
los usuarios vinculan cuentas bancarias (banco libre + número de cuenta).
"""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User, RolUsuario
from flask_jwt_extended import create_access_token


@pytest.fixture(scope="module")
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _user(client, email="pagos@test.com", rol=RolUsuario.SOLICITANTE):
    with client.application.app_context():
        u = User(email=email, nombre=email.split("@")[0], rol=rol, acepto_tyc=True)
        u.set_password("Test1234!")
        _db.session.add(u)
        _db.session.commit()
        token = create_access_token(identity=str(u.id))
        return u.id, {"Authorization": f"Bearer {token}"}


def test_billetera_es_la_primera_metodo(client):
    """GET /metodos-pago crea y lista la billetera virtual primero."""
    uid, h = _user(client)
    r = client.get("/api/v1/metodos-pago", headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["tipo"] == "billetera"
    assert data[0]["es_principal"] is True
    assert "saldo" in data[0]


def test_vincular_cuenta_bancaria(client):
    """POST /metodos-pago vincula banco libre + número de cuenta."""
    uid, h = _user(client, "pagos2@test.com")
    r = client.post("/api/v1/metodos-pago", headers=h, json={
        "tipo": "banco", "banco": "Bancolombia", "numero_cuenta": "1234567890",
    })
    assert r.status_code == 201
    m = r.get_json()
    assert m["tipo"] == "banco"
    assert m["banco"] == "Bancolombia"
    assert m["numero_cuenta"] == "1234567890"
    assert m["es_principal"] is True  # primer vinculado → principal

    lista = client.get("/api/v1/metodos-pago", headers=h).get_json()
    assert [x["tipo"] for x in lista] == ["billetera", "banco"]


def test_banco_es_texto_libre(client):
    """El input del banco acepta cualquier texto (ej: 'Nequi', 'RappiPay')."""
    uid, h = _user(client, "pagos3@test.com")
    for banco in ["Nequi", "RappiPay", "Banco de Bogotá S.A."]:
        r = client.post("/api/v1/metodos-pago", headers=h, json={
            "tipo": "banco", "banco": banco, "numero_cuenta": f"000{len(banco)}",
        })
        assert r.status_code == 201
        assert r.get_json()["banco"] == banco


def test_cambiar_principal(client):
    """PATCH /metodos-pago/<id>/principal marca uno y desmarca el resto."""
    uid, h = _user(client, "pagos4@test.com")
    m1 = client.post("/api/v1/metodos-pago", headers=h, json={
        "tipo": "banco", "banco": "Nequi", "numero_cuenta": "300111",
    }).get_json()
    m2 = client.post("/api/v1/metodos-pago", headers=h, json={
        "tipo": "banco", "banco": "Daviplata", "numero_cuenta": "300222",
    }).get_json()

    r = client.patch(f"/api/v1/metodos-pago/{m2['id']}/principal", headers=h)
    assert r.status_code == 200
    assert r.get_json()["es_principal"] is True

    lista = client.get("/api/v1/metodos-pago", headers=h).get_json()
    principales = [m for m in lista if m["es_principal"]]
    assert len(principales) == 1
    assert principales[0]["id"] == m2["id"]


def test_eliminar_metodo_y_reasignar_principal(client):
    """DELETE /metodos-pago/<id> desvincula; si era principal se reasigna."""
    uid, h = _user(client, "pagos5@test.com")
    m1 = client.post("/api/v1/metodos-pago", headers=h, json={
        "tipo": "banco", "banco": "Nequi", "numero_cuenta": "300111",
    }).get_json()

    r = client.delete(f"/api/v1/metodos-pago/{m1['id']}", headers=h)
    assert r.status_code == 200

    lista = client.get("/api/v1/metodos-pago", headers=h).get_json()
    assert [m["tipo"] for m in lista] == ["billetera"]
    assert lista[0]["es_principal"] is True


def test_billetera_no_se_elimina(client):
    """DELETE sobre la billetera del sistema → 400."""
    uid, h = _user(client, "pagos6@test.com")
    lista = client.get("/api/v1/metodos-pago", headers=h).get_json()
    bid = lista[0]["id"]
    r = client.delete(f"/api/v1/metodos-pago/{bid}", headers=h)
    assert r.status_code == 400


def test_solo_metodos_propios(client):
    """DELETE de un método ajeno → 403."""
    uid1, h1 = _user(client, "pagos7a@test.com")
    uid2, h2 = _user(client, "pagos7b@test.com")
    m = client.post("/api/v1/metodos-pago", headers=h1, json={
        "tipo": "banco", "banco": "Nequi", "numero_cuenta": "300333",
    }).get_json()
    r = client.delete(f"/api/v1/metodos-pago/{m['id']}", headers=h2)
    assert r.status_code == 403