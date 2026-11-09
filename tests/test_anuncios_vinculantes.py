"""pytest suite — Anuncios vinculantes (modalidad "contrato").

El negocio publica un anuncio con modalidad "contrato", un PDS se postula y
el negocio lo contrata: se genera un Contract vinculante que ambas partes
firman (y que activa la chamba).
"""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig


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


def _anuncio_contrato(client, neg_h, vacantes=1, titulo="Se busca plomero"):
    return client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": titulo,
            "descripcion": "Mantenimiento mensual del local.",
            "categoria": "plomeria",
            "ubicacion": "Valledupar",
            "vacantes": vacantes,
            "modalidad": "contrato",
            "presupuesto": 120000,
            "fecha_deseada": "2026-12-01",
            "horario": "Mañana (6:00 - 12:00)",
        },
        headers=neg_h,
    ).get_json()


def _anuncio_contacto(client, neg_h):
    return client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "Se busca electricista",
            "descripcion": "Arreglo eléctrico puntual.",
            "categoria": "electricidad",
            "ubicacion": "Valledupar",
            "vacantes": 1,
        },
        headers=neg_h,
    ).get_json()


def _postular(client, pds_h, anuncio_id):
    return client.post(
        f"/api/v1/anuncios/{anuncio_id}/postulaciones",
        json={"mensaje": "Disponible"},
        headers=pds_h,
    ).get_json()


# ---------------- Creación ----------------
def test_crear_anuncio_vinculante(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    anuncio = _anuncio_contrato(client, neg_h)
    assert anuncio["modalidad"] == "contrato"
    assert anuncio["presupuesto"] == 120000
    assert anuncio["fecha_deseada"] == "2026-12-01"
    assert anuncio["horario"] == "Mañana (6:00 - 12:00)"
    assert anuncio["estado"] == "publicado"
    assert anuncio["vacantes_disponibles"] == 1


def test_anuncio_sin_modalidad_es_contacto(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    anuncio = _anuncio_contacto(client, neg_h)
    assert anuncio["modalidad"] == "contacto"
    assert anuncio["presupuesto"] is None


def test_anuncio_contrato_sin_presupuesto_falla(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    resp = client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "Se busca plomero",
            "descripcion": "Mantenimiento",
            "categoria": "plomeria",
            "modalidad": "contrato",
        },
        headers=neg_h,
    )
    assert resp.status_code == 400


def test_anuncio_contrato_con_presupuesto_bajo_falla(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    resp = client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "Se busca plomero",
            "descripcion": "Mantenimiento",
            "categoria": "plomeria",
            "modalidad": "contrato",
            "presupuesto": 10000,
        },
        headers=neg_h,
    )
    assert resp.status_code == 400


def test_modalidad_invalida_falla(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    resp = client.post(
        "/api/v1/anuncios/",
        json={
            "titulo": "Se busca plomero",
            "descripcion": "Mantenimiento",
            "categoria": "plomeria",
            "modalidad": "otro",
        },
        headers=neg_h,
    )
    assert resp.status_code == 422


# ---------------- Postulación ----------------
def test_pds_postula_a_anuncio_vinculante(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)

    postulacion = _postular(client, pds_h, anuncio["id"])
    assert postulacion["estado"] == "pendiente"
    assert postulacion["contract_id"] is None


# ---------------- Contratación ----------------
def test_merchant_contrata_crea_contract(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])

    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert resp.status_code == 201
    contrato = resp.get_json()
    assert contrato["estado"] == "pendiente"
    assert contrato["proveedor_id"] == 2  # pds
    assert contrato["solicitante_id"] == 1  # negocio
    assert contrato["monto"] == 120000
    assert contrato["fecha_deseada"] == "2026-12-01"
    assert contrato["horario"] == "Mañana (6:00 - 12:00)"

    # El contrato es visible para ambas partes.
    del_pds = client.get("/api/v1/contracts/mine", headers=pds_h).get_json()
    del_negocio = client.get("/api/v1/contracts/mine", headers=neg_h).get_json()
    assert len(del_pds) == 1
    assert len(del_negocio) == 1
    assert del_pds[0]["id"] == contrato["id"]


def test_postulacion_queda_contratada(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])

    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )

    lista = client.get(f"/api/v1/anuncios/{anuncio['id']}/postulaciones", headers=neg_h)
    body = lista.get_json()[0]
    assert body["estado"] == "contratado"
    assert body["contract_id"] is not None


def test_contratar_actualiza_vacantes_y_cierra_anuncio(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h, vacantes=1)
    postulacion = _postular(client, pds_h, anuncio["id"])

    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )

    detalle = client.get(f"/api/v1/anuncios/{anuncio['id']}", headers=neg_h).get_json()
    assert detalle["vacantes_disponibles"] == 0
    # Al agotar el único vacante el anuncio se cierra.
    assert detalle["estado"] == "cerrado"


