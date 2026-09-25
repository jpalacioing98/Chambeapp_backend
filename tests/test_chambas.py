"""pytest suite — Módulo de Gestión de Chamba (ciclo de vida de ejecución)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.chamba import Chamba
from app.models.contract import Contract

# Valledupar (para geo-validación).
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


def _user_id(app, email):
    with app.app_context():
        from app.models.user import User
        return User.query.filter_by(email=email).first().id


def _user(client, email, rol="pds"):
    _register(client, email=email, rol=rol)
    return _headers(client, email)


def _crear_servicio(client, headers, lat=None, lng=None):
    body = {
        "titulo": "Reparar grifo",
        "categoria": "plomeria",
        "descripcion": "arreglar",
        "ubicacion": "Valledupar",
    }
    if lat is not None:
        body["latitud"] = lat
        body["longitud"] = lng
    resp = client.post("/api/v1/solicitudes/", json=body, headers=headers)
    assert resp.status_code == 201
    return resp.get_json()["id"]


def _crear_contrato(client, app, solicitante_h, pds_email):
    sid = _crear_servicio(client, solicitante_h, lat=LAT_VALLEDUPAR, lng=LNG_VALLEDUPAR)
    pds_id = _user_id(app, pds_email)
    resp = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": pds_id},
        headers=solicitante_h,
    )
    assert resp.status_code == 201
    return resp.get_json()["id"]


def _crear_chamba(client, app, solicitante_h, pds_email):
    cid = _crear_contrato(client, app, solicitante_h, pds_email)
    resp = client.post("/api/v1/chambas/", json={"contract_id": cid}, headers=solicitante_h)
    assert resp.status_code == 201
    return resp.get_json()


# ---------------- Hito 1: creación de la chamba ----------------
def test_crear_chamba_ok(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    assert d["estado"] == "programada"
    assert d["evidencia_entrada"] == []
    assert d["adendas"] == []
    assert d["pago_directo_confirmado"] is False
    assert d["contract"]["solicitante_id"] == _user_id(app, "sol@example.com")


def test_crear_chamba_no_participante(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    other_h = _user(client, "other@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    cid = _crear_contrato(client, app, sol_h, "pds@example.com")
    resp = client.post("/api/v1/chambas/", json={"contract_id": cid}, headers=other_h)
    assert resp.status_code == 403


def test_crear_chamba_duplicada(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    _crear_chamba(client, app, sol_h, "pds@example.com")
    with app.app_context():
        cid = Contract.query.first().id
    resp = client.post("/api/v1/chambas/", json={"contract_id": cid}, headers=sol_h)
    assert resp.status_code == 400


def test_crear_chamba_contrato_inexistente(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    resp = client.post("/api/v1/chambas/", json={"contract_id": 9999}, headers=sol_h)
    assert resp.status_code == 404


# ---------------- Firma del contrato: solicitud en curso + chamba automática ----------------
def test_firma_contrato_activa_solicitud_y_genera_chamba(client, app):
    """Al aceptar el contrato (PDS firma), la solicitud pasa a 'asignada'
    (en curso) y la chamba se genera automáticamente (hito 1)."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    sid = _crear_servicio(client, sol_h, lat=LAT_VALLEDUPAR, lng=LNG_VALLEDUPAR)
    pds_id = _user_id(app, "pds@example.com")
    cid = client.post(
        "/api/v1/contracts/",
        json={"service_id": sid, "proveedor_id": pds_id},
        headers=sol_h,
    ).get_json()["id"]

    # Antes de firmar: la solicitud sigue publicada y no hay chamba.
    svc = client.get(f"/api/v1/solicitudes/{sid}").get_json()
    assert svc["estado"] == "publicado"
    resp_lista = client.get(f"/api/v1/chambas/prestador/{pds_id}", headers=pds_h)
    assert resp_lista.status_code == 200
    assert len(resp_lista.get_json()) == 0

    # El PDS firma el contrato.
    resp = client.patch(
        f"/api/v1/contracts/{cid}/estado",
        json={"estado": "aceptar"},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "en_progreso"

    # La solicitud pasa a "en curso" (asignada).
    svc = client.get(f"/api/v1/solicitudes/{sid}").get_json()
    assert svc["estado"] == "asignada"

    # La chamba se generó automáticamente (programada).
    with app.app_context():
        chamba = Chamba.query.filter_by(contract_id=cid).first()
        assert chamba is not None
        assert chamba.estado.value == "programada"
        assert chamba.fecha_activacion is not None
        chamba_id = chamba.id
    detalle = client.get(f"/api/v1/chambas/{chamba_id}", headers=sol_h)
    assert detalle.status_code == 200
    assert detalle.get_json()["contract_id"] == cid


def test_detalle_chamba_solo_participantes(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    other_h = _user(client, "other@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    ok = client.get(f"/api/v1/chambas/{d['id']}", headers=sol_h)
    assert ok.status_code == 200
    forbb = client.get(f"/api/v1/chambas/{d['id']}", headers=other_h)
    assert forbb.status_code == 403


# ---------------- Evidencia upload (base64 → MinIO → URL) ----------------
def test_upload_evidencia_ok(client, app, monkeypatch):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")

    class _FakeStorage:
        def upload_avatar(self, file_bytes, user_id, filename):
            return "http://minio:9000/chambeapp-portfolio/chamba-1/ev.jpg"

    monkeypatch.setattr("app.services.storage.storage", _FakeStorage())

    resp = client.post(
        "/api/v1/chambas/evidencia/upload",
        json={"archivo_base64": "aGVsbG8=", "nombre_archivo": "ev.jpg"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["url"].startswith("http://minio:9000/")


def test_upload_evidencia_base64_invalido(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    resp = client.post(
        "/api/v1/chambas/evidencia/upload",
        json={"archivo_base64": "no-es-base64!!"},
        headers=sol_h,
    )
    assert resp.status_code == 400


# ---------------- Hito 2: inicio de obra con geo-validación ----------------
def test_inicio_obra_sin_coordenadas(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_proceso"},
        headers=pds_h,
    )
    assert resp.status_code == 400


def test_inicio_obra_fuera_de_radio(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    # ~2 km al norte de Valledupar.
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_proceso", "latitud": LAT_VALLEDUPAR + 0.02, "longitud": LNG_VALLEDUPAR},
        headers=pds_h,
    )
    assert resp.status_code == 400


def test_inicio_obra_ok(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_proceso", "latitud": LAT_VALLEDUPAR, "longitud": LNG_VALLEDUPAR},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "en_proceso"
    assert resp.get_json()["fecha_inicio_obra"] is not None


def test_inicio_obra_solo_prestador(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_proceso", "latitud": LAT_VALLEDUPAR, "longitud": LNG_VALLEDUPAR},
        headers=sol_h,
    )
    assert resp.status_code == 403


def test_transicion_invalida(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    # saltarse hitos: programada → pendiente_validacion
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "pendiente_validacion"},
        headers=pds_h,
    )
    assert resp.status_code == 400


# ---------------- Hito 2/3: evidencia de entrada + ejecución ----------------
def _avanzar_a_ejecucion(client, app, sol_h, pds_h):
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_proceso", "latitud": LAT_VALLEDUPAR, "longitud": LNG_VALLEDUPAR},
        headers=pds_h,
    )
    return d


def test_evidencia_entrada_ok(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/evidencia-entrada",
        json={"urls": ["https://minio.chambeapp.co/chambas/1/entrada/foto1.jpg"]},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["evidencia_entrada"]) == 1


def test_evidencia_entrada_solo_prestador(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/evidencia-entrada",
        json={"urls": ["https://minio.chambeapp.co/x.jpg"]},
        headers=sol_h,
    )
    assert resp.status_code == 403


def test_pasar_a_ejecucion(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_ejecucion"},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "en_ejecucion"


# ---------------- Hito 3: adendas y novedades ----------------
def test_adenda_ok(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Cambio de grifo adicional", "monto_extra": 20000},
        headers=pds_h,
    )
    assert resp.status_code == 200
    adendas = resp.get_json()["adendas"]
    assert len(adendas) == 1
    assert adendas[0]["descripcion"] == "Cambio de grifo adicional"
    assert adendas[0]["monto_extra"] == 20000
    # Default: la cubre el prestador actual.
    assert adendas[0]["cubierta_por"] == "pds_actual"


def test_adenda_para_otro_perfil(client, app):
    """El solicitante marca si la adenda es para otro perfil (candidata a maraña)."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={
            "descripcion": "Cambio de tubería del baño",
            "monto_extra": 25000,
            "cubierta_por": "otro_pds",
            "categoria_requerida": "electricidad",
        },
        headers=sol_h,
    )
    assert resp.status_code == 200
    adenda = resp.get_json()["adendas"][0]
    assert adenda["cubierta_por"] == "otro_pds"
    assert adenda["categoria_requerida"] == "electricidad"


def test_adenda_tiempo_extra_con_unidad(client, app):
    """El tiempo extra es configurable en minutos/horas/días."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Ampliación de jornada", "tiempo_extra": 2, "tiempo_extra_unidad": "horas"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    adenda = resp.get_json()["adendas"][0]
    assert adenda["tiempo_extra"] == 2
    assert adenda["tiempo_extra_unidad"] == "horas"

    # Default: minutos.
    resp2 = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Ajuste menor", "tiempo_extra": 45},
        headers=sol_h,
    )
    assert resp2.status_code == 200
    assert resp2.get_json()["adendas"][1]["tiempo_extra_unidad"] == "minutos"

    # Unidad inválida → 422.
    resp3 = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "x", "tiempo_extra": 1, "tiempo_extra_unidad": "semanas"},
        headers=sol_h,
    )
    assert resp3.status_code == 422


def test_adenda_cubierta_por_invalido(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "x", "cubierta_por": "otra_cosa"},
        headers=sol_h,
    )
    assert resp.status_code == 422


def test_adenda_monto_negativo_422(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "x", "monto_extra": -5000},
        headers=sol_h,
    )
    assert resp.status_code == 422


def test_adenda_sugerida_por_pds(client, app):
    """El PDS propone trabajo de otro perfil: queda como SUGERENCIA."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={
            "descripcion": "Instalación eléctrica adicional",
            "cubierta_por": "otro_pds",
            "categoria_requerida": "electricidad",
        },
        headers=pds_h,
    )
    assert resp.status_code == 200
    adenda = resp.get_json()["adendas"][0]
    assert adenda["cubierta_por"] == "otro_pds"
    assert adenda["sugerida_por_pds"] is True


def test_editar_adenda_cobertura(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Cambio de tubería", "monto_extra": 20000},
        headers=sol_h,
    )
    # El solicitante cambia la cobertura a otro perfil.
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/adenda/0",
        json={"cubierta_por": "otro_pds", "categoria_requerida": "electricidad"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    adenda = resp.get_json()["adendas"][0]
    assert adenda["cubierta_por"] == "otro_pds"
    assert adenda["categoria_requerida"] == "electricidad"
    # El resto de campos se conserva.
    assert adenda["descripcion"] == "Cambio de tubería"
    assert adenda["monto_extra"] == 20000
    # El PDS no puede editar.
    r403 = client.patch(
        f"/api/v1/chambas/{d['id']}/adenda/0",
        json={"cubierta_por": "pds_actual"},
        headers=pds_h,
    )
    assert r403.status_code == 403


def test_eliminar_adenda(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Cambio de tubería", "monto_extra": 20000},
        headers=sol_h,
    )
    client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Pintura extra"},
        headers=sol_h,
    )
    resp = client.delete(f"/api/v1/chambas/{d['id']}/adenda/0", headers=sol_h)
    assert resp.status_code == 200
    assert len(resp.get_json()["adendas"]) == 1
    assert resp.get_json()["adendas"][0]["descripcion"] == "Pintura extra"
    # El PDS no puede eliminar.
    r403 = client.delete(f"/api/v1/chambas/{d['id']}/adenda/0", headers=pds_h)
    assert r403.status_code == 403


def test_no_editar_adenda_derivada(client, app):
    """Una adenda ya derivada a maraña no se edita ni elimina."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    client.post(
        f"/api/v1/chambas/{d['id']}/adenda",
        json={"descripcion": "Cambio de tubería", "monto_extra": 25000},
        headers=sol_h,
    )
    client.post(
        f"/api/v1/chambas/{d['id']}/marana",
        json={
            "adenda_idx": 0,
            "titulo": "Cambio de tubería",
            "categoria": "electricidad",
            "descripcion": "Trabajo extra de otro perfil",
        },
        headers=sol_h,
    )
    r_edit = client.patch(
        f"/api/v1/chambas/{d['id']}/adenda/0",
        json={"cubierta_por": "pds_actual"},
        headers=sol_h,
    )
    assert r_edit.status_code == 400
    r_del = client.delete(f"/api/v1/chambas/{d['id']}/adenda/0", headers=sol_h)
    assert r_del.status_code == 400


