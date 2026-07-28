"""
Protocolo de acceso a datos, con dos implementaciones intercambiables.

Por qué dos y no una: se midió que el entorno de desarrollo de este proyecto
**no tiene salida TCP fuera del 443** (probado contra `github.com:22`,
`…pooler.supabase.com:5432` y `:6543`, los tres agotan el tiempo de espera).
Todo el tráfico sale por un proxy HTTPS. En Vercel sí hay TCP y ahí SQLAlchemy
con pool es la opción correcta; desde aquí sería imposible ejecutar una sola
prueba de integración.

La consecuencia honesta es que **las transacciones reales solo existen en la
ruta SQLAlchemy**. PostgREST no expone `BEGIN`/`COMMIT`: lo máximo que
garantiza es la atomicidad de una sentencia, es decir, un único `POST` con un
arreglo de filas. Por eso el protocolo expone `soporta_transacciones` y el
repositorio de tareas está escrito para que un lote quepa siempre en una sola
sentencia; así el comportamiento es el mismo con ambos motores y la diferencia
se limita a qué ocurre si se mezclan varias tablas.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional, Protocol, Sequence, runtime_checkable

from backend.core.config import Settings, cargar_settings
from backend.core.errors import SinMotorConfigurado


@runtime_checkable
class DataEngine(Protocol):
    """Operaciones mínimas que necesita un repositorio."""

    nombre: str
    soporta_transacciones: bool

    def select(
        self,
        tabla: str,
        *,
        columnas: Optional[Sequence[str]] = None,
        donde: Optional[Dict[str, Any]] = None,
        donde_en: Optional[Dict[str, Sequence[Any]]] = None,
        orden: Optional[str] = None,
        limite: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Filas como diccionarios, **con los tipos que devuelve la base**."""
        ...

    def upsert(
        self,
        tabla: str,
        filas: Sequence[Dict[str, Any]],
        *,
        en_conflicto: str,
    ) -> List[Dict[str, Any]]:
        """Inserta o actualiza por `en_conflicto`. Devuelve las filas resultantes."""
        ...

    @contextmanager
    def transaccion(self) -> Iterator["DataEngine"]:
        """Contexto transaccional. En PostgREST no hay tal cosa y se documenta."""
        ...


def construir_engine(settings: Optional[Settings] = None) -> DataEngine:
    """
    Elige el motor: `BACKEND_ENGINE` manda; si no, SQLAlchemy cuando hay
    `DATABASE_URL` y PostgREST cuando hay `SUPABASE_URL`/`KEY`.

    Se prefiere SQLAlchemy porque es el único con transacciones reales; la
    ruta REST es el respaldo para entornos sin TCP al 5432.
    """
    cfg = settings or cargar_settings()

    if cfg.motor_forzado == "sqlalchemy":
        return _sqlalchemy(cfg)
    if cfg.motor_forzado == "postgrest":
        return _postgrest(cfg)
    if cfg.motor_forzado == "memoria":
        from backend.core.engines.memoria import MemoryEngine

        return MemoryEngine()

    if cfg.hay_sqlalchemy:
        return _sqlalchemy(cfg)
    if cfg.hay_postgrest:
        return _postgrest(cfg)

    raise SinMotorConfigurado(
        "No hay motor de datos configurado: define DATABASE_URL (Postgres directo) "
        "o SUPABASE_URL y SUPABASE_KEY (PostgREST). Ver .env.example."
    )


def _sqlalchemy(cfg: Settings) -> DataEngine:
    if not cfg.database_url:
        raise SinMotorConfigurado("BACKEND_ENGINE=sqlalchemy pero DATABASE_URL está vacía.")
    from backend.core.engines.sqlalchemy_engine import SqlAlchemyEngine

    return SqlAlchemyEngine(cfg.database_url)


def _postgrest(cfg: Settings) -> DataEngine:
    if not (cfg.supabase_url and cfg.supabase_key):
        raise SinMotorConfigurado(
            "BACKEND_ENGINE=postgrest pero faltan SUPABASE_URL o SUPABASE_KEY."
        )
    from backend.core.engines.postgrest import PostgrestEngine

    return PostgrestEngine(cfg.supabase_url, cfg.supabase_key)


def trocear(secuencia: Sequence[Any], tamano: int) -> Iterable[Sequence[Any]]:
    """Divide en lotes. Útil para no rebasar el límite de URL/payload."""
    for inicio in range(0, len(secuencia), tamano):
        yield secuencia[inicio : inicio + tamano]
