"""pytest suite — ofertas (negociación pds/solicitante).

Convenciones del repo: pds = rol 'pds', solicitante = rol 'solicitante'
(dueño vía Solicitud.solicitante_id). El enum RolUsuario usa PDS/SOLICITANTE.
"""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.contract import Contract


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


def _crear_solicitud(client, headers):
    resp = client.post(
        "/api/v1/solicitudes/",
        json={
            "titulo": "Armar mueble",
            "categoria": "carpinteria",
            "descripcion": "armar mueble",
            "ubicacion": "Valledupar",
        },
        headers=headers,
    )
    return resp.get_json()["id"]


# ---------------- pds crea oferta en solicitud ajena ----------------
def test_pds_crea_oferta_ajena_201(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000, "mensaje": "lo hago"},
        headers=pds_h,
    )
    assert resp.status_code == 201
    d = resp.get_json()
    assert d["estado"] == "pendiente"
    assert d["pds_id"] == 2  # pds es el 2º usuario registrado
    assert d["solicitud_id"] == sid


# ---------------- la oferta queda en el hilo de chat ----------------
def test_oferta_crea_conversacion_con_mensaje_estructurado(client):
    """La oferta del PDS aparece en el chat con el solicitante."""
    import json

    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)

    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 120000, "mensaje": "lo hago hoy"},
        headers=pds_h,
    )
    assert resp.status_code == 201
    oferta = resp.get_json()

    convs = client.get("/api/v1/chat/conversations", headers=emp_h).get_json()
    assert len(convs) == 1
    conv_id = convs[0]["id"]

    mensajes = client.get(
        f"/api/v1/chat/conversations/{conv_id}/messages", headers=emp_h
    ).get_json()
    assert len(mensajes) == 1
    contenido = mensajes[0]["contenido"]
    assert contenido.startswith("⟦c:oferta⟧")
    payload = json.loads(contenido.split("⟧", 1)[1])
    assert payload["ofertaId"] == oferta["id"]
    assert payload["monto"] == 120000
    assert payload["mensaje"] == "lo hago hoy"


# ---------------- dueño (solicitante) NO oferta en su propia solicitud ----------------
def test_dueno_no_oferta_propia_403(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    sid = _crear_solicitud(client, emp_h)  # solicitante es dueño
    resp = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=emp_h,
    )
    assert resp.status_code == 403


# ---------------- solicitante lista ofertas de su solicitud ----------------
def test_solicitante_lista_ofertas_200(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    )
    resp = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=emp_h)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


# ---------------- no participante lista ofertas -> 403 ----------------
def test_no_participante_lista_403(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    outsider_h = _user(client, "out@example.com", rol="solicitante")
    sid = _crear_solicitud(client, emp_h)
    client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    )
    resp = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=outsider_h)
    assert resp.status_code == 403


# ---------------- solicitante acepta oferta ----------------
def test_solicitante_acepta_crea_order_y_rechaza_otras(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds1_h = _user(client, "pds1@example.com", rol="pds")
    pds2_h = _user(client, "pds2@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)

    o1 = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds1_h,
    ).get_json()
    o2 = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 90000},
        headers=pds2_h,
    ).get_json()

    resp = client.post(
        f"/api/v1/ofertas/{o1['id']}/responder",
        json={"accion": "aceptar"},
        headers=emp_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "aceptada"

    # Order creada
    orders = client.get("/api/v1/contracts/mine", headers=emp_h).get_json()
    assert len(orders) == 1
    assert orders[0]["proveedor_id"] == o1["pds_id"]
    assert orders[0]["solicitante_id"] == 1
    assert orders[0]["service_id"] == sid
    assert orders[0]["estado"] == "pendiente"

    # La solicitud SIGUE publicada: pasa a "en curso" (asignada) solo cuando
    # el contrato se firma (PATCH /contracts/<id>/estado → aceptar).
    svc = client.get(f"/api/v1/solicitudes/{sid}").get_json()
    assert svc["estado"] == "publicado"

    # La otra oferta queda 'rechazada'
    lista = client.get(f"/api/v1/solicitudes/{sid}/ofertas", headers=emp_h).get_json()
    estados = {o["id"]: o["estado"] for o in lista}
    assert estados[o1["id"]] == "aceptada"
    assert estados[o2["id"]] == "rechazada"


# ---------------- contraofertar + pds acepta contraoferta ----------------
def test_contraofertar_y_pds_acepta_contraoferta(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]

    # solicitante contraoferta
    r1 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 95000, "contra_mensaje": "bajo"},
        headers=emp_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "contraoferta"
    assert r1.get_json()["contra_monto"] == 95000

    # pds acepta contraoferta
    r2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar_contraoferta"},
        headers=pds_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["estado"] == "aceptada"

    # El monto de la contraoferta se convierte en el nuevo precio de la
    # solicitud (y por tanto del contrato).
    sol = client.get(f"/api/v1/solicitudes/{sid}", headers=emp_h).get_json()
    assert sol["presupuesto"] == 95000

    orders = client.get("/api/v1/contracts/mine", headers=emp_h).get_json()
    assert len(orders) == 1
    assert orders[0]["service"]["presupuesto"] == 95000


