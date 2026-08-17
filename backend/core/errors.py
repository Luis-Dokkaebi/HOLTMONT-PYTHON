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
    """
    El motor rechazó la operación (red, permisos, restricción violada).

    `estado` es el código HTTP con el que respondió PostgREST, o 0 cuando el
    fallo no llegó a tener respuesta (corte de red, tiempo agotado). Se guarda
    aparte del mensaje porque quien traduce el error a pantalla necesita
    distinguir "no existe" (404) de "no tienes permiso" (401/403), y sacarlo
    del texto con una búsqueda de subcadena es frágil: PostgREST no siempre
    manda `code` en el cuerpo, pero el estado siempre está.
    """

    def __init__(self, mensaje: str, codigo: str = "", detalle: str = "", estado: int = 0):
        super().__init__(mensaje)
        self.codigo = codigo
        self.detalle = detalle
        self.estado = estado


class CampoDeSoloLectura(BackendError):
    """El cliente mandó una columna que el servidor no acepta desde fuera."""


class ColumnaObligatoriaFaltante(BackendError):
    """
    Falta una columna NOT NULL sin DEFAULT en un alta.

    `tasks` tiene nueve columnas NOT NULL —no solo `status`—, y `folio`,
    `dedupe_key`, `concepto` y `source_sheet` no tienen valor por defecto. Se
    detecta antes de escribir para decir qué falta y en qué folio, en vez de
    dejar que Postgres aborte el lote con un 23502 sin contexto.
    """
