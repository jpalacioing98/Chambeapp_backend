"""pytest suite — Comerciante (merchant) publica chambas (RF-04 extendido).

Contrato (cambio 2026-09-17): POST /solicitudes/ acepta los roles
`solicitante` y `merchant` (antes solo `solicitante`). El aislamiento se
mantiene: cada solicitud queda ligada a su creador (solicitante_id) y solo
el dueño puede cambiar su estado.
"""

import pytest

from app import create_app
from app.extensions import db


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


def _register(client, email, rol, password="secret123"):
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


def _headers(client, email, rol, password="secret123"):
    _register(client, email, rol, password)
    return {"Authorization": f"Bearer {_login(client, email, password)['access_token']}"}


def _crear_solicitud(client, headers, **extra):
    payload = {
        "titulo": "Chamba de prueba",
        "categoria": "gastronomia",
        "descripcion": "Necesito apoyo en el local",
        "ubicacion": "Medellin",
    }
    payload.update(extra)
    return client.post("/api/v1/solicitudes/", json=payload, headers=headers)


# ── Merchant publica chambas ────────────────────────────────────────────

def test_merchant_publica_chamba_ok(client):
    """Merchant puede publicar una solicitud → 201."""
    h = _headers(client, "m_pub@test.com", rol="merchant")
    resp = _crear_solicitud(client, h)
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["estado"] == "publicado"
    assert d["titulo"] == "Chamba de prueba"


def test_merchant_publica_con_presupuesto(client):
    """Merchant publica con presupuesto válido → 201."""
    h = _headers(client, "m_pres@test.com", rol="merchant")
    resp = _crear_solicitud(client, h, presupuesto=120000)
    assert resp.status_code == 201
    assert resp.get_json()["presupuesto"] == 120000


def test_merchant_publica_presupuesto_bajo_400(client):
    """Merchant con presupuesto < 50000 → 400 (misma regla que solicitante)."""
    h = _headers(client, "m_low@test.com", rol="merchant")
    resp = _crear_solicitud(client, h, presupuesto=1000)
    assert resp.status_code == 400


def test_pds_no_puede_publicar(client):
    """PDS sigue sin poder publicar → 403 (contrato intacto)."""
    h = _headers(client, "pds_no@test.com", rol="pds")
    resp = _crear_solicitud(client, h)
    assert resp.status_code == 403


# ── Aislamiento: merchant NO modifica solicitud ajena ───────────────────

def test_merchant_no_modifica_solicitud_ajena(client):
    """Merchant no puede cambiar el estado de una solicitud de otro → 403."""
    h_own = _headers(client, "m_own@test.com", rol="merchant")
    h_other = _headers(client, "m_other@test.com", rol="merchant")
    resp = _crear_solicitud(client, h_own)
    sid = resp.get_json()["id"]

    r = client.patch(
        f"/api/v1/solicitudes/{sid}/estado",
        json={"estado": "cancelado"},
        headers=h_other,
    )
    assert r.status_code == 403


def test_merchant_si_modifica_su_solicitud(client):
    """Merchant sí puede cambiar el estado de su propia solicitud → 200."""
    h = _headers(client, "m_self@test.com", rol="merchant")
    resp = _crear_solicitud(client, h)
    sid = resp.get_json()["id"]

    r = client.patch(
        f"/api/v1/solicitudes/{sid}/estado",
        json={"estado": "cancelado"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.get_json()["estado"] == "cancelado"


# ── Listado correcto para ambos roles ───────────────────────────────────

def test_listado_mezcla_solicitante_y_merchant(client):
    """GET /solicitudes/ lista chambas de solicitantes y merchants."""
    h_sol = _headers(client, "s_list@test.com", rol="solicitante")
    h_mer = _headers(client, "m_list@test.com", rol="merchant")
    _crear_solicitud(client, h_sol, titulo="Chamba solicitante")
    _crear_solicitud(client, h_mer, titulo="Chamba merchant")

    items = client.get("/api/v1/solicitudes/").get_json()
    titulos = {it["titulo"] for it in items}
    assert "Chamba solicitante" in titulos
    assert "Chamba merchant" in titulos


def test_detalle_merchant_ve_coords_de_su_chamba(client):
    """El merchant dueño ve las coordenadas de su propia chamba."""
    h = _headers(client, "m_coord@test.com", rol="merchant")
    resp = _crear_solicitud(
        client, h, latitud=6.2138, longitud=-75.5689, direccion="El Poblado"
    )
    sid = resp.get_json()["id"]

    det = client.get(f"/api/v1/solicitudes/{sid}", headers=h).get_json()
    assert det["latitud"] == 6.2138
    assert det["longitud"] == -75.5689
    assert det["direccion"] == "El Poblado"