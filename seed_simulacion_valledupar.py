"""Seed de simulación de Valledupar (alias del seed unificado).

El seed único vive en `seed.py` (10 meses de datos: usuarios, negocios,
solicitudes, ofertas, contratos, chambas, pagos, KYC, portafolio con imágenes,
calificaciones, confianza, chat, notificaciones, tickets, disputas, anuncios,
auditoría y métricas históricas).

Este archivo conserva el comando histórico y delega en `seed.main()`:

    python seed_simulacion_valledupar.py --reset
    python seed_simulacion_valledupar.py --reset --profile full
    python seed_simulacion_valledupar.py --reset --scale 0.5
"""

from __future__ import annotations

from seed import main

if __name__ == "__main__":
    raise SystemExit(main())
