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
        from app.data.seed_paquetes import sync_paquetes_monedas

        sync_paquetes_monedas()
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
        return User.query.filter_by(email=email).first().id


def _make_user(app, email, rol, password="secret123"):
    with app.app_context():
        user = User(
            email=email,
            rol=rol,
            acepto_tyc=True,
            activo=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _token_headers(app, user_id):
    from flask_jwt_extended import create_access_token

    with app.app_context():
        user = db.session.get(User, user_id)
        token = create_access_token(
            identity=str(user_id),
            additional_claims={
                "role": user.rol.value,
                "role_v": user.role_version,
            },
        )
    return {"Authorization": f"Bearer {token}"}


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
        assert data["monedas_saldo"] == 0

    def test_billetera_creada_al_registrar(self, client, app):
        """El registro crea la billetera sin esperar a que el usuario la abra."""
        _register(client, "nuevo@test.com", "solicitante")
        uid = _user_id(app, "nuevo@test.com")
        with app.app_context():
            assert Wallet.query.filter_by(user_id=uid).first() is not None

    def test_recarga_eliminada(self, client):
        """La recarga de dinero ya no existe: la billetera se monetiza con monedas."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/deposit",
            json={"monto": 50000, "pasarela": "nequi"},
            headers=headers,
        )
        assert resp.status_code in (404, 405)

    def test_retirar_fondos(self, client, app):
        """Se pueden retirar fondos COP acreditados por un contrato."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        uid = _user_id(app, "pds@test.com")
        with app.app_context():
            from app.services.wallet import acreditar_pago

            acreditar_pago(uid, 50000, "TEST-CONTRATO")
            db.session.commit()

        resp = client.post(
            "/api/v1/wallet/withdraw",
            json={"monto": 20000, "cuenta_destino": "1234567890"},
            headers=headers,
        )
        assert resp.status_code == 201

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

    def test_historial_transacciones(self, client, app):
        """Se puede ver el historial de transacciones COP."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        uid = _user_id(app, "pds@test.com")
        with app.app_context():
            from app.services.wallet import acreditar_pago

            acreditar_pago(uid, 10000, "TEST-1")
            acreditar_pago(uid, 20000, "TEST-2")
            db.session.commit()

        resp = client.get("/api/v1/wallet/history", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2


# --------------------------------------------------------------------------
# Tests: Sistema de Monedas (RF-27)
# --------------------------------------------------------------------------

class TestCoins:
    def _paquete_id(self, client, headers, nombre):
        paquetes = client.get("/api/v1/wallet/paquetes", headers=headers).get_json()
        return next(p["id"] for p in paquetes if p["nombre"] == nombre)

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
        assert data["saldo"] == 0
        assert data["gastada"] == 0

    def test_comprar_monedas(self, client):
        """Se pueden comprar monedas con un paquete."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        paquete_id = self._paquete_id(client, headers, "Básico")
        resp = client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete_id": paquete_id},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["compra"]["monedas"] == 50
        assert data["compra"]["precio_cop"] == 5000
        assert data["saldo"]["saldo"] == 50

    def test_comprar_paquete_estandar(self, client):
        """El paquete estándar incluye bonus."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        paquete_id = self._paquete_id(client, headers, "Estándar")
        resp = client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete_id": paquete_id},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.get_json()["compra"]["monedas"] == 165  # 150 + 15 bonus

    def test_paquete_invalido(self, client):
        """No se puede comprar un paquete inválido."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete_id": 99999},
            headers=headers,
        )
        assert resp.status_code in (400, 422)

    def test_usar_monedas(self, client):
        """Se pueden usar monedas y queda el movimiento en el libro."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        paquete_id = self._paquete_id(client, headers, "Básico")
        client.post(
            "/api/v1/wallet/coins/buy",
            json={"paquete_id": paquete_id},
            headers=headers,
        )

        resp = client.post(
            "/api/v1/wallet/coins/use",
            json={"cantidad": 20, "motivo": "Ofertar en solicitud"},
            headers=headers,
        )
        assert resp.status_code == 200

        saldo = client.get("/api/v1/wallet/coins", headers=headers).get_json()
        assert saldo["saldo"] == 30
        assert saldo["gastada"] == 20

        movimientos = client.get(
            "/api/v1/wallet/coins/movimientos", headers=headers
        ).get_json()
        assert [m["tipo"] for m in movimientos] == ["gasto", "compra"]

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
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.get("/api/v1/wallet/paquetes", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        nombres = {p["nombre"] for p in data}
        assert {"Básico", "Estándar", "Premium"} <= nombres
        assert data[0]["monedas_totales"] >= data[0]["cantidad"]

    def test_resumen_financiero_por_rol(self, client):
        """El resumen incluye monedas y el bloque del rol."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.get("/api/v1/wallet/resumen", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["rol"] == "pds"
        assert "monedas" in data and "pds" in data
        assert "finanzas" in data
        assert "cop" not in data
        assert data["finanzas"]["ingresos_cop"] >= 0
        assert data["finanzas"]["egresos_cop"] >= 0

    def test_solo_superadmin_gestiona_paquetes(self, client):
        """Un rol normal no puede crear/editar paquetes."""
        _register(client, "pds@test.com", "pds")
        headers = _headers(client, "pds@test.com")
        resp = client.post(
            "/api/v1/wallet/admin/paquetes",
            json={"nombre": "Hack", "cantidad": 10, "precio_cop": 1000},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_superadmin_crea_edita_y_desactiva_paquete(self, client, app):
        """El superadmin administra paquetes; los usuarios solo los compran."""
        uid = _make_user(app, "root@test.com", RolUsuario.SUPERADMIN)
        headers = _token_headers(app, uid)

        creado = client.post(
            "/api/v1/wallet/admin/paquetes",
            json={
                "nombre": "Temporada",
                "cantidad": 100,
                "bonus": 10,
                "precio_cop": 9000,
                "en_oferta": True,
                "precio_oferta_cop": 7000,
                "orden": 9,
            },
            headers=headers,
        )
        assert creado.status_code == 201, creado.get_json()
        paquete = creado.get_json()
        assert paquete["monedas_totales"] == 110
        assert paquete["precio_efectivo_cop"] == 7000
        assert paquete["oferta_vigente"] is True

        editado = client.patch(
            f"/api/v1/wallet/admin/paquetes/{paquete['id']}",
            json={"activo": False, "en_oferta": False},
            headers=headers,
        )
        assert editado.status_code == 200
        assert editado.get_json()["activo"] is False

        desactivado = client.delete(
            f"/api/v1/wallet/admin/paquetes/{paquete['id']}",
            headers=headers,
        )
        assert desactivado.status_code == 200
        assert desactivado.get_json()["id"] == paquete["id"]

        # Los paquetes inactivos no aparecen en el catálogo público.
        _register(client, "pds@test.com", "pds")
        user_headers = _headers(client, "pds@test.com")
        catalogo = client.get("/api/v1/wallet/paquetes", headers=user_headers).get_json()
        assert all(p["id"] != paquete["id"] for p in catalogo)


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
