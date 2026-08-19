"""pytest suite — auth/usuarios (RF-01, RF-17)."""

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


def _register(client, **overrides):
    payload = {
        "email": "test@example.com",
        "password": "secret123",
        "rol": "pds",
        "acepto_tyc": True,
        "ip": "127.0.0.1",
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def test_register_success(client):
    resp = _register(client)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert data["rol"] == "pds"
    assert data["acepto_tyc"] is True
    assert data["profile"] is not None


def test_register_requires_tyc(client):
    resp = _register(client, acepto_tyc=False)
    assert resp.status_code == 400
    assert "Términos" in resp.get_json()["message"]


def test_register_duplicate_email(client):
    _register(client)
    resp = _register(client)
    assert resp.status_code == 409


def test_login_success(client):
    _register(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client):
    _register(client)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_refresh(client):
    _register(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    ).get_json()
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {login['refresh_token']}"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()


def test_me_without_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_token(client):
    _register(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    ).get_json()
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "test@example.com"
