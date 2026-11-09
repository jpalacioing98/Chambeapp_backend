"""pytest suite - elegibilidad de chambas por habilidades del PDS.

`GET /solicitudes/?elegibles=1` filtra las chambas publicadas a las
categorias que el PDS autenticado declaro en su perfil (categorias +
habilidades). Sin habilidades registradas no se filtra.
"""

import pytest

from app import create_app
from app.extensions import db
from app.models.user import User


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


def _register(client, email, rol):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )


def _headers(client, email):
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secret123"},
    ).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _crear_solicitud(client, headers, categoria):
    return client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": f"Chamba de {categoria}",
            "categoria": categoria,
            "descripcion": "trabajo de prueba",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )


def _set_habilidades(app, email, habilidades):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.profile.habilidades = habilidades
        db.session.commit()


def test_elegibles_filtra_por_habilidades_del_pds(app, client):
    _register(client, "sol@example.com", "solicitante")
    h_sol = _headers(client, "sol@example.com")
    _crear_solicitud(client, h_sol, "plomeria")
    _crear_solicitud(client, h_sol, "electricidad")

    _register(client, "pds@example.com", "pds")
    _set_habilidades(app, "pds@example.com", ["plomeria"])
    h_pds = _headers(client, "pds@example.com")

    resp = client.get("/api/v1/solicitudes/?elegibles=1&page=1&per_page=10", headers=h_pds)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert [s["categoria"] for s in data["items"]] == ["plomeria"]


def test_elegibles_sin_habilidades_no_filtra(app, client):
    _register(client, "sol2@example.com", "solicitante")
    h_sol = _headers(client, "sol2@example.com")
    _crear_solicitud(client, h_sol, "plomeria")
    _crear_solicitud(client, h_sol, "electricidad")

    _register(client, "pds2@example.com", "pds")
    h_pds = _headers(client, "pds2@example.com")

    resp = client.get("/api/v1/solicitudes/?elegibles=1&page=1&per_page=10", headers=h_pds)
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 2


def test_elegibles_sin_token_es_publico(client):
    _register(client, "sol3@example.com", "solicitante")
    h_sol = _headers(client, "sol3@example.com")
    _crear_solicitud(client, h_sol, "plomeria")

    resp = client.get("/api/v1/solicitudes/?elegibles=1&page=1&per_page=10")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 1


def test_normalizar_categoria():
    from app.services.categorias import normalizar_categoria

    assert normalizar_categoria(" Construcción ") == "construccion"
    assert normalizar_categoria("PLOMERÍA") == "plomeria"
    assert normalizar_categoria("  fontanería  ") == "fontaneria"
    assert normalizar_categoria(None) == ""


def test_elegibles_normaliza_acentos_y_mayusculas(app, client):
    _register(client, "sol4@example.com", "solicitante")
    h_sol = _headers(client, "sol4@example.com")
    _crear_solicitud(client, h_sol, "Plomería")
    _crear_solicitud(client, h_sol, "ELECTRICIDAD")

    _register(client, "pds4@example.com", "pds")
    _set_habilidades(app, "pds4@example.com", [" plomeria "])
    h_pds = _headers(client, "pds4@example.com")

    resp = client.get(
        "/api/v1/solicitudes/?elegibles=1&page=1&per_page=10", headers=h_pds
    )
    data = resp.get_json()
    assert data["total"] == 1
    assert data["items"][0]["categoria"] == "Plomería"

    _set_habilidades(app, "pds4@example.com", ["PLOMERÍA", "electricidad"])
    resp = client.get(
        "/api/v1/solicitudes/?elegibles=1&page=1&per_page=10", headers=h_pds
    )
    assert resp.get_json()["total"] == 2
