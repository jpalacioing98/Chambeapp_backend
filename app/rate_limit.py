"""Rate limiting configuration for auth endpoints (P1)."""

from flask import request

# In-memory rate limit storage (in production, use Redis)
_rate_limits: dict[str, list[float]] = {}

# Rate limits
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900  # 15 minutes
REGISTER_MAX_ATTEMPTS = 3
REGISTER_WINDOW_SECONDS = 3600  # 1 hour
PASSWORD_RESET_MAX_ATTEMPTS = 3
PASSWORD_RESET_WINDOW_SECONDS = 3600  # 1 hour


def _get_client_ip() -> str:
    """Obtiene la IP del cliente."""
    if request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr or "unknown"


def _check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """Verifica si se excedió el límite de intentos."""
    import time
    
    now = time.time()
    client_ip = _get_client_ip()
    full_key = f"{key}:{client_ip}"
    
    # Limpiar intentos fuera de la ventana
    if full_key in _rate_limits:
        _rate_limits[full_key] = [
            t for t in _rate_limits[full_key]
            if now - t < window_seconds
        ]
    else:
        _rate_limits[full_key] = []
    
    # Verificar límite
    if len(_rate_limits[full_key]) >= max_attempts:
        return False
    
    # Registrar intento
    _rate_limits[full_key].append(now)
    return True


def check_login_rate_limit() -> bool:
    """Verifica límite de intentos de login."""
    import os
    if os.environ.get("FLASK_TESTING") or os.environ.get("TESTING"):
        return True
    return _check_rate_limit("login", LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS)


def check_register_rate_limit() -> bool:
    """Verifica límite de intentos de registro."""
    import os
    if os.environ.get("FLASK_TESTING") or os.environ.get("TESTING"):
        return True
    return _check_rate_limit("register", REGISTER_MAX_ATTEMPTS, REGISTER_WINDOW_SECONDS)


def check_password_reset_rate_limit() -> bool:
    """Verifica límite de intentos de reseteo de contraseña."""
    import os
    if os.environ.get("FLASK_TESTING") or os.environ.get("TESTING"):
        return True
    return _check_rate_limit("password_reset", PASSWORD_RESET_MAX_ATTEMPTS, PASSWORD_RESET_WINDOW_SECONDS)


def get_rate_limit_remaining(key: str, max_attempts: int, window_seconds: int) -> int:
    """Obtiene el número de intentos restantes."""
    import time
    
    now = time.time()
    client_ip = _get_client_ip()
    full_key = f"{key}:{client_ip}"
    
    if full_key not in _rate_limits:
        return max_attempts
    
    # Contar intentos en la ventana actual
    recent_attempts = [
        t for t in _rate_limits[full_key]
        if now - t < window_seconds
    ]
    
    return max(0, max_attempts - len(recent_attempts))