def test_vacantes_multiples_generan_contratos_separados(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds1_h = _user(client, "pds1@example.com", rol="pds")
    pds2_h = _user(client, "pds2@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h, vacantes=2)

    p1 = _postular(client, pds1_h, anuncio["id"])
    p2 = _postular(client, pds2_h, anuncio["id"])

    r1 = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{p1['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert r1.status_code == 201

    detalle = client.get(f"/api/v1/anuncios/{anuncio['id']}", headers=neg_h).get_json()
    assert detalle["vacantes_disponibles"] == 1
    assert detalle["estado"] == "publicado"

    r2 = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{p2['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert r2.status_code == 201
    assert r1.get_json()["id"] != r2.get_json()["id"]

    detalle2 = client.get(f"/api/v1/anuncios/{anuncio['id']}", headers=neg_h).get_json()
    assert detalle2["vacantes_disponibles"] == 0
    assert detalle2["estado"] == "cerrado"

    contratos = client.get(f"/api/v1/anuncios/{anuncio['id']}/contratos", headers=neg_h)
    assert len(contratos.get_json()) == 2


def test_no_se_puede_contratar_sin_vacantes(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds1_h = _user(client, "pds1@example.com", rol="pds")
    pds2_h = _user(client, "pds2@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h, vacantes=1)
    p1 = _postular(client, pds1_h, anuncio["id"])
    p2 = _postular(client, pds2_h, anuncio["id"])

    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{p1['id']}/contratar",
        json={},
        headers=neg_h,
    )
    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{p2['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert resp.status_code == 400


def test_no_se_puede_contratar_dos_veces_al_mismo_postulante(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h, vacantes=2)
    postulacion = _postular(client, pds_h, anuncio["id"])

    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )
    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert resp.status_code == 400


def test_contratar_anuncio_de_contacto_falla(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contacto(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])

    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert resp.status_code == 400


def test_solo_el_dueno_contrata(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    neg2_h = _user(client, "neg2@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])

    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg2_h,
    )
    assert resp.status_code == 403


def test_postulacion_de_otro_anuncio_falla(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio_a = _anuncio_contrato(client, neg_h, titulo="Anuncio A")
    anuncio_b = _anuncio_contrato(client, neg_h, titulo="Anuncio B")
    postulacion = _postular(client, pds_h, anuncio_a["id"])

    resp = client.post(
        f"/api/v1/anuncios/{anuncio_b['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )
    assert resp.status_code == 400


def test_contratar_con_monto_personalizado(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])

    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={"monto": 135000, "condiciones": ["Incluye materiales"]},
        headers=neg_h,
    )
    assert resp.status_code == 201
    contrato = resp.get_json()
    assert contrato["monto"] == 135000
    textos = [c["texto"] for c in contrato["condiciones"]]
    assert "Incluye materiales" in textos


# ---------------- Firma del contrato generado ----------------
def test_firmas_activan_el_contrato_y_crean_chamba(client, app):
    from app.models.chamba import Chamba

    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])

    cid = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    ).get_json()["id"]

    # Firma el negocio (solicitante del contrato).
    r1 = client.patch(
        f"/api/v1/contracts/{cid}/estado",
        json={"estado": "aceptar", "firma": {"nombre": "Negocio"}},
        headers=neg_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["firma_solicitante"] is True

    # Firma el PDS (proveedor): el contrato se activa.
    r2 = client.patch(
        f"/api/v1/contracts/{cid}/estado",
        json={"estado": "aceptar", "firma": {"nombre": "Prestador"}},
        headers=pds_h,
    )
    assert r2.status_code == 200
    d = r2.get_json()
    assert d["estado"] == "en_progreso"
    assert d["firma_proveedor"] is True
    assert d["firma_solicitante"] is True

    with app.app_context():
        assert Chamba.query.filter_by(contract_id=cid).first() is not None


def test_contrato_cerrado_no_admite_postulaciones(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h, vacantes=1)
    postulacion = _postular(client, pds_h, anuncio["id"])
    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )

    # El anuncio quedó cerrado: un nuevo postulante no puede entrar.
    resp = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones",
        json={},
        headers=pds_h,
    )
    assert resp.status_code == 400


# ---------------- Consulta de contratos ----------------
def test_negocio_consulta_contratos_de_su_anuncio(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])
    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )

    resp = client.get(f"/api/v1/anuncios/{anuncio['id']}/contratos", headers=neg_h)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_otro_negocio_no_consulta_contratos(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    neg2_h = _user(client, "neg2@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])
    client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    )

    resp = client.get(f"/api/v1/anuncios/{anuncio['id']}/contratos", headers=neg2_h)
    assert resp.status_code == 403


def test_anuncio_registra_contract_ids(client):
    neg_h = _user(client, "neg@example.com", rol="merchant")
    pds_h = _user(client, "pds@example.com", rol="pds")
    anuncio = _anuncio_contrato(client, neg_h)
    postulacion = _postular(client, pds_h, anuncio["id"])
    contrato = client.post(
        f"/api/v1/anuncios/{anuncio['id']}/postulaciones/{postulacion['id']}/contratar",
        json={},
        headers=neg_h,
    ).get_json()

    detalle = client.get(f"/api/v1/anuncios/{anuncio['id']}", headers=neg_h).get_json()
    assert detalle["contract_ids"] == [contrato["id"]]
