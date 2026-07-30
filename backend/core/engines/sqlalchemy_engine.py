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


class SqlAlchemyEngine:
    """Implementación de `DataEngine` contra Postgres directo."""

    nombre = "sqlalchemy"
    soporta_transacciones = True
    soporta_candados = True

    def __init__(self, database_url: str, tamano_pool: int = 5, max_desborde: int = 5):
        try:
            from sqlalchemy import MetaData, create_engine
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise ErrorDeMotor(
                "SQLAlchemy no está instalado. Instálalo (requirements.txt) o usa "
                "BACKEND_ENGINE=postgrest si el entorno no tiene TCP al 5432."
            ) from exc

        self._engine = create_engine(
            database_url,
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

    @contextmanager
    def candado(self, clave: str) -> Iterator[None]:
        """
        `pg_advisory_xact_lock`: el equivalente real de `LockService`.

        Tres decisiones que conviene dejar escritas:

        * **`xact` y no `pg_advisory_lock`.** El candado por transacción se
          suelta solo al terminar la transacción, incluso si el proceso muere a
          media petición. Un candado de sesión en serverless, donde la conexión
          la presta un pooler y se reutiliza, se quedaría tomado para siempre.
        * **Se abre una transacción alrededor.** Sin ella no hay a qué atar el
          candado, y además es lo que hace atómico el par "leer el consecutivo
          más alto / escribir la fila con ese folio": si estuvieran en
          transacciones distintas, el candado no serviría de nada.
        * **`hashtext`, no la cadena.** La función toma dos `int`, así que la
          clave se convierte a entero en la base. Dos claves distintas podrían
          colisionar en el mismo hash; eso solo provoca que se serialicen dos
          guardados que podían ir en paralelo, nunca un folio repetido.
        """
        from sqlalchemy import text

        with self.transaccion():
            with self._ejecutor() as conexion:
                conexion.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:clave))"),
                    {"clave": str(clave)},
                )
            yield
