"""pytest suite — contracts (RF-07) + notifications (RF-16 parcial)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.contract import Contract, EstadoContrato
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.notification import Notification


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


def _register(client, email, rol="pds", password="secret123"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )


def _login(client, email, password="secret123"):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).get_json()


def _headers(client, email, password="secret123"):
    return {"Authorization": f"Bearer {_login(client, email, password)['access_token']}"}


def _user(client, email, rol="pds"):
    _register(client, email=email, rol=rol)
    return _headers(client, email)


def _crear_servicio(client, headers):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={"titulo": "Reparar grifo", "categoria": "plomeria", "descripcion": "arreglar", "ubicacion": "Valledupar"},
        headers=headers,
    )
    return resp.get_json()["id"]


# ---------------- RF-07.1: crear orden ----------------
def test_create_order_ok(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    tr_id = _login(client, "tr@example.com")["access_token"]
    # id del trabajador = 2 (empleador=1)
    sid = _crear_servicio(client, emp_h)
    resp = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["estado"] == "pendiente"
    assert d["solicitante_id"] == 1
    assert d["proveedor_id"] == 2
    assert d["service"]["id"] == sid


def test_create_order_not_owner(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    other_h = _user(client, "other@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    resp = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 3},
        headers=other_h,
    )
    assert resp.status_code == 403


def test_create_order_service_not_publicado(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    # sacar de publicado
    client.patch(
        f"/api/v1/solicitudes/{sid}/estado",
        json={"estado": "completado"},
        headers=emp_h,
    )
    resp = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    )
    assert resp.status_code == 400


# ---------------- RF-07.2: aceptar ----------------
def test_aceptar_ok(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=tr_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "en_progreso"


def test_aceptar_not_proveedor(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    # solicitante intenta aceptar
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=emp_h,
    )
    assert resp.status_code == 403


# ---------------- capeta: check-in / check-out ----------------
def test_aceptar_sets_inicio_en(client):
    """RF-07.2 (capeta): pds acepta -> en_progreso y inicio_en no nulo."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=tr_h,
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["estado"] == "en_progreso"
    assert d["inicio_en"] is not None
    assert d["fin_en"] is None


def test_completar_sets_fin_en(client):
    """RF-07.3 (capeta): pds completa -> completado y fin_en no nulo."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=tr_h,
    )
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "completar"},
        headers=tr_h,
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["estado"] == "completado"
    assert d["inicio_en"] is not None
    assert d["fin_en"] is not None


def test_cancelar_saves_motivo(client):
    """RF-07.4: cancelar con motivo -> cancelado y motivo_cancelacion guardado."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "cancelar", "motivo_cancelacion": "ya no necesito"},
        headers=emp_h,
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["estado"] == "cancelado"
    assert d["motivo_cancelacion"] == "ya no necesito"


def test_aceptar_wrong_role_403(client):
    """Rol equivocado: solicitante hace 'aceptar' -> 403 (solo pds)."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=emp_h,
    )
    assert resp.status_code == 403
    # y el contrato sigue pendiente (no se mutó)
    det = client.get(f"/api/v1/contracts/{oid}", headers=emp_h).get_json()
    assert det["estado"] == "pendiente"


# ---------------- RF-07.3: completar ----------------
def test_completar_ok_propagates_service(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "aceptar"},
        headers=tr_h,
    )
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "completar"},
        headers=tr_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "completado"
    # Service.estado queda 'completado' (habilita ratings RF-03)
    svc = client.get(f"/api/v1/solicitudes/{sid}").get_json()
    assert svc["estado"] == "completado"


# ---------------- RF-07.4: cancelar ----------------
def test_cancelar_ok_notifies_contraparte(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "cancelar", "motivo_cancelacion": "ya no necesito"},
        headers=emp_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "cancelado"
    # notificación a contraparte (proveedor id=2): debe incluir la de cancelación
    notifs = client.get("/api/v1/notifications/me", headers=tr_h).get_json()
    assert any("cancelad" in n["mensaje"] for n in notifs)


def test_cancelar_requires_motivo(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "cancelar"},
        headers=emp_h,
    )
    assert resp.status_code == 400


# ---------------- transición ilegal ----------------
def test_transicion_ilegal_completar_desde_pendiente(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.patch(
        f"/api/v1/contracts/{oid}/estado",
        json={"estado": "completar"},
        headers=tr_h,
    )
    assert resp.status_code == 400


# ---------------- GET /mine filtra ----------------
def test_mine_filtra_estado(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    # solicitante ve su orden
    resp = client.get("/api/v1/contracts/mine", headers=emp_h)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1
    # filtro por estado
    resp2 = client.get("/api/v1/contracts/mine?estado=pendiente", headers=emp_h)
    assert len(resp2.get_json()) == 1
    resp3 = client.get("/api/v1/contracts/mine?estado=completado", headers=emp_h)
    assert len(resp3.get_json()) == 0


def test_detail_forbidden_for_non_participant(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "tr@example.com", rol="pds")
    outsider_h = _user(client, "out@example.com", rol="solicitante")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    resp = client.get(f"/api/v1/contracts/{oid}", headers=outsider_h)
    assert resp.status_code == 403


# ---------------- RF-16: notifications ----------------
def test_notification_me_and_read(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    )
    # proveedor tiene la notificación de orden pendiente
    resp = client.get("/api/v1/notifications/me", headers=tr_h)
    assert resp.status_code == 200
    notifs = resp.get_json()
    assert len(notifs) == 1
    nid = notifs[0]["id"]
    assert notifs[0]["leida"] is False

    # marcar leída
    r = client.patch(f"/api/v1/notifications/{nid}/read", headers=tr_h)
    assert r.status_code == 200
    assert r.get_json()["leida"] is True

    # otro usuario no puede marcarla
    other_h = _user(client, "out@example.com", rol="solicitante")
    r2 = client.patch(f"/api/v1/notifications/{nid}/read", headers=other_h)
    assert r2.status_code == 403
