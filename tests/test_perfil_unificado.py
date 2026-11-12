"""Tests: perfil unificado — preferencias (todos los roles) y 2FA.

- GET/PUT /api/v1/users/me/preferences sin restricción de rol.
- 2FA: SMS, app autenticadora (TOTP) y códigos de recuperación.
"""

import pyotp
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


def _set_phone(client, uid, telefono="3001234567"):
    with client.application.app_context():
        u = _db.session.get(User, uid)
        u.telefono = telefono
        _db.session.commit()


def _login(client, email, password="Test1234!"):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).get_json()


def test_2fa_get_default(client):
    """GET /auth/2fa → desactivado, método SMS por defecto."""
    uid, h = _user(client, "2fa@test.com")
    r = client.get("/api/v1/auth/2fa", headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert data["enabled"] is False
    assert data["method"] == "sms"
    assert data["available_methods"] == ["sms", "totp"]
    assert data["has_phone"] is False
    assert data["recovery_codes_remaining"] == 0


def test_2fa_sms_activar_login_y_desactivar(client):
    """Flujo SMS completo: activar → login con código → desactivar."""
    uid, h = _user(client, "2fa-sms@test.com")
    _set_phone(client, uid)

    send = client.post("/api/v1/auth/2fa/sms/send", headers=h)
    assert send.status_code == 200
    code = send.get_json()["dev_code"]

    enable = client.post(
        "/api/v1/auth/2fa/enable",
        headers=h,
        json={"method": "sms", "code": code},
    )
    assert enable.status_code == 200, enable.get_json()
    body = enable.get_json()
    assert body["enabled"] is True
    assert body["method"] == "sms"
    assert len(body["recovery_codes"]) == 10

    status = client.get("/api/v1/auth/2fa", headers=h).get_json()
    assert status["enabled"] is True
    assert status["recovery_codes_remaining"] == 10

    login = _login(client, "2fa-sms@test.com")
    assert login["requires_2fa"] is True
    assert login["method"] == "sms"
    assert login["masked_phone"].endswith("567")

    verify = client.post(
        "/api/v1/auth/2fa/verify",
        json={"email": "2fa-sms@test.com", "code": login["dev_code"]},
    )
    assert verify.status_code == 200
    assert "access_token" in verify.get_json()

    # Desactivar exige un código SMS vigente (se pide uno nuevo) + password.
    nuevo = client.post("/api/v1/auth/2fa/sms/send", headers=h).get_json()
    off = client.post(
        "/api/v1/auth/2fa/disable",
        headers=h,
        json={"password": "Test1234!", "code": nuevo["dev_code"]},
    )
    assert off.status_code == 200, off.get_json()
    assert off.get_json()["enabled"] is False


def test_2fa_totp_activar_login_y_recovery(client):
    """Flujo TOTP: setup + enable; login con app y con código de recuperación."""
    uid, h = _user(client, "2fa-totp@test.com")

    setup = client.post("/api/v1/auth/2fa/setup/totp", headers=h)
    assert setup.status_code == 200
    data = setup.get_json()
    assert data["secret"]
    assert data["otpauth_uri"].startswith("otpauth://totp/")
    assert data["qr_svg"] and "<svg" in data["qr_svg"]

    codigo = pyotp.TOTP(data["secret"]).now()
    enable = client.post(
        "/api/v1/auth/2fa/enable",
        headers=h,
        json={"method": "totp", "code": codigo},
    )
    assert enable.status_code == 200, enable.get_json()
    codes = enable.get_json()["recovery_codes"]
    assert len(codes) == 10

    status = client.get("/api/v1/auth/2fa", headers=h).get_json()
    assert status["enabled"] is True
    assert status["method"] == "totp"
    assert status["has_totp"] is True

    # Login con TOTP: no se envía SMS ni dev_code.
    login = _login(client, "2fa-totp@test.com")
    assert login["requires_2fa"] is True
    assert login["method"] == "totp"
    assert "dev_code" not in login

    verify = client.post(
        "/api/v1/auth/2fa/verify",
        json={
            "email": "2fa-totp@test.com",
            "code": pyotp.TOTP(data["secret"]).now(),
        },
    )
    assert verify.status_code == 200

    # Código de recuperación: válido una sola vez.
    login2 = _login(client, "2fa-totp@test.com")
    assert login2["requires_2fa"] is True
    ok = client.post(
        "/api/v1/auth/2fa/verify",
        json={"email": "2fa-totp@test.com", "code": codes[0]},
    )
    assert ok.status_code == 200
    repetido = client.post(
        "/api/v1/auth/2fa/verify",
        json={"email": "2fa-totp@test.com", "code": codes[0]},
    )
    assert repetido.status_code == 400

    restantes = client.get("/api/v1/auth/2fa", headers=h).get_json()
    assert restantes["recovery_codes_remaining"] == 9


def test_2fa_regenerar_recovery_codes_invalida_los_anteriores(client):
    uid, h = _user(client, "2fa-recovery@test.com")
    setup = client.post("/api/v1/auth/2fa/setup/totp", headers=h).get_json()
    secret = setup["secret"]
    enable = client.post(
        "/api/v1/auth/2fa/enable",
        headers=h,
        json={"method": "totp", "code": pyotp.TOTP(secret).now()},
    ).get_json()
    anterior = enable["recovery_codes"][0]

    nuevo = client.post(
        "/api/v1/auth/2fa/recovery-codes",
        headers=h,
        json={"password": "Test1234!", "code": pyotp.TOTP(secret).now()},
    )
    assert nuevo.status_code == 200, nuevo.get_json()
    codigos = nuevo.get_json()["recovery_codes"]
    assert len(codigos) == 10
    assert anterior not in codigos

    fail = client.post(
        "/api/v1/auth/2fa/verify",
        json={"email": "2fa-recovery@test.com", "code": anterior},
    )
    assert fail.status_code == 400


def test_2fa_enable_requiere_codigo(client):
    uid, h = _user(client, "2fa-body@test.com")
    r = client.post(
        "/api/v1/auth/2fa/enable", headers=h, json={"method": "sms"}
    )
    assert r.status_code == 422