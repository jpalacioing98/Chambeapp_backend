"""pytest — RF-13: certificado de ingresos del proveedor."""

import pytest
from datetime import datetime, timezone
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User, Profile, RolUsuario
from app.models.solicitud import Solicitud
from app.models.contract import Contract, EstadoContrato
from app.models.payment import Payment, EstadoPago


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


def _make_user(email, rol=RolUsuario.PDS, nombre=None):
    u = User(email=email, rol=rol, nombre=nombre, acepto_tyc=True, activo=True)
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.flush()
    # El endpoint lee user.profile.* -> creamos perfil siempre.
    db.session.add(Profile(user=u))
    db.session.commit()
    return u


def _headers(user):
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.rol.value, "role_v": user.role_version},
    )
    return {"Authorization": f"Bearer {token}"}


def _crear_solicitud(solicitante_id):
    s = Solicitud(
        solicitante_id=solicitante_id,
        titulo="Servicio",
        categoria="plomeria",
        descripcion="desc",
        ubicacion="Valledupar",
    )
    db.session.add(s)
    db.session.commit()
    return s


def _contrato_completado(proveedor_id, solicitante_id, fin_en=None):
    s = _crear_solicitud(solicitante_id)
    c = Contract(
        service_id=s.id,
        proveedor_id=proveedor_id,
        solicitante_id=solicitante_id,
        estado=EstadoContrato.COMPLETADO,
        fin_en=fin_en or datetime.now(timezone.utc),
    )
    db.session.add(c)
    db.session.commit()
    return c


def _pago_liberado(contract_id, monto, comision, liberado_en=None):
    p = Payment(
        contract_id=contract_id,
        monto=monto,
        comision_pds=comision,
        comision_solicitante=0,
        estado=EstadoPago.COMPLETADO,
        pasarela="mock",
        liberado_en=liberado_en or datetime.now(timezone.utc),
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_certificado_ingresos_ok(client, app):
    pds = _make_user("pds@example.com", rol=RolUsuario.PDS, nombre="Juan PDS")
    emp = _make_user("emp@example.com", rol=RolUsuario.SOLICITANTE)
    c = _contrato_completado(pds.id, emp.id)
    _pago_liberado(c.id, monto=200000, comision=24000)  # comision_pds

    resp = client.get(
        "/api/v1/payments/certificado-ingresos", headers=_headers(pds)
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["nombre"] == "Juan PDS"
    assert d["total_ingresos"] == 176000  # 200000 - 24000 (comision_pds)
    assert d["servicios_completados"] == 1
    assert d["promedio_mensual"] == round(176000 / 12)
    assert len(d["historial"]) == 12
    # La entrada del mes actual debe tener el ingreso completo.
    mes_actual = datetime.now(timezone.utc).strftime("%Y-%m")
    entry = next(h for h in d["historial"] if h["mes"] == mes_actual)
    assert entry["ingreso"] == 176000
    assert entry["servicios"] == 1


def test_certificado_sin_contratos(client, app):
    pds = _make_user("pds2@example.com", rol=RolUsuario.PDS)

    resp = client.get(
        "/api/v1/payments/certificado-ingresos", headers=_headers(pds)
    )
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["total_ingresos"] == 0
    assert d["servicios_completados"] == 0
    assert len(d["historial"]) == 12
    assert all(h["ingreso"] == 0 and h["servicios"] == 0 for h in d["historial"])
