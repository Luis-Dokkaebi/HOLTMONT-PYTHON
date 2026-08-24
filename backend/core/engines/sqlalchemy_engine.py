"""
Motor sobre SQLAlchemy 2.x con pool de conexiones.

Es la ruta de producción: la **única** de las dos con transacciones reales.
Requiere TCP al puerto de Postgres, que el entorno de desarrollo de este
proyecto no tiene (ver `backend/core/engine.py`), así que aquí no puede
ejecutarse; en Vercel sí.

`sqlalchemy` se importa dentro del constructor a propósito: el paquete
`backend` debe poder importarse (y sus pruebas correr) en un entorno que solo
tenga la ruta REST instalada.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

from backend.core.errors import ErrorDeMotor

# El driver de PostgreSQL que este proyecto instala: `psycopg[binary]>=3.1`
# (`requirements.txt`), es decir psycopg **3**. La versión 2 no está declarada
# en ninguna parte y no se instala.
DRIVER_POSTGRES = "psycopg"

# Los esquemas que un humano escribe cuando copia una cadena de conexión, y que
# SQLAlchemy NO resuelve al driver instalado:
#
# * `postgresql://` es lo que entrega el panel de Supabase en "Connection
#   string". SQLAlchemy lo manda al dialecto por defecto, `psycopg2`, y la
#   conexión muere con `ModuleNotFoundError: No module named 'psycopg2'`.
# * `postgres://` es el alias histórico de Heroku. SQLAlchemy 2.x lo retiró:
#   `Can't load plugin: sqlalchemy.dialects:postgres`.
#
# Ninguno de los dos errores habla de la causa real —el esquema de la URL—, y
# los dos aparecen envueltos en un `except` que solo deja una línea en el log.
# El síntoma que llega al usuario es "no hay conexión a la base" con la
# variable de entorno perfectamente puesta.
#
# Se normalizan aquí y no en cada llamador porque el que impone el driver es
# este archivo: es el único que construye el `create_engine`.
ESQUEMAS_SIN_DRIVER = ("postgresql", "postgres")


def normalizar_dsn(database_url: str) -> str:
    """
    El DSN con el driver de Postgres explícito, si hacía falta ponerlo.

    No valida nada: una cadena que no es un DSN sale igual que entró y falla
    más adelante, en `create_engine`, que es donde el error trae contexto. Un
    esquema que ya nombra driver (`postgresql+psycopg2://`) se respeta: quien
    lo escribió sabe lo que quiere, y sobrescribirlo sería adivinar.
    """
    esquema, separador, resto = database_url.partition("://")
    if not separador or "+" in esquema:
        return database_url
    if esquema.lower() not in ESQUEMAS_SIN_DRIVER:
        return database_url
    return f"postgresql+{DRIVER_POSTGRES}://{resto}"


class SqlAlchemyEngine:
    """Implementación de `DataEngine` contra Postgres directo."""

    nombre = "sqlalchemy"
    soporta_transacciones = True
    # El único motor que puede ejecutar el SQL que genera `api/services/agente_sql.py`.
    soporta_sql_crudo = True

    def __init__(self, database_url: str, tamano_pool: int = 5, max_desborde: int = 5):
        try:
            from sqlalchemy import MetaData, create_engine
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise ErrorDeMotor(
                "SQLAlchemy no está instalado. Instálalo (requirements.txt) o usa "
                "BACKEND_ENGINE=postgrest si el entorno no tiene TCP al 5432."
            ) from exc

        self._engine = create_engine(
            normalizar_dsn(database_url),
            pool_size=tamano_pool,
            max_overflow=max_desborde,
            # Una conexión que el pooler cerró de su lado revive como error en
            # la siguiente petición; `pre_ping` la descarta antes de usarla.
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )
        self._metadata = MetaData()
        self._tablas: Dict[str, Any] = {}
        self._conexion = None  # activa solo dentro de `transaccion()`

    # --- utilidades ----------------------------------------------------

    def _tabla(self, nombre: str):
        """Refleja la tabla una vez y la cachea: el esquema vive en la base."""
        if nombre not in self._tablas:
            from sqlalchemy import Table

            try:
                self._tablas[nombre] = Table(
                    nombre, self._metadata, autoload_with=self._engine
                )
            except Exception as exc:
                raise ErrorDeMotor(f"No se pudo reflejar la tabla {nombre}: {exc}") from exc
        return self._tablas[nombre]

    @contextmanager
    def _ejecutor(self):
        """Reutiliza la conexión de la transacción abierta, si la hay."""
        if self._conexion is not None:
            yield self._conexion
            return
        with self._engine.connect() as conexion:
            with conexion.begin():
                yield conexion

    # --- operaciones ---------------------------------------------------

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
        from sqlalchemy import select as sa_select

        t = self._tabla(tabla)
        seleccion = [t.c[c] for c in columnas] if columnas else [t]
        consulta = sa_select(*seleccion)
        for col, val in (donde or {}).items():
            consulta = consulta.where(t.c[col] == val)
        for col, valores in (donde_en or {}).items():
            consulta = consulta.where(t.c[col].in_(list(valores)))
        if orden:
            columna, _, sentido = orden.partition(".")
            expresion = t.c[columna]
            consulta = consulta.order_by(
                expresion.desc() if sentido.lower().startswith("desc") else expresion.asc()
            )
        if limite:
            consulta = consulta.limit(limite)

        try:
            with self._ejecutor() as conexion:
                return [dict(fila) for fila in conexion.execute(consulta).mappings()]
        except ErrorDeMotor:
            raise
        except Exception as exc:
            raise ErrorDeMotor(f"SELECT sobre {tabla} falló: {exc}") from exc

    def upsert(
        self,
        tabla: str,
        filas: Sequence[Dict[str, Any]],
        *,
        en_conflicto: str,
    ) -> List[Dict[str, Any]]:
        """
        `INSERT ... ON CONFLICT (clave) DO UPDATE`, actualizando **solo** las
        columnas presentes en el payload.

        Es la traducción exacta de `resolution=merge-duplicates` de PostgREST:
        una columna ausente conserva lo que ya había en la base. Enviar nulo
        para las ausentes borraría datos que nadie pidió borrar.
        """
        if not filas:
            return []
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        t = self._tabla(tabla)
        claves = list(filas[0].keys())
        sentencia = pg_insert(t).values(list(filas))
        actualizables = {c: sentencia.excluded[c] for c in claves if c != en_conflicto}
        sentencia = (
            sentencia.on_conflict_do_update(index_elements=[en_conflicto], set_=actualizables)
            if actualizables
            else sentencia.on_conflict_do_nothing(index_elements=[en_conflicto])
        ).returning(t)

        try:
            with self._ejecutor() as conexion:
                return [dict(fila) for fila in conexion.execute(sentencia).mappings()]
        except ErrorDeMotor:
            raise
        except Exception as exc:
            raise ErrorDeMotor(f"UPSERT sobre {tabla} falló: {exc}") from exc

    def insertar(self, tabla: str, filas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """INSERT puro: un conflicto de clave es un error, no una fusión."""
        if not filas:
            return []
        from sqlalchemy import insert as sa_insert

        t = self._tabla(tabla)
        sentencia = sa_insert(t).values(list(filas)).returning(t)
        try:
            with self._ejecutor() as conexion:
                return [dict(fila) for fila in conexion.execute(sentencia).mappings()]
        except ErrorDeMotor:
            raise
        except Exception as exc:
            raise ErrorDeMotor(f"INSERT sobre {tabla} falló: {exc}") from exc

    def borrar(self, tabla: str, donde: Dict[str, Any]) -> None:
        if not donde:
            raise ErrorDeMotor(f"DELETE sobre {tabla} sin filtros: se aborta por seguridad")
        from sqlalchemy import delete as sa_delete

        t = self._tabla(tabla)
        sentencia = sa_delete(t)
        for col, val in donde.items():
            sentencia = sentencia.where(t.c[col] == val)
        try:
            with self._ejecutor() as conexion:
                conexion.execute(sentencia)
        except ErrorDeMotor:
            raise
        except Exception as exc:
            raise ErrorDeMotor(f"DELETE sobre {tabla} falló: {exc}") from exc

    @contextmanager
    def transaccion(self) -> Iterator["SqlAlchemyEngine"]:
        """Transacción real: si algo revienta dentro, no queda nada a medias."""
        if self._conexion is not None:  # ya estamos dentro de una
            yield self
            return
        with self._engine.connect() as conexion:
            transaccion = conexion.begin()
            self._conexion = conexion
            try:
                yield self
                transaccion.commit()
            except Exception:
                transaccion.rollback()
                raise
            finally:
                self._conexion = None

    # --- consulta de solo lectura para el agente SQL --------------------

    def consulta_cruda(
        self,
        sql: str,
        *,
        tiempo_maximo_ms: int = 8000,
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta un SELECT ya validado y devuelve las filas como diccionarios.

        Existe para `api/services/agente_sql.py`, que traduce preguntas en
        lenguaje natural a SQL. El texto lo escribe un modelo, así que esta
        función asume lo peor y pone las dos defensas que **no** dependen de
        analizar la cadena:

        * `SET TRANSACTION READ ONLY`, que hace que Postgres rechace cualquier
          escritura aunque el rol tuviera permiso. El guardarraíl de texto del
          agente se puede rodear; esto no.
        * `statement_timeout`, porque una consulta generada puede cruzar la
          tabla consigo misma sin querer y dejar la petición colgada hasta que
          el runtime la mate. Con el límite, falla en segundos y el error vuelve
          al agente, que reintenta.

        Abre siempre su propia conexión y nunca reutiliza la de `transaccion()`:
        marcar como de solo lectura una transacción que está escribiendo la
        rompería a media operación.
        """
        from sqlalchemy import text

        try:
            with self._engine.connect() as conexion:
                with conexion.begin():
                    conexion.execute(text("SET TRANSACTION READ ONLY"))
                    conexion.execute(
                        text(f"SET LOCAL statement_timeout = {int(tiempo_maximo_ms)}")
                    )
                    filas = conexion.execute(text(sql)).mappings()
                    return [dict(fila) for fila in filas]
        except Exception as exc:
            raise ErrorDeMotor(f"La consulta de solo lectura falló: {exc}") from exc
