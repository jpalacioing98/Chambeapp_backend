"""Tests unitarios para geo.py — Helper geoespacial.

Estos tests verifican:
1. Fórmula Haversine (distancia entre puntos)
2. Detección de PostGIS
3. Búsqueda de providers cercanos

Nota: Estos tests usan SQLite (sin PostGIS), por lo que
el fallback a Haversine se prueba automáticamente.
"""

import math
import pytest
from unittest.mock import patch, MagicMock


class TestHaversine:
    """Tests para la fórmula Haversine."""

    def test_same_point_returns_zero(self):
        """Un punto consigo mismo debe retornar 0 km."""
        from app.ai.geo import haversine_km
        
        result = haversine_km(10.4806, -73.2495, 10.4806, -73.2495)
        assert result == 0.0

    def test_known_distance_valledupar(self):
        """Distancia conocida entre puntos de Valledupar."""
        from app.ai.geo import haversine_km
        
        # Puntos aproximados en Valledupar
        # Centro: 10.4806, -73.2495
        # Hospital: 10.4700, -73.2400
        # Distancia estimada: ~1.5 km
        result = haversine_km(10.4806, -73.2495, 10.4700, -73.2400)
        assert 1.0 < result < 2.0

    def test_known_distance_bogota(self):
        """Distancia conocida entre puntos de Bogotá."""
        from app.ai.geo import haversine_km
        
        # Norte: 4.7110, -74.0721
        # Sur: 4.5981, -74.1680
        # Distancia estimada: ~15 km
        result = haversine_km(4.7110, -74.0721, 4.5981, -74.1680)
        assert 10.0 < result < 20.0

    def test_long_distance(self):
        """Distancia larga entre ciudades."""
        from app.ai.geo import haversine_km
        
        # Valledupar a Bogotá: ~650 km
        result = haversine_km(10.4806, -73.2495, 4.7110, -74.0721)
        assert 600.0 < result < 700.0

    def test_symmetry(self):
        """La distancia debe ser simétrica: A→B == B→A."""
        from app.ai.geo import haversine_km
        
        dist_ab = haversine_km(10.4806, -73.2495, 4.7110, -74.0721)
        dist_ba = haversine_km(4.7110, -74.0721, 10.4806, -73.2495)
        assert abs(dist_ab - dist_ba) < 0.001


class TestIsPostgis:
    """Tests para detección de PostGIS."""

    def test_returns_false_when_no_postgis(self):
        """Debe retornar False cuando PostGIS no está disponible."""
        from app.ai.geo import is_postgis
        
        # En tests con SQLite, PostGIS no está disponible
        result = is_postgis()
        assert result is False

    def test_returns_true_with_mock(self):
        """Debe retornar True cuando PostGIS está disponible (mock)."""
        from app.ai.geo import is_postgis
        from app.extensions import db
        
        # Mockear la ejecución de SQL
        with patch.object(db.session, 'execute') as mock_execute:
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ('3.4',)
            mock_execute.return_value = mock_result
            
            result = is_postgis()
            assert result is True

    def test_returns_false_on_exception(self):
        """Debe retornar False cuando hay excepción."""
        from app.ai.geo import is_postgis
        from app.extensions import db
        
        # Mockear excepción
        with patch.object(db.session, 'execute') as mock_execute:
            mock_execute.side_effect = Exception("DB error")
            
            result = is_postgis()
            assert result is False


class TestFindNearbyProviders:
    """Tests para búsqueda de providers cercanos."""

    def test_returns_empty_when_no_providers(self):
        """Debe retornar lista vacía cuando no hay providers."""
        from app.ai.geo import find_nearby_providers, _find_nearby_haversine
        
        # Mockear query vacía
        with patch('app.ai.geo.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.all.return_value = []
            
            result = find_nearby_providers(10.4806, -73.2495, 5.0)
            assert result == []

    def test_haversine_filters_by_radius(self):
        """Haversine debe filtrar por radio."""
        from app.ai.geo import _find_nearby_haversine
        
        # Crear mock de providers
        provider_close = MagicMock()
        provider_close.profile.latitud = 10.4806
        provider_close.profile.longitud = -73.2495
        
        provider_far = MagicMock()
        provider_far.profile.latitud = 11.0000  # Lejos
        provider_far.profile.longitud = -74.0000
        
        with patch('app.ai.geo.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.all.return_value = [
                provider_close, provider_far
            ]
            
            result = _find_nearby_haversine(10.4806, -73.2495, 5.0)
            
            # Solo el provider cercano debe estar en el resultado
            assert len(result) == 1
            assert result[0] == provider_close

    def test_haversine_orders_by_distance(self):
        """Haversine debe ordenar por distancia (más cercano primero)."""
        from app.ai.geo import _find_nearby_haversine
        
        provider_medium = MagicMock()
        provider_medium.profile.latitud = 10.4750
        provider_medium.profile.longitud = -73.2450
        
        provider_close = MagicMock()
        provider_close.profile.latitud = 10.4800
        provider_close.profile.longitud = -73.2490
        
        with patch('app.ai.geo.db.session.query') as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.all.return_value = [
                provider_medium, provider_close
            ]
            
            result = _find_nearby_haversine(10.4806, -73.2495, 5.0)
            
            # El más cercano debe ser el primero
            assert result[0] == provider_close
            assert result[1] == provider_medium


class TestCalculateDistance:
    """Tests para la función wrapper."""

    def test_wrapper_uses_haversine(self):
        """La función wrapper debe usar Haversine."""
        from app.ai.geo import calculate_distance
        
        result = calculate_distance(10.4806, -73.2495, 10.4700, -73.2400)
        assert isinstance(result, float)
        assert result > 0
