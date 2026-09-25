"""Tests: perfil unificado — preferencias (todos los roles) y 2FA.

- GET/PUT /api/v1/users/me/preferences sin restricción de rol.
- GET/PUT /api/v1/auth/2fa persiste el toggle de verificación en dos pasos.
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


def _user(client, email="perfil@test.com", rol=RolUsuario.PDS):
    with client.application.app_context():
        u = User(email=email, nombre=email.split("@")[0], rol=rol, acepto_tyc=True)
        u.set_password("Test1234!")
        _db.session.add(u)
        _db.session.commit()
        token = create_access_token(identity=str(u.id))
        return u.id, {"Authorization": f"Bearer {token}"}


def test_preferencias_get_crea_por_defecto(client):
    """GET /users/me/preferences crea preferencias por defecto para cualquier rol."""
    uid, h = _user(client)
    r = client.get("/api/v1/users/me/preferences", headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert data["idioma"] == "es"
    assert data["tema"] == "system"
    assert data["push_enabled"] is True
    assert data["notif_nueva_solicitud"] is True


def test_preferencias_put_actualiza_idioma_tema(client):
    """PUT /users/me/preferences actualiza idioma, tema y notificaciones."""
    uid, h = _user(client, "prefs@test.com")
    r = client.put("/api/v1/users/me/preferences", headers=h, json={
        "idioma": "en",
        "tema": "dark",
        "push_enabled": False,
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data["idioma"] == "en"
    assert data["tema"] == "dark"
    assert data["push_enabled"] is False


def test_preferencias_put_rechaza_valores_invalidos(client):
    """422 si idioma/tema salen de los valores permitidos."""
    uid, h = _user(client, "prefs2@test.com")
    r = client.put("/api/v1/users/me/preferences", headers=h, json={"idioma": "fr"})
    assert r.status_code == 422


def test_preferencias_sin_rol_merchant(client):
    """El endpoint funciona para PDS y solicitante (no restringido a merchant)."""
    for rol in [RolUsuario.PDS, RolUsuario.SOLICITANTE, RolUsuario.MERCHANT]:
        uid, h = _user(client, f"rol-{rol.value}@test.com", rol=rol)
        r = client.get("/api/v1/users/me/preferences", headers=h)
        assert r.status_code == 200, f"rol {rol.value} falló"


def test_2fa_get_default_false(client):
    """GET /auth/2fa → false por defecto."""
    uid, h = _user(client, "2fa@test.com")
    r = client.get("/api/v1/auth/2fa", headers=h)
    assert r.status_code == 200
    assert r.get_json() == {"enabled": False}


def test_2fa_toggle_persiste(client):
    """PUT /auth/2fa activa y desactiva; GET devuelve el estado persistido."""
    uid, h = _user(client, "2fa2@test.com")

    r = client.put("/api/v1/auth/2fa", headers=h, json={"enabled": True})
    assert r.status_code == 200
    assert r.get_json() == {"enabled": True}

    r = client.get("/api/v1/auth/2fa", headers=h)
    assert r.get_json() == {"enabled": True}

    r = client.put("/api/v1/auth/2fa", headers=h, json={"enabled": False})
    assert r.get_json() == {"enabled": False}


def test_2fa_requiere_body(client):
    """422 si falta el campo enabled."""
    uid, h = _user(client, "2fa3@test.com")
    r = client.put("/api/v1/auth/2fa", headers=h, json={})
    assert r.status_code == 422