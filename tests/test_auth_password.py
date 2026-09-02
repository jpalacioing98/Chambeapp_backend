"""Tests: recuperación de contraseña (P0)."""

import pytest
from app import create_app
from app.extensions import db as _db, bcrypt
from app.models.user import User, RolUsuario


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


def _create_user(client, email="test@test.com", password="Test1234!"):
    """Helper para crear un usuario."""
    with client.application.app_context():
        user = User(
            email=email,
            nombre=email.split("@")[0],
            rol=RolUsuario.SOLICITANTE,
            acepto_tyc=True,
        )
        user.set_password(password)
        _db.session.add(user)
        _db.session.commit()
        return user.id


def test_forgot_password_returns_message(client):
    """P0: Forgot password retorna mensaje genérico."""
    _create_user(client, "forgot@test.com")
    
    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "forgot@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "message" in data
    assert "email" in data["message"].lower() or "reseteo" in data["message"].lower()


def test_forgot_password_nonexistent_email(client):
    """P0: Forgot password no revela si el email existe."""
    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "noexiste@test.com"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    # No debe revelar que el email no existe
    assert "no existe" not in data["message"].lower()


def test_reset_password_invalid_token(client):
    """P0: Reset password rechaza token inválido."""
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "token_invalido",
            "new_password": "Nueva1234!",
        },
    )
    assert resp.status_code == 400


def test_reset_password_valid_token(client):
    """P0: Reset password funciona con token válido."""
    from app.routes.auth_password import _generate_reset_token
    
    user_id = _create_user(client, "reset@test.com")
    token = _generate_reset_token(user_id)
    
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": token,
            "new_password": "Nueva1234!",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "message" in data
    
    # Verificar que la contraseña cambió
    with client.application.app_context():
        user = _db.session.get(User, user_id)
        assert bcrypt.check_password_hash(user.password_hash, "Nueva1234!")


def test_reset_password_expired_token(client):
    """P0: Reset password rechaza token expirado."""
    from app.routes.auth_password import _reset_tokens
    from datetime import datetime, timedelta, timezone
    
    user_id = _create_user(client, "expired@test.com")
    token = "expired_token"
    _reset_tokens[token] = {
        "user_id": user_id,
        "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),  # Expirado
        "used": False,
    }
    
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": token,
            "new_password": "Nueva1234!",
        },
    )
    assert resp.status_code == 400


def test_change_password_requires_auth(client):
    """P0: Change password requiere autenticación."""
    resp = client.post(
        "/api/v1/auth/change-password",
        json={
            "new_password": "Nueva1234!",
        },
    )
    assert resp.status_code in (401, 422)  # JWT required
