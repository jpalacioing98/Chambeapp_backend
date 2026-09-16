"""pytest suite — negocio_utils.py: unit tests (RF-N, RF-N-Ratings).

Tests unitarios puros para funciones de utilidad:
- calcular_estado_horario()
- generar_slug()

Run: py -m pytest tests/test_negocio_utils.py -v
"""

import pytest
from datetime import datetime, time, timedelta
from unittest.mock import patch


# ── generar_slug ────────────────────────────────────────────────────────

class TestGenerarSlug:
    """Tests para generar_slug()."""

    @pytest.mark.unit
    def test_slug_simple(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("Mi Negocio") == "mi-negocio"

    @pytest.mark.unit
    def test_slug_con_acentos(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("Restaurante El Corazón") == "restaurante-el-corazon"

    @pytest.mark.unit
    def test_slug_con_caracteres_especiales(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("Farmacia @La #Salud!") == "farmacia-la-salud"

    @pytest.mark.unit
    def test_slug_espacios_multiples(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("  Muchos   espacios  ") == "muchos-espacios"

    @pytest.mark.unit
    def test_slug_vacio(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("") == ""

    @pytest.mark.unit
    def test_slug_solo_numeros(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("12345") == "12345"

    @pytest.mark.unit
    def test_slug_unicode_extremos(self):
        from app.services.negocio_utils import generar_slug
        assert generar_slug("Ñandú") == "nandu"

    @pytest.mark.unit
    def test_slug_guiones_consecutivos(self):
        from app.services.negocio_utils import generar_slug
        result = generar_slug("A--B----C")
        assert "--" not in result
        assert result == "a-b-c"


# ── calcular_estado_horario ────────────────────────────────────────────

class _HorarioMock:
    """Mock simple de NegocioHorario para tests."""
    def __init__(self, dia_semana, abierto, hora_apertura=None, hora_cierre=None):
        self.dia_semana = dia_semana
        self.abierto = abierto
        self.hora_apertura = hora_apertura
        self.hora_cierre = hora_cierre


class TestCalcularEstadoHorario:
    """Tests para calcular_estado_horario()."""

    @pytest.mark.unit
    def test_sin_horarios(self):
        from app.services.negocio_utils import calcular_estado_horario
        result = calcular_estado_horario([])
        assert result["esta_abierto"] is False
        assert result["cierra_pronto"] is False

    @pytest.mark.unit
    def test_dia_cerrado(self):
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        horarios = [_HorarioMock(dia_semana=now.weekday(), abierto=False)]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is False

    @pytest.mark.unit
    def test_dia_abierto_en_horario(self):
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        horarios = [
            _HorarioMock(
                dia_semana=now.weekday(),
                abierto=True,
                hora_apertura=time(0, 0),
                hora_cierre=time(23, 59),
            )
        ]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is True
        assert result["cierra_pronto"] is False

    @pytest.mark.unit
    def test_cierra_pronto_true(self):
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        # Cierre en 10 minutos → cierra_pronto = True
        cierre = (now + timedelta(minutes=10)).time()
        horarios = [
            _HorarioMock(
                dia_semana=now.weekday(),
                abierto=True,
                hora_apertura=time(0, 0),
                hora_cierre=cierre,
            )
        ]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is True
        assert result["cierra_pronto"] is True

    @pytest.mark.unit
    def test_cierra_pronto_false(self):
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        # Cierre en 60 minutos → cierra_pronto = False
        cierre = (now + timedelta(minutes=60)).time()
        horarios = [
            _HorarioMock(
                dia_semana=now.weekday(),
                abierto=True,
                hora_apertura=time(0, 0),
                hora_cierre=cierre,
            )
        ]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is True
        assert result["cierra_pronto"] is False

    @pytest.mark.unit
    def test_fuera_de_horario(self):
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        # Horario: 9:00-10:00, pero probamos con hora_mock que simula otro rango
        horarios = [
            _HorarioMock(
                dia_semana=now.weekday(),
                abierto=True,
                hora_apertura=time(9, 0),
                hora_cierre=time(10, 0),
            )
        ]
        # Si ahora está fuera de 9-10 → cerrado
        result = calcular_estado_horario(horarios)
        if time(9, 0) <= now.time() <= time(10, 0):
            assert result["esta_abierto"] is True
        else:
            assert result["esta_abierto"] is False

    @pytest.mark.unit
    def test_horarios_como_dicts(self):
        """calcular_estado_horario debe aceptar dicts además de objetos."""
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        horarios = [
            {
                "dia_semana": now.weekday(),
                "abierto": True,
                "hora_apertura": time(0, 0),
                "hora_cierre": time(23, 59),
            }
        ]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is True

    @pytest.mark.unit
    def test_sin_hora_apertura_o_cierre(self):
        """Si abierto=True pero faltan horas → cerrado."""
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        horarios = [
            _HorarioMock(
                dia_semana=now.weekday(),
                abierto=True,
                hora_apertura=None,
                hora_cierre=None,
            )
        ]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is False

    @pytest.mark.unit
    def test_no_hay_horario_para_hoy(self):
        """Si no hay horario registrado para el día actual → cerrado."""
        from app.services.negocio_utils import calcular_estado_horario
        now = datetime.now()
        otro_dia = (now.weekday() + 1) % 7
        horarios = [
            _HorarioMock(
                dia_semana=otro_dia,
                abierto=True,
                hora_apertura=time(0, 0),
                hora_cierre=time(23, 59),
            )
        ]
        result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is False

    @pytest.mark.unit
    def test_borde_cierre_exacto(self):
        """Si hora_actual == hora_cierre → abierto (<= es inclusivo)."""
        from app.services.negocio_utils import calcular_estado_horario
        fijo = datetime(2026, 9, 15, 12, 0, 0)
        horarios = [
            _HorarioMock(
                dia_semana=fijo.weekday(),
                abierto=True,
                hora_apertura=time(0, 0),
                hora_cierre=time(12, 0),
            )
        ]
        with patch("app.services.negocio_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fijo
            mock_dt.combine = datetime.combine
            result = calcular_estado_horario(horarios)
        assert result["esta_abierto"] is True
