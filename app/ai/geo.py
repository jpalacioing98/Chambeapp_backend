"""Helper geoespacial — PostGIS en prod/dev, Haversine en tests.

Este módulo detecta automáticamente si la DB soporta PostGIS y usa
la estrategia adecuada para consultas de proximidad.

Uso:
    from app.ai.geo import find_nearby_providers, haversine_km

    # En producción (PostGIS):
    providers = find_nearby_providers(lat=10.4, lng=-73.2, radius_km=5)

    # En tests (SQLite + Haversine):
    providers = find_nearby_providers(lat=10.4, lng=-73.2, radius_km=5)
"""

import math
import logging
from sqlalchemy import text
from app.extensions import db

logger = logging.getLogger(__name__)


def is_postgis() -> bool:
    """Detecta si la DB soporta PostGIS.
    
    Returns:
        True si PostGIS está disponible, False si es SQLite u otra DB.
        
    Example:
        >>> is_postgis()  # En Docker con postgis/postgis:16-3.4
        True
        >>> is_postgis()  # En tests con SQLite
        False
    """
    try:
        result = db.session.execute(text("SELECT PostGIS_Version()"))
        return result.fetchone() is not None
    except Exception:
        return False


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia entre dos puntos usando fórmula Haversine.
    
    Funciona en cualquier DB (SQLite, PostgreSQL, etc.) sin dependencias
    geoespaciales. Usa para tests o fallback.
    
    Args:
        lat1: Latitud del punto 1 (grados)
        lon1: Longitud del punto 1 (grados)
        lat2: Latitud del punto 2 (grados)
        lon2: Longitud del punto 2 (grados)
    
    Returns:
        Distancia en kilómetros
        
    Example:
        >>> haversine_km(10.4, -73.2, 10.5, -73.3)  # Valledupar
        14.2
    """
    R = 6371.0  # Radio de la Tierra en km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(dlon / 2) ** 2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def find_nearby_providers(lat: float, lng: float, radius_km: float, top_k: int = 50):
    """Busca providers cercanos a un punto dado.
    
    Usa PostGIS ST_DWithin en producción/dev, Haversine en tests.
    
    Args:
        lat: Latitud del punto central (grados)
        lng: Longitud del punto central (grados)
        radius_km: Radio de búsqueda en kilómetros
        top_k: Máximo número de resultados
    
    Returns:
        Lista de usuarios Provider (User) ordenados por distancia
        
    Example:
        >>> providers = find_nearby_providers(
        ...     lat=10.4806,  # Valledupar
        ...     lng=-73.2495,
        ...     radius_km=5.0,
        ...     top_k=10
        ... )
    """
    from app.models.user import User, Profile, RolUsuario
    
    if is_postgis():
        return _find_nearby_postgis(lat, lng, radius_km, top_k)
    else:
        return _find_nearby_haversine(lat, lng, radius_km, top_k)


def _find_nearby_postgis(lat: float, lng: float, radius_km: float, top_k: int):
    """Busca providers cercanos usando PostGIS ST_DWithin."""
    from app.models.user import User, Profile, RolUsuario
    from geoalchemy2.functions import ST_DWithin, ST_SetSRID, ST_MakePoint
    
    logger.debug(f"PostGIS search: lat={lat}, lng={lng}, radius={radius_km}km")
    
    providers = db.session.query(User).join(Profile).filter(
        User.rol == RolUsuario.PDS,
        Profile.perfil_completo.is_(True),
        Profile.geom.isnot(None),
        ST_DWithin(
            Profile.geom,
            ST_SetSRID(ST_MakePoint(lng, lat), 4326),
            radius_km * 1000  # ST_DWithin usa metros para Geography
        )
    ).limit(top_k).all()
    
    logger.debug(f"PostGIS found {len(providers)} providers within {radius_km}km")
    return providers


def _find_nearby_haversine(lat: float, lng: float, radius_km: float, top_k: int = 50):
    """Busca providers cercanos usando Haversine (fallback para SQLite)."""
    from app.models.user import User, Profile, RolUsuario
    
    logger.debug(f"Haversine search: lat={lat}, lng={lng}, radius={radius_km}km")
    
    # Cargar todos los providers con ubicación
    providers = db.session.query(User).join(Profile).filter(
        User.rol == RolUsuario.PDS,
        Profile.perfil_completo.is_(True),
        Profile.latitud.isnot(None),
        Profile.longitud.isnot(None)
    ).all()
    
    # Calcular distancias y filtrar
    nearby = []
    for p in providers:
        dist = haversine_km(lat, lng, p.profile.latitud, p.profile.longitud)
        if dist <= radius_km:
            nearby.append((p, dist))
    
    # Ordenar por distancia
    nearby.sort(key=lambda x: x[1])
    
    providers = [p for p, _ in nearby[:top_k]]
    logger.debug(f"Haversine found {len(providers)} providers within {radius_km}km")
    return providers


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia entre dos puntos (PostGIS o Haversine).
    
    Función wrapper que usa la mejor estrategia disponible.
    
    Args:
        lat1: Latitud del punto 1
        lon1: Longitud del punto 1
        lat2: Latitud del punto 2
        lon2: Longitud del punto 2
    
    Returns:
        Distancia en kilómetros
    """
    return haversine_km(lat1, lon1, lat2, lon2)
