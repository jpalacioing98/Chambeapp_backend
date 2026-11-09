"""RF-05: Motor de Match / Recomendación — enfoque PLUGGEABLE y testable.

Implementación base SIN dependencias ML (heurística transparente, RF-05.4).
La interfaz ``Recommender`` permite cambiar la estrategia (p.ej. VectorRecommender
con sentence-transformers + pgvector) sin tocar rutas ni esquemas.

Fase 4: Se agrega HybridRecommender (ML + geoespacial) y ShadowRecommender
(log ML pero usa heurístico para validación A/B).
"""

import logging
from abc import ABC, abstractmethod

import numpy as np

from app.extensions import db
from app.models.user import User, Profile, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud

logger = logging.getLogger(__name__)


class Recommender(ABC):
    """Contrato pluggeable del motor de recomendación (RF-05)."""

    @abstractmethod
    def rank_providers_for_service(self, service: Solicitud, top_n: int = 10) -> list[dict]:
        """Rankea proveedores ('trabajador') para una solicitud dada."""
        raise NotImplementedError

    @abstractmethod
    def rank_services_for_provider(self, profile: Profile, top_n: int = 10) -> list[dict]:
        """Rankea servicios publicados afines al perfil del proveedor."""
        raise NotImplementedError


class HeuristicRecommender(Recommender):
    """Heurística transparente (sin ML). Score = 0.6*cat + 0.3*rep + 0.1*verif."""

    # Pesos (deben sumar 1.0) — transparencia RF-05.4
    W_CATEGORIA = 0.6
    W_REPUTACION = 0.3
    W_VERIFICADO = 0.1

    def _categoria_match(self, categoria: str, profile: Profile) -> int:
        from app.services.categorias import normalizar_categoria

        cats = list(profile.categorias or [])
        habs = list(profile.habilidades or [])
        objetivo = normalizar_categoria(categoria)
        return 1 if any(
            normalizar_categoria(c) == objetivo for c in cats + habs
        ) else 0

    def _score(self, categoria_match: int, reputacion: float, verificado: bool) -> float:
        return round(
            self.W_CATEGORIA * categoria_match
            + self.W_REPUTACION * reputacion
            + self.W_VERIFICADO * (1 if verificado else 0),
            4,
        )

    def rank_providers_for_service(self, service: Solicitud, top_n: int = 10) -> list[dict]:
        providers = (
            db.session.query(User)
            .join(Profile, Profile.user_id == User.id)
            .filter(User.rol == RolUsuario.PDS)
            .filter(Profile.perfil_completo.is_(True))
            .all()
        )
        results = []
        for p in providers:
            prof = p.profile
            cm = self._categoria_match(service.categoria, prof)
            rep = (prof.calificacion_promedio or 0.0) / 5.0
            ver = bool(prof.verificado)
            score = self._score(cm, rep, ver)
            results.append(
                {
                    "user_id": p.id,
                    "email": p.email,
                    "score": score,
                    "explicacion": (
                        f"Coincidencia de categoría '{service.categoria}': "
                        f"{'sí' if cm else 'no'} (peso {self.W_CATEGORIA}); "
                        f"reputación {prof.calificacion_promedio or 0.0:.1f}/5 "
                        f"(peso {self.W_REPUTACION}); "
                        f"{'verificado' if ver else 'no verificado'} "
                        f"(peso {self.W_VERIFICADO})."
                    ),
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_n]

    def rank_services_for_provider(self, profile: Profile, top_n: int = 10) -> list[dict]:
        services = Solicitud.query.filter_by(estado=EstadoSolicitud.PUBLICADO).all()
        rep = (profile.calificacion_promedio or 0.0) / 5.0
        ver = bool(profile.verificado)
        results = []
        for s in services:
            cm = self._categoria_match(s.categoria, profile)
            score = self._score(cm, rep, ver)
            results.append(
                {
                    "id": s.id,
                    "titulo": s.titulo,
                    "categoria": s.categoria,
                    "descripcion": s.descripcion,
                    "ubicacion": s.ubicacion,
                    "presupuesto": s.presupuesto,
                    "radio_km": s.radio_km,
                    "urgencia": s.urgencia.value if s.urgencia else None,
                    "fecha_deseada": (
                        s.fecha_deseada.isoformat() if s.fecha_deseada else None
                    ),
                    "estado": s.estado.value,
                    "score": score,
                    "explicacion": (
                        f"Servicio '{s.categoria}' coincide con tu perfil: "
                        f"{'sí' if cm else 'no'} (peso {self.W_CATEGORIA}); "
                        f"tu reputación {profile.calificacion_promedio or 0.0:.1f}/5 "
                        f"(peso {self.W_REPUTACION}); "
                        f"{'verificado' if ver else 'no verificado'} "
                        f"(peso {self.W_VERIFICADO})."
                    ),
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_n]


class VectorRecommender(Recommender):
    """STUB para iteración futura (sentence-transformers + pgvector).

    No se instancia en esta iteración (dependencias pesadas no instaladas).
    Implementa la misma interfaz ``Recommender`` para ser pluggeable.
    """

    def rank_providers_for_service(self, service: Solicitud, top_n: int = 10) -> list[dict]:
        raise NotImplementedError(
            "VectorRecommender requiere sentence-transformers + pgvector (Iter futura)."
        )

    def rank_services_for_provider(self, profile: Profile, top_n: int = 10) -> list[dict]:
        raise NotImplementedError(
            "VectorRecommender requiere sentence-transformers + pgvector (Iter futura)."
        )


class HybridRecommender(Recommender):
    """Recommender híbrido: Retrieval geoespacial + Ranking ML.

    Usa PostGIS para filtrar candidatos cercanos y LightGBM para rankear.
    Si ML falla, hace fallback a HeuristicRecommender.
    """

    def __init__(self):
        from app.ai.features import FeatureExtractor
        from app.ai.ml_ranker import MLRanker
        from app.ai.geo import find_nearby_providers

        self.extractor = FeatureExtractor()
        self.ranker = MLRanker()
        self.find_nearby = find_nearby_providers
        self.heuristic = HeuristicRecommender()

    def rank_providers_for_service(self, service: Solicitud, top_n: int = 10) -> list[dict]:
        """Retrieval geoespacial + Ranking ML."""
        if service.latitud is None or service.longitud is None:
            logger.warning(
                "HybridRecommender: solicitud sin coordenadas, fallback to heuristic"
            )
            return self.heuristic.rank_providers_for_service(service, top_n)

        # 1. Retrieval: encontrar candidatos cercanos (respeta el radio de la solicitud)
        radius_km = service.radio_km or 15.0
        radius_km = max(1.0, min(float(radius_km), 100.0))
        candidates = self.find_nearby(
            lat=service.latitud,
            lng=service.longitud,
            radius_km=radius_km,
            top_k=50
        )

        if not candidates:
            logger.warning("HybridRecommender: No candidates found, fallback to heuristic")
            return self.heuristic.rank_providers_for_service(service, top_n)

        # 2. Feature extraction
        X = self.extractor.extract_batch(candidates, service)

        # 3. ML Ranking
        try:
            scores = self.ranker.predict(X)
        except Exception as e:
            logger.error(f"HybridRecommender ML error: {e}, fallback to heuristic")
            return self.heuristic.rank_providers_for_service(service, top_n)

        # 4. Construir resultados
        results = []
        for provider, score in zip(candidates, scores):
            features = self.extractor.extract_for_provider(provider, service)
            results.append({
                "user_id": provider.id,
                "email": provider.email,
                "score": float(score),
                "explicacion": self.ranker.explain(features),
                "features": features,
                "model_version": self.ranker.version
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:top_n]
        for i, result in enumerate(results):
            result["ranking"] = i + 1
        return results

    def rank_services_for_provider(self, profile: Profile, top_n: int = 10) -> list[dict]:
        """Ranking de servicios para un proveedor."""
        from app.models.user import User

        solicitudes = Solicitud.query.filter_by(estado=EstadoSolicitud.PUBLICADO).all()

        if not solicitudes:
            return []

        results = []
        for s in solicitudes:
            features = self.extractor.extract_for_provider(profile.user, s)
            X = np.array([[features[k] for k in FeatureExtractor.FEATURE_NAMES]])

            try:
                score = self.ranker.predict(X)[0]
            except Exception as e:
                logger.error(f"HybridRecommender ML error: {e}")
                score = 0.5

            results.append({
                "id": s.id,
                "titulo": s.titulo,
                "categoria": s.categoria,
                "descripcion": s.descripcion,
                "ubicacion": s.ubicacion,
                "presupuesto": s.presupuesto,
                "radio_km": s.radio_km,
                "urgencia": s.urgencia.value if s.urgencia else None,
                "fecha_deseada": (
                    s.fecha_deseada.isoformat() if s.fecha_deseada else None
                ),
                "estado": s.estado.value,
                "score": float(score),
                "explicacion": self.ranker.explain(features),
                "model_version": self.ranker.version
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_n]


class ShadowRecommender(Recommender):
    """Shadow mode: log ML pero retorna heurístico.

    Útil para validación A/B sin afectar usuarios.
    """

    def __init__(self):
        self.heuristic = HeuristicRecommender()
        self.hybrid = HybridRecommender()

    def rank_providers_for_service(self, service: Solicitud, top_n: int = 10) -> list[dict]:
        """Log ML predictions pero retorna heurístico."""
        try:
            ml_results = self.hybrid.rank_providers_for_service(service, top_n)
            self._log_comparison(service.id, ml_results)
        except Exception as e:
            logger.error(f"ShadowRecommender ML error: {e}")

        return self.heuristic.rank_providers_for_service(service, top_n)

    def rank_services_for_provider(self, profile: Profile, top_n: int = 10) -> list[dict]:
        """Log ML predictions pero retorna heurístico."""
        try:
            ml_results = self.hybrid.rank_services_for_provider(profile, top_n)
            self._log_comparison(profile.user_id, ml_results)
        except Exception as e:
            logger.error(f"ShadowRecommender ML error: {e}")

        return self.heuristic.rank_services_for_provider(profile, top_n)

    def _log_comparison(self, solicitud_id, ml_results):
        """Log para comparación A/B."""
        logger.info(f"Shadow mode - solicitud {solicitud_id}")
        for r in ml_results[:3]:
            ident = r.get('email') or f"user {r.get('user_id') or r.get('id')}"
            logger.info(f"  ML: {ident} score={r['score']:.4f}")


def get_recommender() -> Recommender:
    """Factory pluggeable: retorna la implementación activa según feature flags.

    Lógica:
        1. Si ml_ranking_enabled y no shadow_mode → HybridRecommender
        2. Si ml_ranking_enabled y shadow_mode → ShadowRecommender
        3. Si ML está apagado → HeuristicRecommender (shadow no aplica)
    """
    from app.models.config import FeatureFlag

    ml_enabled = FeatureFlag.query.filter_by(
        key='ml_ranking_enabled', enabled=True
    ).first() is not None

    shadow_mode = FeatureFlag.query.filter_by(
        key='ml_shadow_mode', enabled=True
    ).first() is not None

    if not ml_enabled:
        return HeuristicRecommender()
    if shadow_mode:
        return ShadowRecommender()
    return HybridRecommender()
