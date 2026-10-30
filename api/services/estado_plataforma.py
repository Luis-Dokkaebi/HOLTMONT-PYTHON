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
    "Límite de uso agotado por insuficiencia de espacio en base de datos. "
    "La plataforma detectó que el almacenamiento contratado ya no es suficiente "
    "para el volumen de datos del proyecto."
)


def estado() -> Dict[str, Any]:
    """Respuesta de `GET /api/estado`. Lee el entorno en cada llamada."""
    disponible = hay_base_configurada()
    return {
        "success": True,
        "disponible": disponible,
        "mensaje": "" if disponible else MENSAJE_LIMITE_DE_USO,
    }


def bloqueo_de_login() -> Optional[Dict[str, Any]]:
    """Lo que contesta `/api/login` sin base; `None` si se puede validar el acceso."""
    if hay_base_configurada():
        return None
    return {"success": False, "message": MENSAJE_LIMITE_DE_USO, "limiteDeUso": True}
