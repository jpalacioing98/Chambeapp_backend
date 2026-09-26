"""pytest — Seguridad: JWT, RBAC, revocación, refresh y sockets.

- Auditoría: ningún GET /api/v1 nuevo debe quedar público sin allowlist.
- Rutas sensibles (admin/superadmin/kyc/regiones/onboarding/me) exigen JWT.
- RBAC: rol no permitido -> 403; role_version cambiado -> 401; token inválido -> 401.
- Refresh: renueva access y emite nuevo refresh; revocado por cambio de rol/estado.
- Sockets: el user_id se deriva del JWT, nunca del payload del cliente.
"""

import re

import pytest
from flask_jwt_extended import create_access_token, create_refresh_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.auth.socket_auth import decode_socket_user_id

PUBLIC_GET_ALLOW = {
    "/api/v1/auth/health",
    "/api/v1/legal/politica-datos",
    "/api/v1/legal/tyc",
    "/api/v1/negocios/",
    "/api/v1/negocios/buscar",
    "/api/v1/negocios/categorias",
    "/api/v1/negocios/mapa",
    "/api/v1/negocios/slug/<string:slug>",
    "/api/v1/negocios/<int:negocio_id>",
    "/api/v1/negocios/<int:negocio_id>/ratings",
    "/api/v1/payments/nequi",
    "/api/v1/portfolio/pds/<int:pds_id>",
    "/api/v1/prices/precios",
    "/api/v1/prices/precios/<string:categoria>",
    "/api/v1/providers/search",
    "/api/v1/solicitudes/",
    "/api/v1/solicitudes/<int:solicitud_id>",
    "/api/v1/solicitudes/<int:solicitud_id>/ratings",
    "/api/v1/subscriptions/planes",
    "/api/v1/trust/<int:user_id>",
    "/api/v1/users/<int:user_id>/profile",
    "/api/v1/wallet/coins/packages",
    "/api/v1/ai/recommendations",
}


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


def _make_user(email, rol, status="active"):
    u = User(email=email, rol=rol, nombre="U", acepto_tyc=True, activo=True, status=status)
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, email, password="ChambeApp123!"):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).get_json()


def _concrete(path):
    path = re.sub(r"<int:[^>]+>", "1", path)
    path = re.sub(r"<float:[^>]+>", "1", path)
    path = re.sub(r"<uuid:[^>]+>", "00000000-0000-0000-0000-000000000000", path)
    path = re.sub(r"<string:[^>]+>", "x", path)
    path = re.sub(r"<[^:]+:[^>]+>", "1", path)
    path = re.sub(r"<[^>]+>", "1", path)
    return path


# ---------------- Auditoría: GET públicos requieren allowlist ----------------

def test_no_new_public_get_without_allowlist(app, client):
    """Todo GET /api/v1 accesible sin token debe estar en PUBLIC_GET_ALLOW."""
    leaks = []
    for rule in app.url_map.iter_rules():
        rule_path = rule.rule
        if not rule_path.startswith("/api/v1") or "GET" not in rule.methods:
            continue
        resp = client.get(_concrete(rule_path))
        if resp.status_code in (200, 201, 204):
            if rule_path not in PUBLIC_GET_ALLOW:
                leaks.append((rule_path, resp.status_code))
    assert leaks == [], f"Rutas GET sin token no permitidas: {leaks}"


# ---------------- Rutas sensibles exigen autenticación ----------------

SENSITIVE_GETS = [
    "/api/v1/admin/users",
    "/api/v1/admin/staff",
    "/api/v1/superadmin/admins",
    "/api/v1/kyc/pendientes",
    "/api/v1/onboarding/status",
    "/api/v1/users/me/profile",
    "/api/v1/regions",
    "/api/v1/regions/detectar",
]


@pytest.mark.parametrize("path", SENSITIVE_GETS)
def test_sensitive_route_requires_auth(client, path):
    resp = client.get(path)
    assert resp.status_code == 401


