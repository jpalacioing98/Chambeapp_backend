"""pytest — brechas del panel SuperAdmin cerradas (nov 2026).

Cubre lo que antes solo se podía aproximar en el frontend:
- filtros de auditoría (acción, texto, fechas, offset y tope de limit)
- T&C con borrador, historial y rollback
- justificación persistida en los overrides de emergencia
- reordenamiento masivo y reactivación de paquetes de monedas
- `updated_at` en la configuración de cobros
"""

from datetime import datetime, timedelta, timezone

import json

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.audit import AuditLog, write_audit
from app.models.config import SystemConfig


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


def _make_user(email, rol, nombre=None):
    u = User(
        email=email,
        rol=rol,
        nombre=nombre,
        acepto_tyc=True,
        activo=True,
        status="active",
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


@pytest.fixture
def superadmin(app):
    sa = _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA")
    db.session.add(
        SystemConfig(
            key="tyc_current",
            value_type="json",
            value='{"version": 1, "content": "texto v1", "published_at": "2026-01-01T00:00:00+00:00"}',
            description="T&C vigentes",
        )
    )
    db.session.commit()
    return sa


# ---------------------------------------------------------------- auditoría

def _log(actor_id, action, entity_type="user", entity_id=1, dias=0):
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=None,
        after_json=None,
    )
    db.session.add(log)
    db.session.commit()
    log.created_at = datetime.now(timezone.utc) - timedelta(days=dias)
    db.session.commit()
    return log