def test_novedad_panico_ok(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/novedad",
        json={"tipo": "panic", "descripcion": "Desacuerdo en sitio"},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["novedades"][0]["tipo"] == "panic"


def test_novedad_tipo_invalido(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/novedad",
        json={"tipo": "otro_tipo", "descripcion": "x"},
        headers=pds_h,
    )
    assert resp.status_code == 422


# ---------------- Pánico: pausar y reanudar ----------------
def test_pausar_y_reanudar(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_ejecucion"},
        headers=pds_h,
    )
    # Cualquiera de las partes puede pausar.
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "pausada"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "pausada"
    # Reanudar vuelve al estado previo.
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_ejecucion"},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "en_ejecucion"


# ---------------- Hito 4: solicitud de cierre ----------------
def _subir_evidencia_salida(client, chamba_id, pds_h, url=None):
    """Registra una evidencia final (requisito para solicitar el cierre)."""
    resp = client.post(
        f"/api/v1/chambas/{chamba_id}/evidencia-salida",
        json={"urls": [url or f"https://minio.chambeapp.co/chambas/{chamba_id}/salida/360.jpg"]},
        headers=pds_h,
    )
    assert resp.status_code == 200
    return resp


def _avanzar_a_ejecucion_con_salida(client, app, sol_h, pds_h):
    """en_ejecucion + evidencia final registrada (lista para el cierre)."""
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_ejecucion"},
        headers=pds_h,
    )
    _subir_evidencia_salida(client, d["id"], pds_h)
    return d