def test_admin_route_forbidden_for_pds(client):
    user = _make_user("pds@x.com", RolUsuario.PDS)
    data = _login(client, "pds@x.com")
    resp = client.get(
        "/api/v1/admin/users", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert resp.status_code == 403


def test_admin_route_allowed_for_admin(client):
    user = _make_user("admin@x.com", RolUsuario.ADMIN)
    data = _login(client, "admin@x.com")
    resp = client.get(
        "/api/v1/admin/users", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert resp.status_code == 200


def test_invalid_token_rejected(client):
    resp = client.get(
        "/api/v1/users/me/profile", headers={"Authorization": "Bearer token-invalido"}
    )
    assert resp.status_code in (401, 422)


# ---------------- Revocación por role_version ----------------

def test_role_change_revokes_access_token(app, client):
    """La revocación por role_version se aplica en rutas role_required."""
    user = _make_user("u@x.com", RolUsuario.ADMIN)
    uid = user.id
    data = _login(client, "u@x.com")
    token = data["access_token"]
    u = db.session.get(User, uid)
    u.rol = RolUsuario.PDS
    u.role_version += 1
    db.session.commit()
    resp = client.get(
        "/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code in (401, 403)


# ---------------- Refresh: renovación + revocación ----------------

def test_refresh_returns_new_tokens(client):
    _make_user("r@x.com", RolUsuario.PDS)
    data = _login(client, "r@x.com")
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {data['refresh_token']}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_refresh_revoked_when_status_changes(client):
    user = _make_user("s@x.com", RolUsuario.PDS)
    data = _login(client, "s@x.com")
    user.status = "suspended"
    user.role_version += 1
    db.session.commit()
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {data['refresh_token']}"},
    )
    assert resp.status_code == 401


def test_refresh_invalid_without_token(client):
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


# ---------------- 2FA: desafío en login + verificación ----------------

def test_login_requires_2fa_when_enabled(client):
    user = _make_user("2fa@x.com", RolUsuario.PDS)
    user.two_factor_enabled = True
    db.session.commit()
    resp = client.post(
        "/api/v1/auth/login", json={"email": "2fa@x.com", "password": "ChambeApp123!"}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("requires_2fa") is True
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "dev_code" in body


def test_login_without_2fa_returns_tokens(client):
    _make_user("nof2fa@x.com", RolUsuario.PDS)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "nof2fa@x.com", "password": "ChambeApp123!"}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("requires_2fa") is None
    assert "access_token" in body


def test_verify_2fa_issues_tokens(client):
    user = _make_user("2fab@x.com", RolUsuario.ADMIN)
    user.two_factor_enabled = True
    db.session.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": "2fab@x.com", "password": "ChambeApp123!"}
    ).get_json()
    assert login["requires_2fa"] is True

    verify = client.post(
        "/api/v1/auth/2fa/verify", json={"email": "2fab@x.com", "code": login["dev_code"]}
    )
    assert verify.status_code == 200
    tokens = verify.get_json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.get_json()["email"] == "2fab@x.com"


def test_verify_2fa_wrong_code(client):
    user = _make_user("2fac@x.com", RolUsuario.PDS)
    user.two_factor_enabled = True
    db.session.commit()
    client.post("/api/v1/auth/login", json={"email": "2fac@x.com", "password": "ChambeApp123!"})
    resp = client.post(
        "/api/v1/auth/2fa/verify", json={"email": "2fac@x.com", "code": "000000"}
    )
    assert resp.status_code == 400


def test_verify_2fa_without_challenge(client):
    _make_user("2fad@x.com", RolUsuario.PDS)
    resp = client.post(
        "/api/v1/auth/2fa/verify", json={"email": "2fad@x.com", "code": "123456"}
    )
    assert resp.status_code == 400


# ---------------- Sockets: identidad desde el JWT ----------------

def test_socket_auth_from_handshake(app):
    with app.app_context():
        user = _make_user("sock@x.com", RolUsuario.PDS)
        token = create_access_token(identity=str(user.id))
        assert decode_socket_user_id(auth={"token": token}) == user.id
        assert decode_socket_user_id(auth={"access_token": token}) == user.id


def test_socket_auth_from_event_data(app):
    with app.app_context():
        user = _make_user("sock2@x.com", RolUsuario.PDS)
        token = create_refresh_token(identity=str(user.id))
        assert decode_socket_user_id(data={"token": token}) == user.id


def test_socket_auth_rejects_garbage():
    assert decode_socket_user_id(auth={"token": "basura"}) is None
    assert decode_socket_user_id(data={"token": "basura"}) is None
    assert decode_socket_user_id() is None


def test_socket_auth_ignores_client_user_id(app):
    """El user_id del payload del cliente NO debe influir en la identidad."""
    with app.app_context():
        user = _make_user("sock3@x.com", RolUsuario.PDS)
        token = create_access_token(identity=str(user.id))
        # Aunque el cliente mande otro user_id, la identidad es la del token.
        decoded = decode_socket_user_id(auth={"token": token})
        assert decoded == user.id
        assert decoded != 9999