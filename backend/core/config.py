"""
Configuración del backend relacional, resuelta **solo** desde el entorno.

Ni un valor por defecto que sea una credencial, ni siquiera dentro de un
`os.environ.get(clave, "...")`: `tests/test_api_contract.py` lo verifica y la
Fase 0 ya tuvo que limpiar dos sitios donde había contraseñas de producción
escritas en el fuente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# --- Nombres de variables (no valores) ---------------------------------
ENV_DATABASE_URL = "DATABASE_URL"
ENV_SUPABASE_URL = "SUPABASE_URL"
ENV_SUPABASE_KEY = "SUPABASE_KEY"
ENV_ESCRITURA = "BACKEND_TASKS_WRITE_ENABLED"
ENV_MOTOR = "BACKEND_ENGINE"


@dataclass(frozen=True)
class Settings:
    """Instantánea del entorno. Inmutable para que nadie la mute a mitad de una petición."""

    database_url: Optional[str]
    supabase_url: Optional[str]
    supabase_key: Optional[str]
    motor_forzado: Optional[str]
    escritura_habilitada: bool

    @property
    def hay_sqlalchemy(self) -> bool:
        return bool(self.database_url)

    @property
    def hay_postgrest(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


def _bandera(nombre: str, por_defecto: bool = False) -> bool:
    crudo = os.environ.get(nombre, "").strip().lower()
    if not crudo:
        return por_defecto
    if crudo in {"0", "false", "no", "off"}:
        return False
    return crudo in {"1", "true", "si", "sí", "yes", "on"}


def _texto(nombre: str) -> Optional[str]:
    valor = os.environ.get(nombre, "").strip()
    return valor or None


def cargar_settings() -> Settings:
    """
    Lee el entorno en cada llamada, a propósito.

    En serverless cada invocación es un proceso nuevo y cachear la
    configuración en un módulo solo esconde de qué entorno vino. Además las
    pruebas necesitan poder cambiarla con `monkeypatch.setenv`.
    """
    return Settings(
        database_url=_texto(ENV_DATABASE_URL),
        supabase_url=_texto(ENV_SUPABASE_URL),
        supabase_key=_texto(ENV_SUPABASE_KEY),
        motor_forzado=(_texto(ENV_MOTOR) or "").lower() or None,
        # La escritura está ENCENDIDA por defecto desde que Supabase es la base
        # de la aplicación (decisión del dueño, 2026-07: "que cada usuario
        # guarde en su respectiva tabla").
        #
        # Arrancó apagada mientras Supabase era una copia estática de la
        # migración y Google Sheets seguía siendo la fuente de verdad: escribir
        # entonces habría pisado filas que la operación diaria ya había
        # cambiado en la hoja. Con la aplicación leyendo y escribiendo contra
        # Supabase esa razón desaparece, y dejarla apagada tiene el costo
        # contrario y peor: cada guardado del tracker se pierde.
        #
        # `BACKEND_TASKS_WRITE_ENABLED=0` sigue siendo el interruptor de
        # emergencia: apaga la escritura sin desplegar nada.
        escritura_habilitada=_bandera(ENV_ESCRITURA, por_defecto=True),
    )
