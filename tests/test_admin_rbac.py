"""pytest — RBAC Fase 1: panel admin, decoradores y revocación de token."""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario, Verification


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


def _make_user(email, rol, nombre=None, status="active"):
    u = User(
        email=email,
        rol=rol,
        nombre=nombre,
        acepto_tyc=True,
        activo=True,
        status=status,
    )
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.commit()
    return u


def _headers(user):
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.rol.value, "role_v": user.role_version},
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------- acceso por rol ----------------

def test_admin_lista_usuarios_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    r = client.get("/api/v1/admin/users", headers=_headers(admin))
    assert r.status_code == 200
    assert "items" in r.get_json()
    assert "total" in r.get_json()


def test_admin_stats_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    r = client.get("/api/v1/admin/stats/overview", headers=_headers(admin))
    assert r.status_code == 200
    data = r.get_json()
    assert "users_total" in data
    assert "revenue_total" in data


@pytest.mark.parametrize(
    "rol",
    [RolUsuario.PDS, RolUsuario.SOLICITANTE, RolUsuario.VERIFICADOR, RolUsuario.SOPORTE],
)
def test_no_admin_403_en_users(client, rol):
    u = _make_user("u@x.com", rol, "U")
    r = client.get("/api/v1/admin/users", headers=_headers(u))
    assert r.status_code == 403


def test_superadmin_accede_200(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    r = client.get("/api/v1/admin/users", headers=_headers(sa))
    assert r.status_code == 200


# ---------------- verificaciones ----------------

def test_aprobar_verificacion_cambia_status(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    user = _make_user("v@x.com", RolUsuario.PDS, "V")
    v = Verification(user_id=user.id, document_type="cédula",
                     document_number="123", status="pending")
    db.session.add(v)
    db.session.commit()

    r = client.post(
        f"/api/v1/admin/verifications/{v.id}/approve", headers=_headers(admin)
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "approved"
    db.session.refresh(v)
    assert v.status == "approved"
    assert v.reviewed_by == admin.id


def test_rechazar_verificacion_con_razon(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    user = _make_user("v@x.com", RolUsuario.PDS, "V")
    v = Verification(user_id=user.id, status="pending")
    db.session.add(v)
    db.session.commit()

    r = client.post(
        f"/api/v1/admin/verifications/{v.id}/reject",
        headers=_headers(admin),
        json={"reason": "documento ilegible"},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "rejected"
    db.session.refresh(v)
    assert v.reason == "documento ilegible"


# ---------------- cambio de rol / estado ----------------

def test_patch_role_superadmin_403(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    target = _make_user("t@x.com", RolUsuario.PDS, "T")
    r = client.patch(
        f"/api/v1/admin/users/{target.id}/role",
        headers=_headers(admin),
        json={"role": "superadmin"},
    )
    assert r.status_code == 403


def test_patch_role_valido_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    target = _make_user("t@x.com", RolUsuario.PDS, "T")
    r = client.patch(
        f"/api/v1/admin/users/{target.id}/role",
        headers=_headers(admin),
        json={"role": "solicitante"},
    )
    assert r.status_code == 200
    assert r.get_json()["rol"] == "solicitante"
    db.session.refresh(target)
    assert target.rol == RolUsuario.SOLICITANTE
    assert target.role_version == 2  # se incrementó


def test_patch_status_suspend_200(client):
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    target = _make_user("t@x.com", RolUsuario.PDS, "T")
    r = client.patch(
        f"/api/v1/admin/users/{target.id}/status",
        headers=_headers(admin),
        json={"status": "suspended"},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "suspended"


def test_token_revoked_tras_cambio_rol(client):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    admin = _make_user("admin@x.com", RolUsuario.ADMIN, "Admin")
    # Token de admin emitido con role_v=1
    old_headers = _headers(admin)
    # Un superadmin cambia el estado del admin -> role_version pasa a 2
    client.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        headers=_headers(sa),
        json={"status": "suspended"},
    )
    # El token viejo (role_v=1) ya no coincide -> revocado (401).
    r = client.get("/api/v1/admin/users", headers=old_headers)
    assert r.status_code == 401
