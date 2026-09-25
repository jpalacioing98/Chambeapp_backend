"""pytest suite — Maraña (rebusque): adenda derivada de una chamba."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.chamba import Chamba
from app.models.marana import Marana, EstadoMarana

LAT_VALLEDUPAR = 10.4806
LNG_VALLEDUPAR = -73.2495


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


def _register(client, email, rol="pds"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "rol": rol, "acepto_tyc": True, "ip": "127.0.0.1"},
    )


def _login(client, email):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": "secret123"}
    ).get_json()


def _headers(client, email):
    return {"Authorization": f"Bearer {_login(client, email)['access_token']}"}


def _user_id(app, email):
    with app.app_context():
        from app.models.user import User
        return User.query.filter_by(email=email).first().id


def _chamba_activa(client, app):
    """Solicitante + pds + contrato firmado + chamba en ejecución con adenda."""
    _register(client, "sol@example.com", rol="solicitante")
    _register(client, "pds@example.com", rol="pds")
    _register(client, "pds2@example.com", rol="pds")
    sol_h = _headers(client, "sol@example.com")
    pds_h = _headers(client, "pds@example.com")

    sid = client.post(
        "/api/v1/solicitudes/",
        json={"titulo": "Maraña base", "categoria": "plomeria", "descripcion": "x",
              "ubicacion": "Valledupar", "latitud": LAT_VALLEDUPAR, "longitud": LNG_VALLEDUPAR},
        headers=sol_h,
    ).get_json()["id"]
    pds_id = _user_id(app, "pds@example.com")
    cid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": pds_id},
        headers=sol_h,
    ).get_json()["id"]
    client.patch(f"/api/v1/contracts/{cid}/estado", json={"estado": "aceptar"}, headers=pds_h)

    with app.app_context():
        chamba = Chamba.query.filter_by(contract_id=cid).first()
        chamba.estado = "en_ejecucion"
        chamba.adendas = [{"fecha": "2026-09-21T12:00:00Z", "descripcion": "Cambio de tubería",
                           "monto_extra": 25000, "tiempo_extra": 30}]
        db.session.commit()
        chid = chamba.id
    return client, app, sol_h, pds_h, chid


def _crear_marana(client, sol_h, chid):
    resp = client.post(
        f"/api/v1/chambas/{chid}/marana",
        json={
            "adenda_idx": 0,
            "titulo": "Cambio de tubería del baño",
            "categoria": "electricidad",
            "descripcion": "Trabajo extra de otro perfil",
            "presupuesto": 25000,
        },
        headers=sol_h,
    )
    assert resp.status_code == 201
    return resp.get_json()


# ---------------- Creación desde adenda ----------------
def test_crear_marana_desde_adenda(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    assert marana["estado"] == "publicado"
    assert marana["chamba_id"] == chid
    assert marana["presupuesto"] == 25000

    # La adenda quedó derivada y su monto SE MOVIÓ (no se cobra dos veces).
    detalle = client.get(f"/api/v1/chambas/{chid}", headers=sol_h).get_json()
    adenda = detalle["adendas"][0]
    assert adenda["derivada"] is True
    assert adenda["marana_id"] == marana["id"]
    assert adenda["monto_extra"] is None


def test_crear_marana_solo_solicitante(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    resp = client.post(
        f"/api/v1/chambas/{chid}/marana",
        json={"adenda_idx": 0, "titulo": "Cambio", "categoria": "yeso", "descripcion": "Trabajo extra de otro perfil"},
        headers=pds_h,
    )
    assert resp.status_code == 403


def test_crear_marana_adenda_ya_derivada(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    _crear_marana(client, sol_h, chid)
    resp = client.post(
        f"/api/v1/chambas/{chid}/marana",
        json={"adenda_idx": 0, "titulo": "Cambio", "categoria": "yeso", "descripcion": "Trabajo extra de otro perfil"},
        headers=sol_h,
    )
    assert resp.status_code == 400


def test_crear_marana_presupuesto_default_desde_adenda(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    resp = client.post(
        f"/api/v1/chambas/{chid}/marana",
        json={"adenda_idx": 0, "titulo": "Cambio", "categoria": "yeso", "descripcion": "Trabajo extra de otro perfil"},
        headers=sol_h,
    )
    assert resp.status_code == 201
    # Sin presupuesto explícito: toma el monto_extra de la adenda.
    assert resp.get_json()["presupuesto"] == 25000


# ---------------- Feed y postulación ----------------
def test_feed_solo_publicadas_y_filtro(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    m1 = _crear_marana(client, sol_h, chid)
    feed = client.get("/api/v1/maranas/?categoria=electricidad", headers=pds_h)
    assert feed.status_code == 200
    assert len(feed.get_json()) == 1
    assert feed.get_json()[0]["id"] == m1["id"]


def test_postular_y_listar_ofertas(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    pds2_h = _headers(client, "pds2@example.com")
    oferta = client.post(
        f"/api/v1/maranas/{marana['id']}/ofertas",
        json={"monto": 30000, "mensaje": "Lo hago"},
        headers=pds2_h,
    )
    assert oferta.status_code == 201
    assert oferta.get_json()["estado"] == "pendiente"

    ofertas = client.get(f"/api/v1/maranas/{marana['id']}/ofertas", headers=sol_h)
    assert ofertas.status_code == 200
    assert len(ofertas.get_json()) == 1


def test_postulacion_duplicada(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    pds2_h = _headers(client, "pds2@example.com")
    client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 30000}, headers=pds2_h)
    resp = client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 40000}, headers=pds2_h)
    assert resp.status_code == 400


def test_no_se_postula_en_marana_asignada(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    pds2_h = _headers(client, "pds2@example.com")
    client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 30000}, headers=pds2_h)
    oferta_id = client.get(f"/api/v1/maranas/{marana['id']}/ofertas", headers=sol_h).get_json()[0]["id"]
    client.post(
        f"/api/v1/maranas/{marana['id']}/responder?oferta_id={oferta_id}",
        json={"accion": "aceptar"},
        headers=sol_h,
    )
    resp = client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 50000}, headers=pds_h)
    assert resp.status_code == 400


# ---------------- Negociación y asignación ----------------
def test_aceptar_asigna_y_rechaza_resto(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    pds2_h = _headers(client, "pds2@example.com")
    client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 30000}, headers=pds2_h)
    client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 35000}, headers=pds_h)

    ofertas = client.get(f"/api/v1/maranas/{marana['id']}/ofertas", headers=sol_h).get_json()
    oferta_ganadora = next(o for o in ofertas if o["monto"] == 35000)

    resp = client.post(
        f"/api/v1/maranas/{marana['id']}/responder?oferta_id={oferta_ganadora['id']}",
        json={"accion": "aceptar"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    detalle = client.get(f"/api/v1/maranas/{marana['id']}", headers=pds_h).get_json()
    assert detalle["estado"] == "asignado"
    assert detalle["pds_asignado_id"] == _user_id(app, "pds@example.com")
    assert detalle["presupuesto"] == 35000

    ofertas2 = client.get(f"/api/v1/maranas/{marana['id']}/ofertas", headers=sol_h).get_json()
    estados = {o["id"]: o["estado"] for o in ofertas2}
    assert estados[oferta_ganadora["id"]] == "aceptada"
    assert sum(1 for e in estados.values() if e == "rechazada") == 1


def test_contraoferta_y_aceptar_contraoferta(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    pds2_h = _headers(client, "pds2@example.com")
    client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 40000}, headers=pds2_h)
    oferta_id = client.get(f"/api/v1/maranas/{marana['id']}/ofertas", headers=sol_h).get_json()[0]["id"]

    # Solicitante contraoferta.
    r1 = client.post(
        f"/api/v1/maranas/{marana['id']}/responder?oferta_id={oferta_id}",
        json={"accion": "contraofertar", "contra_monto": 32000},
        headers=sol_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "contraoferta"

    # PDS acepta la contraoferta → asignada con el monto negociado.
    r2 = client.post(
        f"/api/v1/maranas/{marana['id']}/responder?oferta_id={oferta_id}",
        json={"accion": "aceptar_contraoferta"},
        headers=pds2_h,
    )
    assert r2.status_code == 200
    detalle = client.get(f"/api/v1/maranas/{marana['id']}", headers=sol_h).get_json()
    assert detalle["estado"] == "asignado"
    assert detalle["presupuesto"] == 32000


# ---------------- Completar, pago dual y cancelar ----------------
def _marana_asignada(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    marana = _crear_marana(client, sol_h, chid)
    pds2_h = _headers(client, "pds2@example.com")
    client.post(f"/api/v1/maranas/{marana['id']}/ofertas", json={"monto": 30000}, headers=pds2_h)
    oferta_id = client.get(f"/api/v1/maranas/{marana['id']}/ofertas", headers=sol_h).get_json()[0]["id"]
    client.post(
        f"/api/v1/maranas/{marana['id']}/responder?oferta_id={oferta_id}",
        json={"accion": "aceptar"},
        headers=sol_h,
    )
    return client, sol_h, pds2_h, marana["id"]


def test_completar_y_pago_dual(client, app):
    client, sol_h, pds2_h, mid = _marana_asignada(client, app)

    r1 = client.patch(f"/api/v1/maranas/{mid}/estado", json={"accion": "completar"}, headers=pds2_h)
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "completado"
    assert r1.get_json()["fecha_entrega"] is not None

    # Solo una parte confirma: sigue completado.
    r2 = client.post(f"/api/v1/maranas/{mid}/pago", json={"monto_final": 30000}, headers=sol_h)
    assert r2.status_code == 200
    assert r2.get_json()["pago_confirmado_solicitante"] is True
    assert r2.get_json()["estado"] == "completado"

    # Segunda confirmación → PAGADO.
    r3 = client.post(f"/api/v1/maranas/{mid}/pago", json={}, headers=pds2_h)
    assert r3.status_code == 200
    assert r3.get_json()["estado"] == "pagado"
    assert r3.get_json()["pago_monto_final"] == 30000
    assert r3.get_json()["fecha_pago"] is not None


def test_pago_solo_tras_entrega(client, app):
    client, sol_h, pds2_h, mid = _marana_asignada(client, app)
    resp = client.post(f"/api/v1/maranas/{mid}/pago", json={"monto_final": 30000}, headers=sol_h)
    assert resp.status_code == 400


def test_completar_solo_pds_asignado(client, app):
    client, sol_h, pds2_h, mid = _marana_asignada(client, app)
    pds_original_h = _headers(client, "pds@example.com")
    resp = client.patch(f"/api/v1/maranas/{mid}/estado", json={"accion": "completar"}, headers=pds_original_h)
    assert resp.status_code == 403


def test_cancelar_marana(client, app):
    client, sol_h, pds2_h, mid = _marana_asignada(client, app)
    resp = client.patch(f"/api/v1/maranas/{mid}/estado", json={"accion": "cancelar"}, headers=sol_h)
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "cancelado"


# ---------------- Listados por rol ----------------
def test_listado_maranas_de_chamba(client, app):
    client, app, sol_h, pds_h, chid = _chamba_activa(client, app)
    m = _crear_marana(client, sol_h, chid)
    lista = client.get(f"/api/v1/maranas/chamba/{chid}", headers=sol_h)
    assert lista.status_code == 200
    assert len(lista.get_json()) == 1
    assert lista.get_json()[0]["id"] == m["id"]
    # El prestador de la chamba también las ve; un ajeno no.
    assert client.get(f"/api/v1/maranas/chamba/{chid}", headers=pds_h).status_code == 200
    ajeno_h = _headers(client, "pds2@example.com")
    assert client.get(f"/api/v1/maranas/chamba/{chid}", headers=ajeno_h).status_code == 403


def test_listados_rol(client, app):
    client, sol_h, pds2_h, mid = _marana_asignada(client, app)
    sol_id = _user_id(app, "sol@example.com")
    pds2_id = _user_id(app, "pds2@example.com")

    sol_lista = client.get(f"/api/v1/maranas/solicitante/{sol_id}", headers=sol_h)
    assert sol_lista.status_code == 200
    assert len(sol_lista.get_json()) == 1

    pds_lista = client.get(f"/api/v1/maranas/prestador/{pds2_id}?estado=asignado", headers=pds2_h)
    assert pds_lista.status_code == 200
    assert len(pds_lista.get_json()) == 1
    assert pds_lista.get_json()[0]["estado"] == "asignado"

    ajeno = client.get(f"/api/v1/maranas/prestador/{sol_id}", headers=pds2_h)
    assert ajeno.status_code == 403