# ---------------- negociación "a convenir": PDS contra-contraoferta ----------------
def test_pds_contracontraoferta_y_solicitante_acepta(client):
    """El PDS ajusta el precio cuando el solicitante contraofertó y el
    solicitante acepta el nuevo valor (chat de negociación)."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)

    # Oferta inicial del PDS: define el precio de una chamba "a convenir".
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 120000},
        headers=pds_h,
    ).get_json()["id"]

    # Solicitante contraoferta a 90000.
    r1 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 90000, "contra_mensaje": "muy alto"},
        headers=emp_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["estado"] == "contraoferta"

    # PDS contra-contraoferta a 100000 (ajuste en el chat).
    r2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 100000, "contra_mensaje": "por materiales"},
        headers=pds_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["estado"] == "contraoferta"
    assert r2.get_json()["contra_monto"] == 100000

    # Solicitante acepta la contra-contraoferta: el acordado es el nuevo monto.
    r3 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=emp_h,
    )
    assert r3.status_code == 200
    assert r3.get_json()["estado"] == "aceptada"
    sol = client.get(f"/api/v1/solicitudes/{sid}", headers=emp_h).get_json()
    assert sol["presupuesto"] == 100000


def test_pds_rechaza_contraoferta_403_otro(client):
    """El PDS puede rechazar una contraoferta; otro usuario no."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    otro_h = _user(client, "otro@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]
    client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 80000},
        headers=emp_h,
    )
    # Un pds ajeno no puede rechazar.
    r_otro = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "rechazar"},
        headers=otro_h,
    )
    assert r_otro.status_code == 403
    # El pds dueño de la oferta sí.
    r_pds = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "rechazar"},
        headers=pds_h,
    )
    assert r_pds.status_code == 200
    assert r_pds.get_json()["estado"] == "rechazada"


# ---------------- oferta concreta los parámetros "a convenir" ----------------
def test_oferta_concreta_fecha_y_horario(client):
    """La oferta define fecha y horario cuando la solicitud los dejó "a
    convenir"; al aceptarla se escriben en la solicitud."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)

    oferta = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={
            "monto": 150000,
            "fecha_deseada": "2026-10-05",
            "horario": "Mañana (6:00 - 12:00)",
        },
        headers=pds_h,
    ).get_json()
    assert oferta["fecha_deseada"] == "2026-10-05"
    assert oferta["horario"] == "Mañana (6:00 - 12:00)"

    r = client.post(
        f"/api/v1/ofertas/{oferta['id']}/responder",
        json={"accion": "aceptar"},
        headers=emp_h,
    )
    assert r.status_code == 200
    sol = client.get(f"/api/v1/solicitudes/{sid}", headers=emp_h).get_json()
    assert sol["fecha_deseada"] == "2026-10-05"
    assert sol["horario"] == "Mañana (6:00 - 12:00)"
    assert sol["presupuesto"] == 150000


def test_contraoferta_ajusta_fecha_y_horario(client):
    """La contraoferta del chat puede ajustar fecha/horario; al aceptarla
    esos valores negociados tienen prioridad sobre la oferta."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000, "fecha_deseada": "2026-10-05"},
        headers=pds_h,
    ).get_json()["id"]

    r1 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={
            "accion": "contraofertar",
            "contra_monto": 95000,
            "fecha_deseada": "2026-10-08",
            "horario": "Tarde (12:00 - 18:00)",
        },
        headers=emp_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["contra_fecha_deseada"] == "2026-10-08"
    assert r1.get_json()["contra_horario"] == "Tarde (12:00 - 18:00)"

    r2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar_contraoferta"},
        headers=pds_h,
    )
    assert r2.status_code == 200
    sol = client.get(f"/api/v1/solicitudes/{sid}", headers=emp_h).get_json()
    assert sol["fecha_deseada"] == "2026-10-08"
    assert sol["horario"] == "Tarde (12:00 - 18:00)"
    assert sol["presupuesto"] == 95000


