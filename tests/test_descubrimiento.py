"""Tests del aviso a PDS elegibles y de la cascada de notificaciones.

Cubre:
1. Regresión del bug `NameError` en `_find_nearby_postgis` (PostGIS).
2. Registro de la task de cascada en la instancia Celery del worker.
3. `notificar_pds_elegibles`: filtra por categoría y no duplica.
4. Integración: `POST /solicitudes/` crea cascada + notificación + emisión
   por socket al PDS elegible.
"""

from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.extensions import db
from app.models.cascade import NotificationCascade
from app.models.notification import Notification
from app.models.user import User


# ── Fixtures ──────────────────────────────────────────────────────────────

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
    return client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "rol": rol,
        "acepto_tyc": True, "ip": "127.0.0.1",
    })


def _headers(client, email, password="secret123"):
    data = client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    }).get_json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def _crear_pds_cerca(client, email, habilidades, lat=10.4806, lng=-73.2495):
    """Crea un PDS con perfil completo, habilidades y coordenadas."""
    _register(client, email, rol="pds")
    client.put("/api/v1/users/me/profile", headers=_headers(client, email), json={
        "habilidades": habilidades,
        "categorias": habilidades,
        "zona": "Valledupar",
    })
    user = User.query.filter_by(email=email).first()
    user.profile.latitud = lat
    user.profile.longitud = lng
    user.profile.perfil_completo = True
    db.session.commit()
    return user


