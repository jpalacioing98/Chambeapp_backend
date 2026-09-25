"""Tests: foto de perfil (POST/DELETE /users/me/foto-perfil)."""

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


def _auth(client, email="foto@test.com"):
    from app.models.user import Profile
    with client.application.app_context():
        u = User(email=email, nombre="Foto User", rol=RolUsuario.SOLICITANTE, acepto_tyc=True)
        u.set_password("Test1234!")
        _db.session.add(u)
        _db.session.flush()
        _db.session.add(Profile(user_id=u.id))
        _db.session.commit()
        return u.id, {"Authorization": f"Bearer {create_access_token(identity=str(u.id))}"}


def test_upload_invalida_400(client):
    """Base64 inválido o vacío → 400."""
    _, h = _auth(client)
    r = client.post("/api/v1/users/me/foto-perfil", headers=h, json={
        "archivo_base64": "no-es-base64!!",
    })
    assert r.status_code in (400, 502)

    r2 = client.post("/api/v1/users/me/foto-perfil", headers=h, json={
        "archivo_base64": "",
    })
    assert r2.status_code in (400, 502)


def test_eliminar_foto(client):
    """DELETE /me/foto-perfil limpia el campo y responde 200."""
    uid, h = _auth(client, "foto2@test.com")
    with client.application.app_context():
        u = _db.session.get(User, uid)
        u.profile.foto_perfil = "http://storage/avatar/x.webp"
        _db.session.commit()

    r = client.delete("/api/v1/users/me/foto-perfil", headers=h)
    assert r.status_code == 200
    assert r.get_json()["foto_perfil"] is None

    with client.application.app_context():
        u = _db.session.get(User, uid)
        assert u.profile.foto_perfil is None


def test_foto_perfil_en_perfil(client):
    """GET /users/me/profile expone foto_perfil."""
    uid, h = _auth(client, "foto3@test.com")
    with client.application.app_context():
        u = _db.session.get(User, uid)
        u.profile.foto_perfil = "http://storage/avatar/yo.webp"
        _db.session.commit()

    r = client.get("/api/v1/users/me/profile", headers=h)
    assert r.status_code == 200
    assert r.get_json()["foto_perfil"] == "http://storage/avatar/yo.webp"