def test_solicitar_cierre_sin_evidencia_final(client, app):
    """El cierre NO se puede solicitar sin imágenes finales de la entrega."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "en_ejecucion"},
        headers=pds_h,
    )
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "pendiente_validacion"},
        headers=pds_h,
    )
    assert resp.status_code == 400
    assert "evidencia" in resp.get_json()["message"]


def test_solicitar_cierre_con_evidencia_final(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion_con_salida(client, app, sol_h, pds_h)
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "pendiente_validacion"},
        headers=pds_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "pendiente_validacion"
    assert resp.get_json()["fecha_solicitud_cierre"] is not None
    assert len(resp.get_json()["evidencia_salida"]) == 1


def test_evidencia_salida_ok(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion_con_salida(client, app, sol_h, pds_h)
    # La evidencia final quedó registrada antes del cierre.
    detalle = client.get(f"/api/v1/chambas/{d['id']}", headers=pds_h)
    assert detalle.status_code == 200
    assert len(detalle.get_json()["evidencia_salida"]) == 1


# ---------------- Hito 4: revisión y validación de habilidades ----------------
def test_validar_habilidades_en_revision(client, app):
    """El solicitante marca las habilidades del PDS en la revisión
    (pendiente_validacion), NO en la liquidación."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)

    resp = client.post(
        f"/api/v1/chambas/{d['id']}/validacion",
        json={"habilidades": [1, 3]},
        headers=sol_h,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["habilidades_validadas"] == [1, 3]
    assert body["fecha_validacion"] is not None
    # No finaliza ni cambia de estado: sigue en revisión.
    assert body["estado"] == "pendiente_validacion"


def test_validar_solo_solicitante(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/validacion",
        json={"habilidades": [1]},
        headers=pds_h,
    )
    assert resp.status_code == 403


def test_validar_solo_en_revision(client, app):
    """No se validan habilidades en la liquidación: solo el pago."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={"monto_final": 100000}, headers=sol_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={}, headers=pds_h)
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "liquidacion_confirmada"},
        headers=sol_h,
    )
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/validacion",
        json={"habilidades": [1]},
        headers=sol_h,
    )
    assert resp.status_code == 400


# ---------------- Hito 5: confirmación de pago directo ----------------
def _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h):
    d = _avanzar_a_ejecucion_con_salida(client, app, sol_h, pds_h)
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "pendiente_validacion"},
        headers=pds_h,
    )
    return d


def test_pago_antes_de_entrega(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_ejecucion(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/pago",
        json={"monto_final": 100000},
        headers=sol_h,
    )
    assert resp.status_code == 400


def test_pago_actualizable_en_liquidacion(client, app):
    """En la liquidación el pago sigue visible: permite actualizar el monto."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_liquidada(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/pago",
        json={"monto_final": 125000},
        headers=sol_h,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pago_monto_final"] == 125000
    assert body["pago_directo_confirmado"] is True
    assert body["estado"] == "liquidacion_confirmada"


def test_pago_confirmacion_dual(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    # Solo una parte confirma: no queda confirmado.
    r1 = client.post(
        f"/api/v1/chambas/{d['id']}/pago",
        json={"monto_final": 100000},
        headers=sol_h,
    )
    assert r1.status_code == 200
    assert r1.get_json()["pago_confirmado_solicitante"] is True
    assert r1.get_json()["pago_directo_confirmado"] is False
    # Segunda parte confirma: pago directo confirmado.
    r2 = client.post(
        f"/api/v1/chambas/{d['id']}/pago",
        json={},
        headers=pds_h,
    )
    assert r2.status_code == 200
    assert r2.get_json()["pago_confirmado_prestador"] is True
    assert r2.get_json()["pago_directo_confirmado"] is True
    assert r2.get_json()["pago_monto_final"] == 100000


def test_liquidar_sin_pago_completo(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "liquidacion_confirmada"},
        headers=sol_h,
    )
    assert resp.status_code == 400


def test_liquidar_solo_solicitante(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={"monto_final": 100000}, headers=sol_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={}, headers=pds_h)
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "liquidacion_confirmada"},
        headers=pds_h,
    )
    assert resp.status_code == 403


