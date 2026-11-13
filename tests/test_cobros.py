"""pytest suite — cobros en monedas (contratos y anuncios)."""

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.contract import Contract
from app.models.oferta import EstadoOferta
from app.models.solicitud import EstadoSolicitud, Solicitud
from app.models.user import RolUsuario, User
from app.models.wallet import (
    Coin,
    MovimientoMonedas,
    PaqueteMonedas,
    TipoMoneda,
    Wallet,
)
from app.services.cobros import (
    actualizar_tarifas,
    calcular_monedas_contrato,
    get_config_publica,
)


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


def _user(email, rol=RolUsuario.PDS, monedas=200):
    u = User(
        email=email,
        rol=rol,
        nombre=email.split("@")[0],
        acepto_tyc=True,
        activo=True,
        status="active",
    )
    u.set_password("ChambeApp123!")
    db.session.add(u)
    db.session.commit()
    wallet = Wallet.query.filter_by(user_id=u.id).first()
    if wallet is None:
        wallet = Wallet(user_id=u.id, monedas_saldo=monedas)
        db.session.add(wallet)
    else:
        wallet.monedas_saldo = monedas
    db.session.add(Coin(user_id=u.id, cantidad=monedas, tipo=TipoMoneda.GANADA))
    db.session.commit()
    return u


def _headers(user):
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.rol.value, "role_v": user.role_version},
    )
    return {"Authorization": f"Bearer {token}"}


def _solicitud(solicitante_id, presupuesto=100000):
    sol = Solicitud(
        solicitante_id=solicitante_id,
        titulo="Pintar fachada",
        categoria="pintura",
        descripcion="Pintar la fachada completa",
        ubicacion="Valledupar",
        presupuesto=presupuesto,
        estado=EstadoSolicitud.PUBLICADO,
    )
    db.session.add(sol)
    db.session.commit()
    return sol


