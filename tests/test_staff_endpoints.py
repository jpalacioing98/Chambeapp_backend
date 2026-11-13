"""pytest — endpoints que faltaban para las pantallas operativas.

- `GET /kyc/metricas`: indicadores reales del dashboard del verificador.
- `GET/PUT /plantillas`: plantillas de KYC, tickets y veredictos.
- `POST /tickets` con `user_id`: el staff crea tickets a nombre de un usuario.
"""

from datetime import datetime, timedelta, timezone

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.kyc import DocumentoUsuario
from app.models.ticket import Ticket


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
def staff(app):
    return {
        "superadmin": _make_user("sa@x.com", RolUsuario.SUPERADMIN, "SA"),
        "verificador": _make_user("ver@x.com", RolUsuario.VERIFICADOR, "Ver"),
        "soporte": _make_user("sup@x.com", RolUsuario.SOPORTE, "Sup"),
        "pds": _make_user("pds@x.com", RolUsuario.PDS, "PDS"),
    }


# ---------------------------------------------------------------- KYC métricas

def test_metricas_kyc_calculan_indicadores(client, staff):
    pds = staff["pds"]
    ahora = datetime.now(timezone.utc)

    db.session.add_all(
        [
            DocumentoUsuario(
                user_id=pds.id,
                documento_clave="doc_identidad",
                estado="enviado",
                fecha_envio=ahora - timedelta(hours=5),
            ),
            DocumentoUsuario(
                user_id=pds.id,
                documento_clave="cert_bancaria",
                estado="aprobado",
                fecha_envio=ahora - timedelta(hours=10),
                revisado_en=ahora - timedelta(hours=2),
                revisor_id=staff["verificador"].id,
            ),
            DocumentoUsuario(
                user_id=pds.id,
                documento_clave="validacion_profesional",
                estado="rechazado",
                fecha_envio=ahora - timedelta(hours=8),
                revisado_en=ahora - timedelta(hours=1),
                revisor_id=staff["verificador"].id,
            ),
        ]
    )
    db.session.commit()

    r = client.get("/api/v1/kyc/metricas", headers=_headers(staff["verificador"]))
    assert r.status_code == 200
    data = r.get_json()

    assert data["pendientes"] == 1
    assert data["revisados_hoy"] == 2
    assert data["aprobados"] == 1
    assert data["rechazados"] == 1
    assert data["tasa_aprobacion"] == 50.0
    assert data["tiempo_medio_horas"] == pytest.approx(7.5, abs=0.01)
    assert data["mas_antiguo_horas"] == pytest.approx(5, abs=0.01)


def test_metricas_kyc_sin_datos_no_divide_por_cero(client, staff):
    r = client.get("/api/v1/kyc/metricas", headers=_headers(staff["verificador"]))
    assert r.status_code == 200
    data = r.get_json()
    assert data["pendientes"] == 0
    assert data["tasa_aprobacion"] is None
    assert data["tiempo_medio_horas"] is None


def test_metricas_kyc_requiere_rol_staff(client, staff):
    r = client.get("/api/v1/kyc/metricas", headers=_headers(staff["pds"]))
    assert r.status_code == 403


# ---------------------------------------------------------------- plantillas

def test_plantillas_devuelve_los_tres_tipos_con_defaults(client, staff):
    r = client.get("/api/v1/plantillas/", headers=_headers(staff["verificador"]))
    assert r.status_code == 200
    data = r.get_json()
    assert set(data) == {"kyc_rechazo", "ticket_respuesta", "disputa_veredicto"}
    assert len(data["kyc_rechazo"]) >= 3


def test_plantillas_actualiza_un_tipo(client, staff):
    r = client.put(
        "/api/v1/plantillas/kyc_rechazo",
        headers=_headers(staff["superadmin"]),
        json={"items": ["Foto borrosa", "Documento vencido"]},
    )
    assert r.status_code == 200
    assert r.get_json()["kyc_rechazo"] == ["Foto borrosa", "Documento vencido"]

    # Persistió y no afectó a los otros tipos.
    r = client.get("/api/v1/plantillas/", headers=_headers(staff["verificador"]))
    data = r.get_json()
    assert data["kyc_rechazo"] == ["Foto borrosa", "Documento vencido"]
    assert len(data["ticket_respuesta"]) >= 3


def test_plantillas_tipo_desconocido_404(client, staff):
    r = client.put(
        "/api/v1/plantillas/inventado",
        headers=_headers(staff["superadmin"]),
        json={"items": ["algo"]},
    )
    assert r.status_code == 404


def test_plantillas_solo_superadmin_escribe(client, staff):
    r = client.put(
        "/api/v1/plantillas/kyc_rechazo",
        headers=_headers(staff["verificador"]),
        json={"items": ["No debería poder"]},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------- tickets

def test_soporte_crea_ticket_para_otro_usuario(client, staff):
    pds = staff["pds"]
    r = client.post(
        "/api/v1/tickets/",
        headers=_headers(staff["soporte"]),
        json={
            "subject": "Problema con el pago",
            "body": "El usuario reporta un cobro duplicado en su contrato.",
            "category": "pagos",
            "user_id": pds.id,
        },
    )
    assert r.status_code == 201

    ticket = db.session.get(Ticket, r.get_json()["id"])
    assert ticket.user_id == pds.id


def test_usuario_normal_no_crea_ticket_para_otro(client, staff):
    r = client.post(
        "/api/v1/tickets/",
        headers=_headers(staff["pds"]),
        json={
            "subject": "Prueba de suplantación",
            "body": "Intento de crear un ticket en nombre de otro usuario.",
            "user_id": staff["soporte"].id,
        },
    )
    assert r.status_code == 403


def test_usuario_crea_su_propio_ticket(client, staff):
    r = client.post(
        "/api/v1/tickets/",
        headers=_headers(staff["pds"]),
        json={
            "subject": "No puedo subir mi documento",
            "body": "La app muestra un error al adjuntar la cédula.",
        },
    )
    assert r.status_code == 201
    ticket = db.session.get(Ticket, r.get_json()["id"])
    assert ticket.user_id == staff["pds"].id
