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


def bloqueo_de_login() -> Optional[Dict[str, Any]]:
    """Lo que contesta `/api/login` sin base; `None` si se puede validar el acceso."""
    if hay_base_configurada():
        return None
    return {"success": False, "message": MENSAJE_LIMITE_DE_USO, "limiteDeUso": True}