# ---------------- aceptación bilateral: cada parte acepta ----------------
def test_pds_acepta_su_oferta_queda_pendiente_el_solicitante(client):
    """El pds puede aceptar su propia propuesta, pero el acuerdo (y el
    contrato) queda pendiente hasta que el solicitante acepte también."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]

    resp = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=pds_h,
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["estado"] == "pendiente"
    assert d["aceptada_por_pds"] is True
    assert d["aceptada_por_solicitante"] is False
    # Todavía no hay contrato: falta la aceptación del solicitante.
    orders = client.get("/api/v1/contracts/mine", headers=pds_h).get_json()
    assert len(orders) == 0

    # El solicitante acepta: ahora sí hay acuerdo y contrato.
    resp2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=emp_h,
    )
    assert resp2.status_code == 200
    d2 = resp2.get_json()
    assert d2["estado"] == "aceptada"
    assert d2["aceptada_por_solicitante"] is True
    assert d2["monto_final"] == 100000

    orders = client.get("/api/v1/contracts/mine", headers=emp_h).get_json()
    assert len(orders) == 1
    assert orders[0]["monto"] == 100000
    assert orders[0]["estado"] == "pendiente"


def test_contraoferta_actualiza_solicitud_y_contrato(client):
    """La contraoferta del solicitante queda registrada y, al aceptar el pds,
    el valor final viaja a la solicitud y al contrato."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]

    r1 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "contraofertar", "contra_monto": 80000},
        headers=emp_h,
    )
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["contra_autor"] == "solicitante"
    assert d1["aceptada_por_solicitante"] is True
    assert d1["aceptada_por_pds"] is False
    # La solicitud todavía NO cambia de precio: el valor final se fija al
    # cerrar el acuerdo.
    sol = client.get(f"/api/v1/solicitudes/{sid}", headers=emp_h).get_json()
    assert sol["presupuesto"] is None

    r2 = client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=pds_h,
    )
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert d2["estado"] == "aceptada"
    assert d2["monto_final"] == 80000

    sol = client.get(f"/api/v1/solicitudes/{sid}", headers=emp_h).get_json()
    assert sol["presupuesto"] == 80000

    orders = client.get("/api/v1/contracts/mine", headers=emp_h).get_json()
    assert len(orders) == 1
    assert orders[0]["monto"] == 80000


def test_condiciones_se_guandan_y_pasan_al_contrato(client):
    """Las condiciones acordadas se guardan en la oferta y llegan al contrato."""
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]

    r = client.post(
        f"/api/v1/ofertas/{oid}/condiciones",
        json={"texto": "Incluye materiales", "autor": "solicitante"},
        headers=emp_h,
    )
    assert r.status_code == 200
    condiciones = r.get_json()["condiciones"]
    assert len(condiciones) == 1
    assert condiciones[0]["texto"] == "Incluye materiales"

    client.post(
        f"/api/v1/ofertas/{oid}/responder",
        json={"accion": "aceptar"},
        headers=emp_h,
    )
    orders = client.get("/api/v1/contracts/mine", headers=emp_h).get_json()
    assert len(orders) == 1
    assert len(orders[0]["condiciones"]) == 1
    assert orders[0]["condiciones"][0]["texto"] == "Incluye materiales"


def test_usuario_ajeno_no_agrega_condiciones_403(client):
    emp_h = _user(client, "emp@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    otro_h = _user(client, "otro@example.com", rol="solicitante")
    sid = _crear_solicitud(client, emp_h)
    oid = client.post(
        f"/api/v1/solicitudes/{sid}/ofertas",
        json={"monto": 100000},
        headers=pds_h,
    ).get_json()["id"]
    resp = client.post(
        f"/api/v1/ofertas/{oid}/condiciones",
        json={"texto": "No soy parte"},
        headers=otro_h,
    )
    assert resp.status_code == 403
