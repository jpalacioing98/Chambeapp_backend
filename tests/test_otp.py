"""Tests: verificación de celular por OTP (SMS) en el registro."""

import pytest
from app import create_app
from app.extensions import db as _db


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


def test_otp_send_returns_dev_code_in_testing(client):
    """En testing, el envío retorna dev_code para completar el flujo."""
    resp = client.post(
        "/api/v1/auth/otp/send",
        json={"telefono": "300 123 4567"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "message" in data
    assert "dev_code" in data
    assert len(data["dev_code"]) == 6


def test_otp_send_rejects_invalid_phone(client):
    """Un celular inválido es rechazado."""
    resp = client.post(
        "/api/v1/auth/otp/send",
        json={"telefono": "123"},
    )
    assert resp.status_code == 400


def test_otp_verify_success(client):
    """El código correcto verifica el celular."""
    send = client.post(
        "/api/v1/auth/otp/send",
        json={"telefono": "3001234567"},
    ).get_json()

    resp = client.post(
        "/api/v1/auth/otp/verify",
        json={"telefono": "3001234567", "code": send["dev_code"]},
    )
    assert resp.status_code == 200
    assert "verificado" in resp.get_json()["message"].lower()


def test_otp_verify_wrong_code(client):
    """Un código incorrecto es rechazado."""
    client.post(
        "/api/v1/auth/otp/send",
        json={"telefono": "3001234567"},
    )

    resp = client.post(
        "/api/v1/auth/otp/verify",
        json={"telefono": "3001234567", "code": "000000"},
    )
    assert resp.status_code == 400


def test_otp_verify_no_active_code(client):
    """Verificar sin haber enviado un código falla."""
    resp = client.post(
        "/api/v1/auth/otp/verify",
        json={"telefono": "3009999999", "code": "123456"},
    )
    assert resp.status_code == 400


def test_otp_single_use(client):
    """El código es de un solo uso: una segunda verificación falla."""
    send = client.post(
        "/api/v1/auth/otp/send",
        json={"telefono": "3001234567"},
    ).get_json()

    first = client.post(
        "/api/v1/auth/otp/verify",
        json={"telefono": "3001234567", "code": send["dev_code"]},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/otp/verify",
        json={"telefono": "3001234567", "code": send["dev_code"]},
    )
    assert second.status_code == 400
