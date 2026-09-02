"""pytest suite — wallet, coins, modalities, milestones (RF-25, RF-26, RF-27, RF-29)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig
from app.models.user import User, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud
from app.models.contract import Contract, EstadoContrato
from app.models.wallet import Wallet, Transaction, Coin, TipoTransaccion, TipoMoneda
from app.models.modalidad import Modalidad, Milestone, TipoModalidad, EstadoHito


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


# --------------------------------------------------------------------------
# Tests: Billetera Virtual (RF-25)
# --------------------------------------------------------------------------

class TestWallet:
    def test_crear_billetera_automaticamente(self, client):
        """Al consultar billetera, se crea automáticamente si no existe."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.get("/api/v1/wallet/", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["saldo"] == 0
        assert data["saldo_bloqueado"] == 0

    def test_depositar_fondos(self, client):
        """Se pueden depositar fondos en la billetera."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/deposit",
            json={"monto": 50000, "pasarela": "nequi"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["tipo"] == "deposito"
        assert data["monto"] == 50000

        # Verificar saldo
        resp = client.get("/api/v1/wallet/", headers=headers)
        assert resp.get_json()["saldo"] == 50000

    def test_depositar_monto_minimo(self, client):
        """El monto mínimo de depósito es $1,000."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/deposit",
            json={"monto": 500},
            headers=headers,
        )
        assert resp.status_code in (400, 422)

    def test_retirar_fondos(self, client):
        """Se pueden retirar fondos de la billetera."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")

        # Depositar primero
        client.post(
            "/api/v1/wallet/deposit",
            json={"monto": 50000},
            headers=headers,
        )

        # Retirar
        resp = client.post(
            "/api/v1/wallet/withdraw",
            json={"monto": 20000, "cuenta_destino": "1234567890"},
            headers=headers,
        )
        assert resp.status_code == 201

        # Verificar saldo
        resp = client.get("/api/v1/wallet/", headers=headers)
        assert resp.get_json()["saldo"] == 30000

    def test_retirar_saldo_insuficiente(self, client):
        """No se puede retirar más de lo disponible."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/withdraw",
            json={"monto": 20000, "cuenta_destino": "1234567890"},
            headers=headers,
        )
        assert resp.status_code in (400, 422)

    def test_historial_transacciones(self, client):
        """Se puede ver el historial de transacciones."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")

        # Hacer algunos depósitos
        client.post("/api/v1/wallet/deposit", json={"monto": 10000}, headers=headers)
        client.post("/api/v1/wallet/deposit", json={"monto": 20000}, headers=headers)

        resp = client.get("/api/v1/wallet/history", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2


# --------------------------------------------------------------------------
# Tests: Sistema de Monedas (RF-27)
# --------------------------------------------------------------------------

class TestCoins:
    def test_ver_saldo_monedas(self, client):
        """Se puede ver el saldo de monedas."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.get("/api/v1/wallet/coins", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["comprada"] == 0
        assert data["promocional"] == 0
        assert data["ganada"] == 0

    def test_comprar_monedas(self, client):
        """Se pueden comprar monedas."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete": "basico"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["cantidad"] == 50  # 50 monedas en paquete básico
        assert data["tipo"] == "comprada"

    def test_comprar_paquete_estandar(self, client):
        """El paquete estándar incluye bonus."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete": "estandar"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["cantidad"] == 165  # 150 + 15 bonus

    def test_paquete_invalido(self, client):
        """No se puede comprar un paquete inválido."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete": "invalido"},
            headers=headers,
        )
        assert resp.status_code in (400, 422)

    def test_usar_monedas(self, client):
        """Se pueden usar monedas."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")

        # Comprar monedas
        client.post("/api/v1/wallet/coins/buy", json={"paquete": "basico"}, headers=headers)

        # Usar monedas
        resp = client.post(
            "/api/v1/wallet/coins/use",
            json={"cantidad": 20, "motivo": "Ofertar en solicitud"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Verificar saldo
        resp = client.get("/api/v1/wallet/coins", headers=headers)
        assert resp.get_json()["comprada"] == 30

    def test_usar_monedas_insuficientes(self, client):
        """No se pueden usar más monedas de las disponibles."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/coins/use",
            json={"cantidad": 100, "motivo": "Ofertar"},
            headers=headers,
        )
        assert resp.status_code in (400, 422)

    def test_ver_paquetes(self, client):
        """Se pueden ver los paquetes disponibles."""
        resp = client.get("/api/v1/wallet/coins/packages")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "basico" in data
        assert "estandar" in data
        assert "premium" in data


# --------------------------------------------------------------------------
# Tests: Modalidades de Cobro (RF-26)
# --------------------------------------------------------------------------

class TestModalidades:
    def _create_solicitud(self, client, solicitante_id):
        """Helper para crear una solicitud."""
        with client.application.app_context():
            sol = Solicitud(
                solicitante_id=solicitante_id,
                titulo="Reparación de tubería",
                categoria="plomeria",
                descripcion="Reparación de tubería",
                ubicacion="Valledupar",
                presupuesto=100000,
                estado=EstadoSolicitud.PUBLICADO,
            )
            db.session.add(sol)
            db.session.commit()
            return sol.id

    def test_crear_modalidad(self, client):
        """Se puede crear una modalidad para una solicitud."""
        _register(client, "sol@test.com", "solicitante")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            user = User.query.filter_by(email="sol@test.com").first()
            sol_id = self._create_solicitud(client, user.id)

        resp = client.post(
            f"/api/v1/wallet/modalidades/{sol_id}",
            json={"tipo": "A_comision"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["tipo"] == "A_comision"

    def test_ver_modalidad(self, client):
        """Se puede ver la modalidad de una solicitud."""
        _register(client, "sol@test.com", "solicitante")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            user = User.query.filter_by(email="sol@test.com").first()
            sol_id = self._create_solicitud(client, user.id)

        # Crear modalidad
        client.post(
            f"/api/v1/wallet/modalidades/{sol_id}",
            json={"tipo": "B_sin_comision"},
            headers=headers,
        )

        # Ver modalidad
        resp = client.get(f"/api/v1/wallet/modalidades/{sol_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tipo"] == "B_sin_comision"
        assert data["monedas_requeridas"] == 50

    def test_modalidad_por_defecto(self, client):
        """Si no hay modalidad, se usa A_comision por defecto."""
        _register(client, "sol@test.com", "solicitante")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            user = User.query.filter_by(email="sol@test.com").first()
            sol_id = self._create_solicitud(client, user.id)

        resp = client.get(f"/api/v1/wallet/modalidades/{sol_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tipo"] == "A_comision"


# --------------------------------------------------------------------------
# Tests: Hitos de Pago (RF-29)
# --------------------------------------------------------------------------

class TestMilestones:
    def _create_contract(self, client, solicitante_id, proveedor_id):
        """Helper para crear un contrato."""
        with client.application.app_context():
            sol = Solicitud(
                solicitante_id=solicitante_id,
                titulo="Proyecto largo",
                categoria="plomeria",
                descripcion="Proyecto largo",
                ubicacion="Valledupar",
                presupuesto=400000,
                estado=EstadoSolicitud.PUBLICADO,
            )
            db.session.add(sol)
            db.session.flush()

            contract = Contract(
                service_id=sol.id,
                proveedor_id=proveedor_id,
                solicitante_id=solicitante_id,
                estado=EstadoContrato.EN_PROGRESO,
            )
            db.session.add(contract)
            db.session.commit()
            return contract.id

    def test_crear_hitos(self, client):
        """Se pueden crear hitos para un contrato."""
        _register(client, "sol@test.com", "solicitante")
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            sol_user = User.query.filter_by(email="sol@test.com").first()
            pds_user = User.query.filter_by(email="pds@test.com").first()
            contract_id = self._create_contract(client, sol_user.id, pds_user.id)

        resp = client.post(
            f"/api/v1/wallet/milestones/{contract_id}/create",
            json={
                "hitos": [
                    {"descripcion": "Semana 1", "monto": 100000},
                    {"descripcion": "Semana 2", "monto": 100000},
                    {"descripcion": "Semana 3", "monto": 100000},
                    {"descripcion": "Semana 4", "monto": 100000},
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert len(data) == 4
        assert data[0]["numero"] == 1
        assert data[0]["estado"] == "pendiente"

    def test_aprobar_hito(self, client):
        """Se puede aprobar un hito."""
        _register(client, "sol@test.com", "solicitante")
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            sol_user = User.query.filter_by(email="sol@test.com").first()
            pds_user = User.query.filter_by(email="pds@test.com").first()
            contract_id = self._create_contract(client, sol_user.id, pds_user.id)

        # Crear hitos
        resp = client.post(
            f"/api/v1/wallet/milestones/{contract_id}/create",
            json={"hitos": [{"descripcion": "Hito 1", "monto": 100000}]},
            headers=headers,
        )
        hito_id = resp.get_json()[0]["id"]

        # Aprobar hito
        resp = client.post(
            f"/api/v1/wallet/milestones/{hito_id}/action",
            json={"accion": "aprobar"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "aprobado"
        assert data["aprobado_en"] is not None

    def test_rechazar_hito(self, client):
        """Se puede rechazar un hito."""
        _register(client, "sol@test.com", "solicitante")
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            sol_user = User.query.filter_by(email="sol@test.com").first()
            pds_user = User.query.filter_by(email="pds@test.com").first()
            contract_id = self._create_contract(client, sol_user.id, pds_user.id)

        # Crear hitos
        resp = client.post(
            f"/api/v1/wallet/milestones/{contract_id}/create",
            json={"hitos": [{"descripcion": "Hito 1", "monto": 100000}]},
            headers=headers,
        )
        hito_id = resp.get_json()[0]["id"]

        # Rechazar hito
        resp = client.post(
            f"/api/v1/wallet/milestones/{hito_id}/action",
            json={"accion": "rechazar"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "rechazado"

    def test_verificar_todos_aprobados(self, client):
        """Se puede verificar si todos los hitos están aprobados."""
        _register(client, "sol@test.com", "solicitante")
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "sol@test.com")

        with client.application.app_context():
            sol_user = User.query.filter_by(email="sol@test.com").first()
            pds_user = User.query.filter_by(email="pds@test.com").first()
            contract_id = self._create_contract(client, sol_user.id, pds_user.id)

        # Crear hitos
        resp = client.post(
            f"/api/v1/wallet/milestones/{contract_id}/create",
            json={"hitos": [{"descripcion": "Hito 1", "monto": 100000}]},
            headers=headers,
        )
        hito_id = resp.get_json()[0]["id"]

        # Verificar (no todos aprobados)
        resp = client.get(f"/api/v1/wallet/milestones/{contract_id}/check", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["todos_aprobados"] is False

        # Aprobar hito
        client.post(
            f"/api/v1/wallet/milestones/{hito_id}/action",
            json={"accion": "aprobar"},
            headers=headers,
        )

        # Verificar (todos aprobados)
        resp = client.get(f"/api/v1/wallet/milestones/{contract_id}/check", headers=headers)
        data = resp.get_json()
        assert data["todos_aprobados"] is True