def _contrato(client, emp_h, emp_id, pds_id, presupuesto=100000):
    sol = _solicitud(emp_id, presupuesto)
    resp = client.post(
        "/api/v1/contracts/",
        json={"service_id": sol.id, "proveedor_id": pds_id},
        headers=emp_h,
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def _firmar(client, contract_id, headers):
    return client.patch(
        f"/api/v1/contracts/{contract_id}/estado",
        json={"estado": "aceptar", "firma": {"nombre": "Firma"}},
        headers=headers,
    )


def _saldo(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    return wallet.monedas_saldo if wallet else 0


# ---------------- fórmula ----------------
def test_formula_trunc_y_minimo(app):
    # 100.000 × 3% / 100 = 30 + 1 = 31
    assert calcular_monedas_contrato(100000) == 31
    # 55.000 × 3% / 100 = 16,5 -> trunc 16 + 1 = 17
    assert calcular_monedas_contrato(55000) == 17
    # Monto pequeño: el mínimo manda (10)
    assert calcular_monedas_contrato(10000) == 10
    assert calcular_monedas_contrato(0) == 10


def test_config_publica_tiene_claves(app):
    config = get_config_publica()
    assert config["pct_contrato"] == 3.0
    assert config["precio_moneda_cop"] == 100
    assert config["costo_publicar_anuncio"] == 10
    assert config["costo_reactivar_anuncio"] == 5


# ---------------- firma de contrato ----------------
def test_firmar_cobra_monedas(client):
    emp = _user("emp@x.com", RolUsuario.SOLICITANTE)
    pds = _user("pds@x.com", RolUsuario.PDS)
    emp_h = _headers(emp)
    cid = _contrato(client, emp_h, emp.id, pds.id)

    resp = _firmar(client, cid, emp_h)
    assert resp.status_code == 200, resp.get_json()
    assert _saldo(emp.id) == 200 - 31

    movimiento = MovimientoMonedas.query.filter_by(
        user_id=emp.id, referencia=f"COBRO-FIRMA-{cid}-{emp.id}"
    ).first()
    assert movimiento is not None
    assert movimiento.cantidad == -31


def test_firmar_sin_monedas_400(client):
    emp = _user("emp2@x.com", RolUsuario.SOLICITANTE, monedas=0)
    pds = _user("pds2@x.com", RolUsuario.PDS)
    emp_h = _headers(emp)
    cid = _contrato(client, emp_h, emp.id, pds.id)

    resp = _firmar(client, cid, emp_h)
    assert resp.status_code == 400
    assert "MONEDAS_INSUFICIENTES" in resp.get_json()["message"]
    assert _saldo(emp.id) == 0


def test_cancelar_antes_de_ambas_firmas_reembolsa(client):
    emp = _user("emp3@x.com", RolUsuario.SOLICITANTE)
    pds = _user("pds3@x.com", RolUsuario.PDS)
    emp_h = _headers(emp)
    cid = _contrato(client, emp_h, emp.id, pds.id)

    assert _firmar(client, cid, emp_h).status_code == 200
    assert _saldo(emp.id) == 169

    resp = client.patch(
        f"/api/v1/contracts/{cid}/estado",
        json={"estado": "cancelar", "motivo_cancelacion": "Ya no se requiere"},
        headers=emp_h,
    )
    assert resp.status_code == 200, resp.get_json()
    assert _saldo(emp.id) == 200
    contract = db.session.get(Contract, cid)
    assert contract.cobros_reembolsados is True


# ---------------- anuncios ----------------
def _anuncio_payload():
    return {
        "titulo": "Se busca pintor",
        "descripcion": "Pintar una casa de dos pisos",
        "categoria": "pintura",
        "ubicacion": "Valledupar",
    }


def test_publicar_anuncio_cobra(client):
    neg = _user("neg@x.com", RolUsuario.MERCHANT, monedas=100)
    resp = client.post(
        "/api/v1/anuncios/", json=_anuncio_payload(), headers=_headers(neg)
    )
    assert resp.status_code in (200, 201), resp.get_json()
    assert _saldo(neg.id) == 90
    movimiento = MovimientoMonedas.query.filter_by(
        user_id=neg.id, tipo="gasto"
    ).first()
    assert movimiento is not None
    assert movimiento.cantidad == -10


def test_publicar_sin_monedas_400(client):
    neg = _user("neg2@x.com", RolUsuario.MERCHANT, monedas=5)
    resp = client.post(
        "/api/v1/anuncios/", json=_anuncio_payload(), headers=_headers(neg)
    )
    assert resp.status_code == 400
    assert "MONEDAS_INSUFICIENTES" in resp.get_json()["message"]
    assert _saldo(neg.id) == 5


def test_reactivar_anuncio_cobra(client):
    neg = _user("neg3@x.com", RolUsuario.MERCHANT, monedas=100)
    h = _headers(neg)
    creado = client.post(
        "/api/v1/anuncios/", json=_anuncio_payload(), headers=h
    ).get_json()
    aid = creado["id"]
    assert _saldo(neg.id) == 90

    client.patch(
        f"/api/v1/anuncios/{aid}/estado", json={"accion": "cerrar"}, headers=h
    )
    assert _saldo(neg.id) == 90

    resp = client.patch(
        f"/api/v1/anuncios/{aid}/estado",
        json={"accion": "abrir"},
        headers=h,
    )
    assert resp.status_code == 200
    assert _saldo(neg.id) == 85


# ---------------- tarifas ----------------
def test_actualizar_precio_moneda_recalcula_paquetes(app):
    paquete = PaqueteMonedas(
        nombre="Básico", cantidad=50, bonus=0, precio_cop=5000, activo=True
    )
    db.session.add(paquete)
    db.session.commit()

    actualizar_tarifas({"precio_moneda_cop": 200})
    db.session.refresh(paquete)
    assert paquete.precio_cop == 10000
    assert get_config_publica()["precio_moneda_cop"] == 200


def test_actualizar_tarifas_invalidas(app):
    with pytest.raises(ValueError):
        actualizar_tarifas({"pct_contrato": -1})
    with pytest.raises(ValueError):
        actualizar_tarifas({"precio_moneda_cop": 0})