def _crear_solicitud(client, email, categoria="plomeria", lat=10.4806, lng=-73.2495):
    _register(client, email, rol="solicitante")
    hdrs = _headers(client, email)
    resp = client.post("/api/v1/solicitudes/", headers=hdrs, json={
        "titulo": f"Servicio de {categoria}",
        "categoria": categoria,
        "descripcion": "Necesito un profesional",
        "ubicacion": "Valledupar",
        "presupuesto": 70000,
        "latitud": lat,
        "longitud": lng,
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"], hdrs


def _crear_solicitud_directa(email, categoria="plomeria", lat=10.4806, lng=-73.2495):
    """Crea la solicitud en BD sin pasar por el endpoint.

    Se usa en los tests unitarios de `notificar_pds_elegibles`: el endpoint
    ya notifica, así que para probar la función aislada hace falta una
    solicitud sin notificaciones previas.
    """
    from app.models.solicitud import Solicitud, EstadoSolicitud

    solicitante = User.query.filter_by(email=email).first()
    solicitud = Solicitud(
        solicitante_id=solicitante.id,
        titulo=f"Servicio de {categoria}",
        categoria=categoria,
        descripcion="Necesito un profesional",
        ubicacion="Valledupar",
        presupuesto=70000,
        latitud=lat,
        longitud=lng,
        radio_km=20.0,
        estado=EstadoSolicitud.PUBLICADO,
    )
    db.session.add(solicitud)
    db.session.commit()
    return solicitud


# ── 1. Regresión del bug NameError en PostGIS ────────────────────────────

class TestPostGISNameError:
    """`User`/`Profile` deben estar disponibles en `_find_nearby_postgis`.

    El import estaba en el scope local de `find_nearby_providers`, así que la
    función hermana `_find_nearby_postgis` reventaba con
    `NameError: name 'User' is not defined` en Docker/prod. Los tests
    (SQLite) no lo detectaban porque caían al fallback Haversine.
    """

    def test_user_y_profile_visibles_en_el_modulo(self):
        from app.ai import geo
        from app.models.user import Profile

        assert geo.User is User
        assert geo.Profile is Profile

    def test_postgis_no_lanza_nameerror(self):
        from app.ai import geo

        cadena = MagicMock()
        cadena.join.return_value.filter.return_value.limit.return_value.all.return_value = []

        fake_db = MagicMock()
        fake_db.session.query.return_value = cadena

        with patch.object(geo, "is_postgis", return_value=True):
            with patch.object(geo, "db", fake_db):
                resultado = geo.find_nearby_providers(10.4806, -73.2495, 20.0)

        assert resultado == []
        # Se consultó el modelo User (no un NameError).
        fake_db.session.query.assert_called_once_with(User)


# ── 2. Celery: una sola instancia y task registrada ──────────────────────

class TestCeleryCascada:
    def test_una_sola_instancia_celery(self):
        """`app.tasks.celery_app` y `app.extensions.celery` son la misma."""
        from app import tasks
        from app.extensions import celery

        assert tasks.celery_app is celery

    def test_celery_tiene_broker_configurado(self):
        """Sin broker, Celery cae a amqp://localhost y `.delay()` falla."""
        from app.extensions import celery

        assert celery.conf.broker_url is not None
        assert celery.conf.broker_url.startswith("redis://")

    def test_send_phase_task_registrada(self):
        """El worker debe conocer la task de cascada."""
        from app.extensions import celery
        import app.services.cascade  # noqa: F401 — registra la task

        assert "app.services.cascade.send_phase_task" in celery.tasks
        assert "app.services.cascade" in (celery.conf.include or [])

    def test_todas_las_tasks_comparten_instancia(self):
        """Las tasks de app.tasks se registran en la instancia compartida."""
        from app import tasks
        from app.extensions import celery

        assert "app.tasks.auto_approve_milestones" in celery.tasks
        assert tasks.celery_app is celery


# ── 3. notificar_pds_elegibles ───────────────────────────────────────────

class TestNotificarPdsElegibles:
    def test_filtra_por_categoria(self, app, client):
        """Un PDS de otra categoría NO debe ser notificado."""
        from app.services.descubrimiento import notificar_pds_elegibles

        _crear_pds_cerca(client, "pds_electrico@test.com", ["electricidad"])
        _register(client, "sol_electrico@test.com", rol="solicitante")
        solicitud = _crear_solicitud_directa("sol_electrico@test.com", categoria="plomeria")

        with patch("app.services.descubrimiento.safe_emit"):
            notificados = notificar_pds_elegibles(solicitud)
        db.session.commit()

        assert notificados == 0
        assert Notification.query.filter_by(tipo="nueva_solicitud").count() == 0

    def test_notifica_a_pds_de_la_misma_categoria(self, app, client):
        from app.services.descubrimiento import notificar_pds_elegibles

        pds = _crear_pds_cerca(client, "pds_plomero@test.com", ["plomería"])
        _register(client, "sol_plomero@test.com", rol="solicitante")
        solicitud = _crear_solicitud_directa("sol_plomero@test.com", categoria="plomería")

        with patch("app.services.descubrimiento.safe_emit"):
            notificados = notificar_pds_elegibles(solicitud)
        db.session.commit()

        assert notificados == 1
        notif = Notification.query.filter_by(
            user_id=pds.id, tipo="nueva_solicitud"
        ).first()
        assert notif is not None
        assert notif.datos["solicitud_id"] == solicitud.id

    def test_no_duplica_notificaciones(self, app, client):
        """La segunda llamada no debe volver a notificar."""
        from app.services.descubrimiento import notificar_pds_elegibles

        pds = _crear_pds_cerca(client, "pds_nodup@test.com", ["plomeria"])
        _register(client, "sol_nodup@test.com", rol="solicitante")
        solicitud = _crear_solicitud_directa("sol_nodup@test.com", categoria="plomeria")

        with patch("app.services.descubrimiento.safe_emit"):
            primera = notificar_pds_elegibles(solicitud)
            db.session.commit()
            segunda = notificar_pds_elegibles(solicitud)
            db.session.commit()

        assert primera == 1
        assert segunda == 0
        assert Notification.query.filter_by(
            user_id=pds.id, tipo="nueva_solicitud"
        ).count() == 1

    def test_flag_apagado_desactiva_el_aviso(self, app, client):
        """`cascade_notifications` es la bandera maestra."""
        from app.models.config import FeatureFlag
        from app.services.descubrimiento import notificar_pds_elegibles

        _crear_pds_cerca(client, "pds_flag@test.com", ["plomeria"])
        _register(client, "sol_flag@test.com", rol="solicitante")
        solicitud = _crear_solicitud_directa("sol_flag@test.com", categoria="plomeria")

        flag = FeatureFlag.query.filter_by(key="cascade_notifications").first()
        if flag is None:
            flag = FeatureFlag(key="cascade_notifications", enabled=True)
            db.session.add(flag)
        flag.enabled = False
        db.session.commit()

        with patch("app.services.descubrimiento.safe_emit"):
            notificados = notificar_pds_elegibles(solicitud)
        db.session.commit()

        assert notificados == 0
        assert Notification.query.filter_by(tipo="nueva_solicitud").count() == 0


# ── 4. Integración: POST /solicitudes/ ───────────────────────────────────

class TestIntegracionPostSolicitud:
    def test_crea_cascada_y_notifica_al_pds(self, app, client):
        """Al publicar una solicitud: cascada activa + notificación + socket."""
        pds = _crear_pds_cerca(client, "pds_int@test.com", ["plomeria"])

        with patch("app.services.cascade.send_phase_task"):
            with patch("app.services.descubrimiento.safe_emit") as mock_emit:
                sol_id, _ = _crear_solicitud(
                    client, "sol_int@test.com", categoria="plomeria"
                )
        db.session.commit()

        # Cascada creada y activa
        cascade = NotificationCascade.query.filter_by(solicitud_id=sol_id).first()
        assert cascade is not None
        assert cascade.estado == "activa"
        # Radios 20/50/100 km con esperas cortas
        radios = [f["radius_km"] for f in cascade.config_json]
        assert radios == [20.0, 50.0, 100.0]
        delays = [f["delay_seconds"] for f in cascade.config_json]
        assert delays == [30, 120, 300]

        # Notificación persistida para el PDS elegible
        notif = Notification.query.filter_by(
            user_id=pds.id, tipo="nueva_solicitud"
        ).first()
        assert notif is not None
        assert notif.datos["solicitud_id"] == sol_id

        # Emisión por socket a la sala del PDS
        salas = [call.kwargs.get("room") for call in mock_emit.call_args_list]
        assert f"user:{pds.id}" in salas

    def test_solicitud_sin_coordenadas_no_notifica(self, app, client):
        """Sin coordenadas no se puede filtrar por radio: no se notifica."""
        pds = _crear_pds_cerca(client, "pds_sincoord@test.com", ["plomeria"])

        with patch("app.services.cascade.send_phase_task"):
            with patch("app.services.descubrimiento.safe_emit"):
                _register(client, "sol_sincoord@test.com", rol="solicitante")
                hdrs = _headers(client, "sol_sincoord@test.com")
                resp = client.post("/api/v1/solicitudes/", headers=hdrs, json={
                    "titulo": "Sin coordenadas",
                    "categoria": "plomeria",
                    "descripcion": "Sin ubicación",
                    "ubicacion": "Valledupar",
                    "presupuesto": 70000,
                })
        db.session.commit()

        assert resp.status_code == 201
        assert Notification.query.filter_by(
            user_id=pds.id, tipo="nueva_solicitud"
        ).count() == 0
