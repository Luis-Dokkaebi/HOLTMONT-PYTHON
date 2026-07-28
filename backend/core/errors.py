"""Errores de la capa de datos. Explícitos para que nada falle en silencio."""

from __future__ import annotations


class BackendError(Exception):
    """Raíz de los errores del backend relacional."""


class SinMotorConfigurado(BackendError):
    """No hay ni DATABASE_URL ni SUPABASE_URL/KEY en el entorno."""


class EscrituraDeshabilitada(BackendError):
    """
    Se intentó escribir con el interruptor apagado.

    Falla ruidosamente a propósito: la lección de la Fase 0 es que una
    escritura que devuelve `{success: true}` sin persistir es peor que un
    error, porque el frontend limpia el borrador y el usuario cree que guardó.
    """


class ErrorDeMotor(BackendError):
    """El motor rechazó la operación (red, permisos, restricción violada)."""

    def __init__(self, mensaje: str, codigo: str = "", detalle: str = ""):
        super().__init__(mensaje)
        self.codigo = codigo
        self.detalle = detalle


class CampoDeSoloLectura(BackendError):
    """El cliente mandó una columna que el servidor no acepta desde fuera."""
