"""Catálogo canónico de categorías de negocio (módulo negocios).

Fuente única: `Chambeapp_frontend/src/features/negocio/data/constants.ts`
(`BUSINESS_CATEGORIES`). El backend lo centraliza aquí para exponer el
catálogo completo en `GET /negocios/categorias` (no solo las categorías en uso).

`value` = slug aceptado por el backend (campo libre `categoria_principal`,
alineado con el seed: "gastronomia").
"""

CATEGORIAS_NEGOCIO = [
    "gastronomia",
    "tiendas",
    "belleza",
    "salud",
    "tecnologia",
    "construccion",
    "hogar",
    "otros",
]