def test_auditoria_filtra_por_accion(client, superadmin):
    _log(superadmin.id, "superadmin.flags.update")
    _log(superadmin.id, "superadmin.tyc.publish", "system_config")

    r = client.get(
        "/api/v1/superadmin/audit-logs?action=flags", headers=_headers(superadmin)
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["items"][0]["action"] == "superadmin.flags.update"


def test_auditoria_filtra_por_texto(client, superadmin):
    _log(superadmin.id, "superadmin.flags.update", "feature_flag")
    _log(superadmin.id, "cobros.update", "tarifas_cobro")

    r = client.get(
        "/api/v1/superadmin/audit-logs?q=tarifas", headers=_headers(superadmin)
    )
    assert r.status_code == 200
    assert r.get_json()["total"] == 1


def test_auditoria_filtra_por_rango_de_fechas(client, superadmin):
    _log(superadmin.id, "viejo.evento", dias=10)
    _log(superadmin.id, "nuevo.evento", dias=0)

    hoy = datetime.now(timezone.utc).date().isoformat()
    ayer = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()

    r = client.get(
        f"/api/v1/superadmin/audit-logs?from={ayer}&to={hoy}",
        headers=_headers(superadmin),
    )
    assert r.status_code == 200
    acciones = [i["action"] for i in r.get_json()["items"]]
    assert "nuevo.evento" in acciones
    assert "viejo.evento" not in acciones


def test_auditoria_pagina_con_offset(client, superadmin):
    for i in range(5):
        _log(superadmin.id, f"evento.{i}")

    r = client.get(
        "/api/v1/superadmin/audit-logs?limit=2&offset=2",
        headers=_headers(superadmin),
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


def test_auditoria_limita_el_tamano_de_pagina(client, superadmin):
    r = client.get(
        "/api/v1/superadmin/audit-logs?limit=9999", headers=_headers(superadmin)
    )
    assert r.status_code == 200  # no revienta; el tope interno es 500


# ---------------------------------------------------------------- T&C

def test_tyc_guarda_borrador_sin_publicar(client, superadmin):
    r = client.put(
        "/api/v1/superadmin/legal/tyc/draft",
        headers=_headers(superadmin),
        json={"content": "borrador nuevo"},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/superadmin/legal/tyc", headers=_headers(superadmin))
    assert r.status_code == 200
    data = r.get_json()
    assert data["version"] == 1
    assert data["draft"]["content"] == "borrador nuevo"


def test_tyc_publicar_archiva_la_version_anterior(client, superadmin):
    r = client.post(
        "/api/v1/superadmin/legal/tyc",
        headers=_headers(superadmin),
        json={"content": "texto v2"},
    )
    assert r.status_code == 201
    assert r.get_json()["version"] == 2

    r = client.get(
        "/api/v1/superadmin/legal/tyc/history", headers=_headers(superadmin)
    )
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert items and items[0]["version"] == 1
    assert items[0]["content"] == "texto v1"


def test_tyc_publicar_descarta_el_borrador(client, superadmin):
    client.put(
        "/api/v1/superadmin/legal/tyc/draft",
        headers=_headers(superadmin),
        json={"content": "borrador"},
    )
    client.post(
        "/api/v1/superadmin/legal/tyc",
        headers=_headers(superadmin),
        json={"content": "publicado"},
    )
    r = client.get("/api/v1/superadmin/legal/tyc", headers=_headers(superadmin))
    assert r.get_json()["draft"] is None


def test_tyc_rollback_restaura_una_version(client, superadmin):
    client.post(
        "/api/v1/superadmin/legal/tyc",
        headers=_headers(superadmin),
        json={"content": "texto v2"},
    )

    r = client.post(
        "/api/v1/superadmin/legal/tyc/rollback",
        headers=_headers(superadmin),
        json={"version": 1},
    )
    assert r.status_code == 200
    assert r.get_json()["version"] == 1

    r = client.get("/api/v1/superadmin/legal/tyc", headers=_headers(superadmin))
    data = r.get_json()
    assert data["content"] == "texto v1"

    # La v2 queda archivada: el rollback no destruye historial.
    r = client.get(
        "/api/v1/superadmin/legal/tyc/history", headers=_headers(superadmin)
    )
    versiones = [i["version"] for i in r.get_json()["items"]]
    assert 2 in versiones


def test_tyc_rollback_de_version_inexistente_404(client, superadmin):
    r = client.post(
        "/api/v1/superadmin/legal/tyc/rollback",
        headers=_headers(superadmin),
        json={"version": 99},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- overrides

def test_override_persiste_la_justificacion(client, superadmin):
    victima = _make_user("pds@x.com", RolUsuario.PDS, "PDS")
    motivo = "Suspensión por suplantación verificada en soporte"

    r = client.post(
        "/api/v1/superadmin/override/user",
        headers=_headers(superadmin),
        json={"user_id": victima.id, "action": "suspend", "justificacion": motivo},
    )
    assert r.status_code == 200

    log = (
        AuditLog.query.filter_by(action="superadmin.override.user.suspend")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert json.loads(log.after_json)["justificacion"] == motivo


def test_override_rechaza_justificacion_muy_corta(client, superadmin):
    victima = _make_user("pds2@x.com", RolUsuario.PDS, "PDS")
    r = client.post(
        "/api/v1/superadmin/override/user",
        headers=_headers(superadmin),
        json={"user_id": victima.id, "action": "suspend", "justificacion": "corto"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- paquetes

def _crear_paquete(client, superadmin, nombre, cantidad=100, precio=10000, orden=0):
    r = client.post(
        "/api/v1/wallet/admin/paquetes",
        headers=_headers(superadmin),
        json={
            "nombre": nombre,
            "cantidad": cantidad,
            "precio_cop": precio,
            "orden": orden,
        },
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_paquetes_reordenar_en_una_sola_llamada(client, superadmin):
    a = _crear_paquete(client, superadmin, "Paquete A", orden=1)
    b = _crear_paquete(client, superadmin, "Paquete B", orden=2)
    c = _crear_paquete(client, superadmin, "Paquete C", orden=3)

    r = client.post(
        "/api/v1/wallet/admin/paquetes/reordenar",
        headers=_headers(superadmin),
        json={"ids": [c, a, b]},
    )
    assert r.status_code == 200
    ordenados = {p["id"]: p["orden"] for p in r.get_json()}
    assert ordenados[c] == 1
    assert ordenados[a] == 2
    assert ordenados[b] == 3


def test_paquetes_reordenar_con_id_inexistente_falla(client, superadmin):
    a = _crear_paquete(client, superadmin, "Paquete A")
    r = client.post(
        "/api/v1/wallet/admin/paquetes/reordenar",
        headers=_headers(superadmin),
        json={"ids": [a, 999999]},
    )
    assert r.status_code == 400


def test_paquete_se_puede_reactivar(client, superadmin):
    pid = _crear_paquete(client, superadmin, "Paquete A")
    client.delete(f"/api/v1/wallet/admin/paquetes/{pid}", headers=_headers(superadmin))

    r = client.post(
        f"/api/v1/wallet/admin/paquetes/{pid}/activar", headers=_headers(superadmin)
    )
    assert r.status_code == 200
    assert r.get_json()["activo"] is True


# ---------------------------------------------------------------- cobros

def test_cobros_expone_la_ultima_actualizacion(client, superadmin):
    r = client.put(
        "/api/v1/admin/cobros",
        headers=_headers(superadmin),
        json={"pct_contrato": 4},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["tarifas"]["pct_contrato"] == 4
    assert data["updated_at"] is not None
    assert data["updated_by"] == superadmin.id

    r = client.get("/api/v1/admin/cobros", headers=_headers(superadmin))
    assert r.status_code == 200
    assert r.get_json()["updated_at"] is not None
