"""pytest suite — payments (RF-08) + pagos directos/refund/retry + RF-09 parcial."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.contract import Contract, EstadoContrato
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.payment import Payment, EstadoPago
from app.models.user import User, RolUsuario


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


def _contrato_completado(client, emp_h, tr_h, tr_id):
    """Crea servicio, contrato, acepta y completa. Devuelve contract_id."""
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": tr_id},
        headers=emp_h,
    ).get_json()["id"]
    client.patch(
        f"/api/v1/contracts/{oid}/estado", json={"estado": "aceptar"}, headers=tr_h
    )
    client.patch(
        f"/api/v1/contracts/{oid}/estado", json={"estado": "completar"}, headers=tr_h
    )
    return oid


# ---------------- RF-08.1: crear pago ----------------
def test_crear_pago_ok(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    resp = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["estado"] == "pendiente"
    assert d["monto"] == 100000
    assert d["comision_pds"] == 12000  # 12% de 100000


def test_crear_pago_orden_no_completada(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "tr@example.com", rol="pds")
    sid = _crear_servicio(client, emp_h)
    oid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": 2},
        headers=emp_h,
    ).get_json()["id"]
    # orden sigue 'pendiente' -> 400
    resp = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    )
    assert resp.status_code == 400


def test_comision_exenta_bajo_umbral(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    resp = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 40000}, headers=emp_h
    )
    assert resp.status_code == 201
    assert resp.get_json()["comision_pds"] == 0  # < 50000 => exenta


def test_comision_12_por_encima_umbral(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    resp = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 50000}, headers=emp_h
    )
    assert resp.status_code == 201
    assert resp.get_json()["comision_pds"] == 6000  # 12% de 50000


# ---------------- RF-08.3 / 08.6 / 08.7: ciclo ----------------
def test_confirmar_pago_directo(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    pid = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    ).get_json()["id"]
    r = client.post(f"/api/v1/payments/{pid}/confirm", headers=emp_h)
    assert r.status_code == 200
    assert r.get_json()["estado"] == "completado"
    assert r.get_json()["referencia_pasarela"].startswith("MOCK-")


def test_liberar_pago_directo(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    pid = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    ).get_json()["id"]
    client.post(f"/api/v1/payments/{pid}/confirm", headers=emp_h)
    r = client.post(f"/api/v1/payments/{pid}/release", headers=emp_h)
    assert r.status_code == 200
    d = r.get_json()
    assert d["estado"] == "completado"
    assert d["liberado_en"] is not None


def test_reembolsar_con_motivo(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    pid = client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    ).get_json()["id"]
    client.post(f"/api/v1/payments/{pid}/confirm", headers=emp_h)
    r = client.post(
        f"/api/v1/payments/{pid}/refund",
        json={"motivo_reembolso": "no-show del proveedor"},
        headers=emp_h,
    )
    assert r.status_code == 200
    d = r.get_json()
    assert d["estado"] == "reembolsado"
    assert d["motivo_reembolso"] == "no-show del proveedor"


# ---------------- RF-08.5: retry sobre fallido ----------------
def test_retry_fallido(client, app):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    # crear pago y forzar estado 'fallido' via DB directa
    with app.app_context():
        p = Payment(
            contract_id=oid, monto=100000, comision_pds=12000, comision_solicitante=8000,
            estado=EstadoPago.FALLIDO, pasarela="mock",
        )
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = client.post(f"/api/v1/payments/{pid}/retry", headers=emp_h)
    assert r.status_code == 200
    assert r.get_json()["estado"] == "completado"


# ---------------- RF-09 parcial: GET /mine ----------------
def test_mine_filtra_por_usuario(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    tr_h = _user(client, "tr@example.com", rol="pds")
    oid = _contrato_completado(client, emp_h, tr_h, tr_id=2)
    client.post(
        "/api/v1/payments/", json={"contract_id": oid, "monto": 100000}, headers=emp_h
    )
    # solicitante (empleador) ve el pago
    r = client.get("/api/v1/payments/mine", headers=emp_h)
    assert r.status_code == 200
    assert len(r.get_json()) == 1
    # proveedor (trabajador) tambien lo ve (participa en la orden)
    r2 = client.get("/api/v1/payments/mine", headers=tr_h)
    assert len(r2.get_json()) == 1
    # outsider no ve nada
    out_h = _user(client, "out@example.com", rol="solicitante")
    r3 = client.get("/api/v1/payments/mine", headers=out_h)
    assert len(r3.get_json()) == 0


# ---------------- admin auto-release ----------------
def test_admin_auto_release_protegido(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    _user(client, "admin@example.com", rol="admin")
    admin_h = _headers(client, "admin@example.com")
    # no admin -> 403
    r = client.post("/api/v1/payments/admin/auto-release", headers=emp_h)
    assert r.status_code == 403
    # admin -> 200
    r2 = client.post("/api/v1/payments/admin/auto-release", headers=admin_h)
    assert r2.status_code == 200
    assert "liberados" in r2.get_json()
