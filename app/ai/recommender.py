"""RF-05: Motor de Match / Recomendación — enfoque PLUGGEABLE y testable.

Implementación base SIN dependencias ML (heurística transparente, RF-05.4).
La interfaz ``Recommender`` permite cambiar la estrategia (p.ej. VectorRecommender
con sentence-transformers + pgvector) sin tocar rutas ni esquemas.
"""

from abc import ABC, abstractmethod

from app.extensions import db
from app.models.user import User, Profile, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud


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
        cats = list(profile.categorias or [])
        habs = list(profile.habilidades or [])
        return 1 if categoria in cats or categoria in habs else 0

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
                    "categoria": s.categoria,
                    "descripcion": s.descripcion,
                    "ubicacion": s.ubicacion,
                    "presupuesto": s.presupuesto,
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


def get_recommender() -> Recommender:
    """Factory pluggeable: retorna la implementación activa (heurística)."""
    return HeuristicRecommender()
