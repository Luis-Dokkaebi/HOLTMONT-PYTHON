"""
Estado de la plataforma: si tiene base de datos o está en «Límite de uso».

Para desconectar la base, el dueño borra `SUPABASE_URL`, `SUPABASE_KEY` y
`DATABASE_URL` del despliegue. Sin base, la plataforma no puede guardar ni
leer nada, así que en lugar de pantallas vacías o un «usuario o contraseña
incorrectos» engañoso muestra un único aviso, a quien ya está dentro y a
quien intenta entrar (`index.html` consulta `GET /api/estado` al cargar y
cada minuto).

Volver a poner las variables y redesplegar quita el aviso solo: las páginas
abiertas lo retiran en su siguiente consulta.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.core.engine import hay_base_configurada

MENSAJE_LIMITE_DE_USO = (
    "Se requiere extender los módulos de la infraestructura de la base de datos "
    "debido a que se debe sostener la arquitectura premium de almacenar y asegurar "
    "el performance, disponibilidad, seguridad, backup, observabilidad y gobernanza "
    "de datos para Holtzar."
)

# Etiquetas que el aviso pinta debajo del texto. Son las mismas palabras que
# nombra el mensaje (una prueba lo comprueba): si se cambia uno, se cambia el otro.
PILARES = ("Performance", "Disponibilidad", "Seguridad", "Backup",
           "Observabilidad", "Gobernanza de datos")


def estado() -> Dict[str, Any]:
    """Respuesta de `GET /api/estado`. Lee el entorno en cada llamada."""
    disponible = hay_base_configurada()
    return {
        "success": True,
        "disponible": disponible,
        "mensaje": "" if disponible else MENSAJE_LIMITE_DE_USO,
        "pilares": [] if disponible else list(PILARES),
    }


# Rutas que el bloqueo deja pasar: `/api/estado` es la que avisa del bloqueo, y
# `/api/login` ya contesta el aviso con un 200 que el login sabe mostrar (con un
# 503, `ApiService.login` lo convertiría en «Connection Error»).
RUTAS_EXENTAS = frozenset({"/api/estado", "/api/login"})


def _cuerpo_de_bloqueo() -> Dict[str, Any]:
    """`limiteDeUso` es la marca que `index.html` busca para mostrar el aviso al momento."""
    return {"success": False, "message": MENSAJE_LIMITE_DE_USO, "limiteDeUso": True,
            "pilares": list(PILARES)}


def bloqueo_de_login() -> Optional[Dict[str, Any]]:
    """Lo que contesta `/api/login` sin base; `None` si se puede validar el acceso."""
    if hay_base_configurada():
        return None
    return _cuerpo_de_bloqueo()


def bloqueo_de_ruta(ruta: str) -> Optional[Dict[str, Any]]:
    """
    Cuerpo del 503 con el que se corta una petición sin base; `None` si pasa.

    Abarca toda `/api/`, lecturas y guardados: entre dos consultas de
    `/api/estado` pasa hasta un minuto, y un guardado en ese hueco tiene que
    toparse con el aviso y no con un error cualquiera.
    """
    if not ruta.startswith("/api/") or ruta in RUTAS_EXENTAS:
        return None
    if hay_base_configurada():
        return None
    return _cuerpo_de_bloqueo()