def _avanzar_a_liquidada(client, app, sol_h, pds_h):
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={"monto_final": 100000}, headers=sol_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={}, headers=pds_h)
    resp = client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "liquidacion_confirmada"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    return d


# ---------------- Hito 6: calificación final ----------------
def test_calificar_solo_solicitante(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_liquidada(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/calificacion",
        json={"estrellas": 5, "comentario": "Excelente", "habilidades": [1, 2]},
        headers=pds_h,
    )
    assert resp.status_code == 403


def test_calificar_ok_y_finalizar(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_liquidada(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/calificacion",
        json={"estrellas": 5, "comentario": "Excelente"},
        headers=sol_h,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estado"] == "finalizada"
    assert body["rating_estrellas"] == 5
    assert body["rating_comentario"] == "Excelente"
    assert body["fecha_finalizacion"] is not None


def test_calificar_conserva_habilidades_validadas(client, app):
    """Las habilidades se validan en la revisión; la calificación final
    no las borra (la liquidación solo notifica el pago)."""
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_pendiente_validacion(client, app, sol_h, pds_h)
    client.post(f"/api/v1/chambas/{d['id']}/validacion", json={"habilidades": [1, 3]}, headers=sol_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={"monto_final": 100000}, headers=sol_h)
    client.post(f"/api/v1/chambas/{d['id']}/pago", json={}, headers=pds_h)
    client.patch(
        f"/api/v1/chambas/{d['id']}/estado",
        json={"estado": "liquidacion_confirmada"},
        headers=sol_h,
    )
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/calificacion",
        json={"estrellas": 5},
        headers=sol_h,
    )
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "finalizada"
    assert resp.get_json()["habilidades_validadas"] == [1, 3]


def test_calificar_estrellas_fuera_de_rango(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    d = _avanzar_a_liquidada(client, app, sol_h, pds_h)
    resp = client.post(
        f"/api/v1/chambas/{d['id']}/calificacion",
        json={"estrellas": 6},
        headers=sol_h,
    )
    assert resp.status_code == 422


# ---------------- Listados por rol ----------------
def test_listar_chambas_solicitante(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    sol_id = _user_id(app, "sol@example.com")
    _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.get(f"/api/v1/chambas/solicitante/{sol_id}", headers=sol_h)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_listar_chambas_prestador_con_filtro(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    pds_h = _user(client, "pds@example.com", rol="pds")
    pds_id = _user_id(app, "pds@example.com")
    _crear_chamba(client, app, sol_h, "pds@example.com")
    resp = client.get(f"/api/v1/chambas/prestador/{pds_id}?estado=programada", headers=pds_h)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 1
    assert body[0]["estado"] == "programada"


def test_listar_chambas_ajenas(client, app):
    sol_h = _user(client, "sol@example.com", rol="solicitante")
    other_h = _user(client, "other@example.com", rol="solicitante")
    _user(client, "pds@example.com", rol="pds")
    other_id = _user_id(app, "other@example.com")
    resp = client.get(f"/api/v1/chambas/solicitante/{other_id}", headers=sol_h)
    assert resp.status_code == 403