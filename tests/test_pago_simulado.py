"""pytest suite — checkout realista de monedas y panel superadmin."""

import pytest

from app import create_app
from app.extensions import db
from app.models.user import User, RolUsuario
from app.models.wallet import (
    Wallet,
    PaqueteMonedas,
    CompraPaquete,
    PagoSimulado,
    MovimientoMonedas,
)


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


def _make_user(app, email, rol="pds", monedas=0, saldo=0, nombre=None):
    """Crea usuario + billetera y devuelve el id."""
    with app.app_context():
        user = User(
            email=email,
            rol=RolUsuario(rol) if isinstance(rol, str) else rol,
            acepto_tyc=True,
            activo=True,
            nombre=nombre or email.split("@")[0],
        )
        user.set_password("secret123")
        db.session.add(user)
        db.session.flush()
        db.session.add(
            Wallet(
                user_id=user.id,
                saldo=saldo,
                saldo_bloqueado=0,
                monedas_saldo=monedas,
            )
        )
        db.session.commit()
        return user.id


def _headers(app, user_id):
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


def _paquete_id(app):
    with app.app_context():
        return PaqueteMonedas.query.filter_by(activo=True).first().id


def _saldo(client, headers):
    return client.get("/api/v1/wallet/coins", headers=headers).get_json()["saldo"]


