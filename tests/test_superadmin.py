"""pytest — RBAC Fase 3: panel SUPERADMIN.

Verifica acceso de superadmin a todas las rutas y denegación (403) para
roles admin/soporte/verificador en /api/v1/superadmin/*.
"""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato
from app.models.config import SystemConfig, FeatureFlag


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


def _seed_config():
    """Crea SystemConfig/FeatureFlag mínimos para los tests."""
    if not SystemConfig.query.filter_by(key="tyc_current").first():
        db.session.add(
            SystemConfig(
                key="tyc_current",
                value_type="json",
                value='{"version": 1, "content": "v1", "published_at": "2026-01-01T00:00:00+00:00"}',
                description="T&C",
            )
        )
    if not SystemConfig.query.filter_by(key="ai_weights").first():
        db.session.add(
            SystemConfig(
                key="ai_weights",
                value_type="json",
                value='{"w_price": 0.4, "w_rating": 0.3, "w_distance": 0.3}',
                description="IA",
            )
        )
    if not SystemConfig.query.filter_by(key="commission_rate").first():
        db.session.add(
            SystemConfig(
                key="commission_rate",
                value_type="int",
                value="12",
                description="Comisión",
            )
        )
    if not FeatureFlag.query.filter_by(key="module_3d").first():
        db.session.add(FeatureFlag(key="module_3d", enabled=False, description="3D"))
    db.session.commit()


@pytest.fixture
def superadmin(app):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    _seed_config()
    return sa


# ---------------- acceso por rol ----------------

def test_superadmin_lista_admins_200(client, superadmin):
    r = client.get("/api/v1/superadmin/admins", headers=_headers(superadmin))
    assert r.status_code == 200
    assert "items" in r.get_json()


def test_superadmin_crea_admin_200(client, superadmin):
    r = client.post(
        "/api/v1/superadmin/admins",
        headers=_headers(superadmin),
        json={
            "email": "nuevo@chambeapp.com",
            "nombre": "Nuevo Admin",
            "rol": "soporte",
            "password": "Clave123!",
        },
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["items"][0]["email"] == "nuevo@chambeapp.com"
    assert data["items"][0]["rol"] == "soporte"


def test_superadmin_edita_admin_200(client, superadmin):
    target = _make_user("edit@x.com", RolUsuario.SOPORTE, "Edit")
    r = client.patch(
        f"/api/v1/superadmin/admins/{target.id}",
        headers=_headers(superadmin),
        json={"status": "suspended"},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "suspended"


def test_superadmin_borra_admin_200(client, superadmin):
    target = _make_user("del@x.com", RolUsuario.VERIFICADOR, "Del")
    r = client.delete(
        f"/api/v1/superadmin/admins/{target.id}", headers=_headers(superadmin)
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "banned"


def test_superadmin_update_config_200(client, superadmin):
    r = client.patch(
        "/api/v1/superadmin/config",
        headers=_headers(superadmin),
        json={"key": "commission_rate", "value": 15},
    )
    assert r.status_code == 200
    assert r.get_json()["value"] == 15


def test_superadmin_list_audit_200(client, superadmin):
    r = client.get("/api/v1/superadmin/audit-logs", headers=_headers(superadmin))
    assert r.status_code == 200
    assert "items" in r.get_json()


def test_superadmin_audit_detail_200(client, superadmin):
    # Genera un log primero (update config) y luego lee detalle.
    client.patch(
        "/api/v1/superadmin/config",
        headers=_headers(superadmin),
        json={"key": "commission_rate", "value": 15},
    )
    logs = client.get(
        "/api/v1/superadmin/audit-logs", headers=_headers(superadmin)
    ).get_json()
    log_id = logs["items"][0]["id"]
    r = client.get(
        f"/api/v1/superadmin/audit-logs/{log_id}", headers=_headers(superadmin)
    )
    assert r.status_code == 200
    assert "before_json" in r.get_json()


def test_superadmin_publish_tyc_200(client, superadmin):
    r = client.post(
        "/api/v1/superadmin/legal/tyc",
        headers=_headers(superadmin),
        json={"content": "Nuevos T&C de ChambeApp."},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["version"] == 2  # incrementa desde v1 sembrada


def test_superadmin_get_tyc_200(client, superadmin):
    r = client.get("/api/v1/superadmin/legal/tyc", headers=_headers(superadmin))
    assert r.status_code == 200
    assert r.get_json()["version"] == 1


def test_superadmin_override_user_200(client, superadmin):
    target = _make_user("ov@x.com", RolUsuario.PDS, "OV", status="suspended")
    r = client.post(
        "/api/v1/superadmin/override/user",
        headers=_headers(superadmin),
        json={"user_id": target.id, "action": "reactivate"},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "active"


def test_superadmin_override_order_200(client, superadmin):
    emp = _make_user("emp@x.com", RolUsuario.SOLICITANTE, "EMP")
    prov = _make_user("prov@x.com", RolUsuario.PDS, "PROV")
    svc = Solicitud(
        solicitante_id=emp.id,
        titulo="Reparar grifo",
        categoria="plomería",
        descripcion="demo",
        ubicacion="Valledupar",
        estado=EstadoSolicitud.PUBLICADO,
    )
    db.session.add(svc)
    db.session.commit()
    contract = Contract(
        service_id=svc.id,
        proveedor_id=prov.id,
        solicitante_id=emp.id,
        estado=EstadoContrato.PENDIENTE,
    )
    db.session.add(contract)
    db.session.commit()
    r = client.post(
        "/api/v1/superadmin/override/contract",
        headers=_headers(superadmin),
        json={"contract_id": contract.id, "action": "complete"},
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "completado"


def test_superadmin_ai_params_200(client, superadmin):
    r = client.get("/api/v1/superadmin/ai/params", headers=_headers(superadmin))
    assert r.status_code == 200
    assert "w_price" in r.get_json()
    r2 = client.patch(
        "/api/v1/superadmin/ai/params",
        headers=_headers(superadmin),
        json={"w_price": 0.5, "w_rating": 0.3, "w_distance": 0.2},
    )
    assert r2.status_code == 200
    assert r2.get_json()["w_price"] == 0.5


def test_superadmin_flags_200(client, superadmin):
    r = client.get("/api/v1/superadmin/flags", headers=_headers(superadmin))
    assert r.status_code == 200
    assert "items" in r.get_json()
    r2 = client.patch(
        "/api/v1/superadmin/flags/module_3d",
        headers=_headers(superadmin),
        json={"enabled": True},
    )
    assert r2.status_code == 200
    assert r2.get_json()["enabled"] is True


# ---------------- denegación a no-superadmin ----------------

@pytest.mark.parametrize(
    "rol",
    [RolUsuario.ADMIN, RolUsuario.SOPORTE, RolUsuario.VERIFICADOR],
)
def test_no_superadmin_403_en_superadmin(client, rol):
    u = _make_user("u@x.com", rol, "U")
    r = client.get("/api/v1/superadmin/admins", headers=_headers(u))
    assert r.status_code == 403