def _checkout(client, headers, paquete_id):
    resp = client.post(
        "/api/v1/wallet/coins/checkout",
        json={"paquete_id": paquete_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


# --------------------------------------------------------------------------
# Checkout + confirmación
# --------------------------------------------------------------------------

class TestPagoSimulado:
    def test_checkout_crea_pendiente_sin_acreditar(self, client, app):
        uid = _make_user(app, "comprador@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        assert data["estado"] == "pendiente"
        assert data["pago_id"] > 0
        assert data["referencia"].startswith(f"PAGO-{uid}-")
        assert data["url_redirect"] == f"/pago/simulado/{data['pago_id']}"
        assert data["paquete"]["id"] == _paquete_id(app)
        assert data["monedas"] > 0
        # No se acredita nada hasta confirmar.
        assert _saldo(client, headers) == 0

    def test_confirmar_acredita_y_crea_compra(self, client, app):
        uid = _make_user(app, "comprador@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        resp = client.post(
            f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers
        )
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()

        assert body["pago"]["estado"] == "completado"
        assert body["pago"]["completado_en"] is not None
        assert body["compra"] is not None
        assert body["compra"]["estado"] == "completado"
        assert body["compra"]["referencia"] == data["referencia"]
        assert body["saldo"]["total"] == data["monedas"]
        assert _saldo(client, headers) == data["monedas"]

        with app.app_context():
            compra = CompraPaquete.query.filter_by(user_id=uid).one()
            assert compra.referencia == data["referencia"]

    def test_confirmar_dos_veces_es_idempotente(self, client, app):
        uid = _make_user(app, "comprador@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        first = client.post(
            f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers
        )
        assert first.status_code == 200
        saldo = _saldo(client, headers)

        second = client.post(
            f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers
        )
        assert second.status_code == 200
        assert second.get_json()["pago"]["estado"] == "completado"
        assert _saldo(client, headers) == saldo
        with app.app_context():
            assert CompraPaquete.query.filter_by(user_id=uid).count() == 1

    def test_pago_expirado_no_se_confirma(self, client, app):
        from datetime import datetime, timedelta, timezone

        uid = _make_user(app, "comprador@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        with app.app_context():
            pago = db.session.get(PagoSimulado, data["pago_id"])
            pago.expira_en = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.session.commit()

        resp = client.post(
            f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers
        )
        assert resp.status_code == 400
        assert "expiró" in resp.get_json()["message"]

        with app.app_context():
            pago = db.session.get(PagoSimulado, data["pago_id"])
            assert pago.estado == "expirado"
        assert _saldo(client, headers) == 0

    def test_cancelar_pendiente(self, client, app):
        uid = _make_user(app, "comprador@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        resp = client.post(
            f"/api/v1/wallet/pagos/{data['pago_id']}/cancelar", headers=headers
        )
        assert resp.status_code == 200
        assert resp.get_json()["pago"]["estado"] == "fallido"

        after = client.post(
            f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers
        )
        assert after.status_code == 400
        assert _saldo(client, headers) == 0

    def test_webhook_confirma_sin_jwt(self, client, app):
        uid = _make_user(app, "comprador@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        resp = client.post(f"/api/v1/wallet/pagos/{data['pago_id']}/webhook")
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["pago"]["estado"] == "completado"
        assert _saldo(client, headers) == data["monedas"]

    def test_detalle_pago_solo_dueno_o_admin(self, client, app):
        uid = _make_user(app, "comprador@test.com")
        otro = _make_user(app, "ajeno@test.com")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))

        propio = client.get(f"/api/v1/wallet/pagos/{data['pago_id']}", headers=headers)
        assert propio.status_code == 200
        ajeno = client.get(
            f"/api/v1/wallet/pagos/{data['pago_id']}", headers=_headers(app, otro)
        )
        assert ajeno.status_code == 400


# --------------------------------------------------------------------------
# Panel superadmin
# --------------------------------------------------------------------------

class TestSuperadminMonedas:
    def test_oferta_con_fechas_naive_no_rompe(self, app):
        """datetime-local llega naive: la vigencia debe comparar sin TypeError."""
        from datetime import datetime

        with app.app_context():
            paquete = PaqueteMonedas(
                nombre="Oferta naive",
                cantidad=10,
                bonus=0,
                precio_cop=1000,
                activo=True,
                en_oferta=True,
                precio_oferta_cop=800,
                oferta_desde=datetime(2026, 1, 1, 0, 0),
                oferta_hasta=datetime(2030, 1, 1, 0, 0),
            )
            db.session.add(paquete)
            db.session.commit()

            assert paquete.oferta_vigente() is True
            assert paquete.precio_efectivo() == 800

            paquete.oferta_hasta = datetime(2020, 1, 1, 0, 0)
            db.session.commit()
            assert paquete.oferta_vigente() is False
            assert paquete.precio_efectivo() == 1000

    def test_tarifas_admin_solo_superadmin(self, client, app):
        sa = _make_user(app, "sa@test.com", "superadmin")
        pds = _make_user(app, "pds@test.com", "pds")

        ok = client.get("/api/v1/wallet/admin/tarifas", headers=_headers(app, sa))
        assert ok.status_code == 200
        claves = {i["clave"] for i in ok.get_json()["items"]}
        assert {"pct_contrato", "precio_moneda_cop", "min_monedas_contrato"} <= claves
        assert all(i["descripcion"] for i in ok.get_json()["items"])

        deny = client.get("/api/v1/wallet/admin/tarifas", headers=_headers(app, pds))
        assert deny.status_code == 403

    def test_patch_tarifas_recalcula_paquetes(self, client, app):
        sa = _make_user(app, "sa@test.com", "superadmin")
        headers = _headers(app, sa)

        resp = client.patch(
            "/api/v1/wallet/admin/tarifas",
            json={"pct_contrato": 4.5},
            headers=headers,
        )
        assert resp.status_code == 200, resp.get_json()
        valores = {i["clave"]: i["valor"] for i in resp.get_json()["items"]}
        assert valores["pct_contrato"] == 4.5
        assert resp.get_json()["paquetes_recalculados"] == 0

        con_paquetes = client.patch(
            "/api/v1/wallet/admin/tarifas",
            json={"precio_moneda_cop": 250},
            headers=headers,
        )
        assert con_paquetes.status_code == 200
        body = con_paquetes.get_json()
        with app.app_context():
            total = PaqueteMonedas.query.count()
        assert body["paquetes_recalculados"] == total
        assert total > 0

    def test_buscar_usuarios(self, client, app):
        sa = _make_user(app, "sa@test.com", "superadmin")
        uid = _make_user(app, "buscado@test.com", "solicitante", monedas=42)

        resp = client.get(
            "/api/v1/wallet/admin/usuarios?q=buscado", headers=_headers(app, sa)
        )
        assert resp.status_code == 200
        items = resp.get_json()["items"]
        assert [i["id"] for i in items] == [uid]
        assert items[0]["monedas_saldo"] == 42
        assert items[0]["email"] == "buscado@test.com"

    def test_billetera_usuario_admin(self, client, app):
        sa = _make_user(app, "sa@test.com", "superadmin")
        uid = _make_user(app, "buscado@test.com", "pds", monedas=7)
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))
        client.post(f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers)

        resp = client.get(
            f"/api/v1/wallet/admin/usuarios/{uid}/billetera", headers=_headers(app, sa)
        )
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["user"]["id"] == uid
        assert body["user"]["rol"] == "pds"
        assert body["wallet"]["user_id"] == uid
        assert body["monedas"]["total"] == 7 + data["monedas"]
        assert body["resumen"]["rol"] == "pds"
        assert isinstance(body["movimientos"], list) and body["movimientos"]
        assert isinstance(body["compras"], list) and len(body["compras"]) == 1

    def test_admin_compras_paginado(self, client, app):
        sa = _make_user(app, "sa@test.com", "superadmin")
        uid = _make_user(app, "comprador@test.com", "solicitante")
        headers = _headers(app, uid)
        data = _checkout(client, headers, _paquete_id(app))
        client.post(f"/api/v1/wallet/pagos/{data['pago_id']}/confirmar", headers=headers)

        resp = client.get(
            "/api/v1/wallet/admin/compras?page=1&per_page=10",
            headers=_headers(app, sa),
        )
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["total"] == 1
        fila = body["items"][0]
        assert fila["user_email"] == "comprador@test.com"
        assert fila["usuario_nombre"] == "comprador"
        assert fila["paquete_nombre"]

        deny = client.get(
            "/api/v1/wallet/admin/compras", headers=headers
        )
        assert deny.status_code == 403
