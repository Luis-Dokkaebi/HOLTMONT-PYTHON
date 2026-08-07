"""
Repositorio de `quotes`: las cotizaciones de las hojas de ventas.

Gemelo de `backend/repositories/tasks.py` para el otro lado del sistema. La
diferencia de fondo entre ambos está en la identidad de la fila:

* En `tasks` la clave es `dedupe_key`, que **incluye la hoja** para los folios
  no globales. Por eso `JO-0009` puede vivir en diez trackers a la vez: cada
  copia es una fila legítima de la difusión lateral ("papa caliente").
* En `quotes` la identidad de una fila es **`(folio, source_sheet)`**, no el
  folio a secas. Una misma cotización puede vivir en dos tablas: la de quien la
  reparte y la de quien la trabaja.

  Fue `folio` a secas hasta el 2026-08-06, y ahí estaba el defecto. La llave
  simple hacía imposible la copia asignada —el upsert la colapsaba contra el
  original— y ya había costado datos en la migración: 25 folios `AV-`, nacidos
  en la tabla de Antonia, acabaron viviendo **solo** en la hoja del vendedor
  porque la llave obligó a que ganara una de las dos filas. Antonia dejó de
  verlos. Ver `docs/DDL_QUOTES_CLAVE_COMPUESTA.sql`.

De ahí la regla que más importa aquí: **`source_sheet` identifica la fila**, así
que se escribe siempre con la hoja que se está guardando. Antes se congelaba el
valor almacenado, y era la única defensa que tenía el "Reverse Sync"
(AGENTS.md §3) para no llevarse la cotización de un vendedor al sincronizar
hacia `ANTONIA_VENTAS`; ahora esa defensa la da la propia clave, porque cada
hoja tiene su fila y escribir en una no toca la otra.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from api.services.tracker_rules import (
    classify_quote_status,
    normalize_staff_name,
)
from backend.core.config import Settings, cargar_settings
from backend.core.engine import DataEngine
from backend.core.errors import ColumnaObligatoriaFaltante, EscrituraDeshabilitada
from backend.schemas.quote import (
    OBLIGATORIAS_AL_INSERTAR,
    SOLO_LECTURA,
    QuoteRead,
    QuoteWrite,
)
from backend.services.identity import primera_persona

TABLA = "quotes"
# Clave de identidad de una fila de `quotes`, en el formato que espera el
# `on_conflict` de PostgREST. El motor en memoria la parte por comas igual.
CLAVE_UPSERT = "folio,source_sheet"
COLUMNAS_CLAVE = ("folio", "source_sheet")


def _clave_hoja(nombre: Any) -> str:
    return " ".join(str(nombre or "").split()).upper()


def esta_cerrada(fila: Any) -> bool:
    """
    ¿La cotización cuenta como cerrada (ganada o perdida)?

    Reutiliza `classify_quote_status`, que es la clasificación con paridad
    probada contra `CODIGO.js` y la que ya alimenta los KPIs. Sirve para
    presentar el historial separado sin depender de un separador de filas.
    """
    estatus = getattr(fila, "estatus", None) if not isinstance(fila, dict) else fila.get("estatus")
    return classify_quote_status(estatus) in {"GANADA", "PERDIDA"}


class QuoteRepository:
    """Acceso a `quotes` sobre cualquier `DataEngine`."""

    def __init__(self, engine: DataEngine, settings: Optional[Settings] = None):
        self.engine = engine
        self.settings = settings or cargar_settings()
        self._indice_hojas: Optional[Dict[str, str]] = None
        self._personas: Optional[Dict[str, str]] = None

    # --- resolución de nombre de hoja -----------------------------------

    def resolver_hoja(self, sheet_name: str) -> str:
        """
        Traduce el nombre pedido al `source_sheet` almacenado.

        Aquí importa más que en `tasks`: cinco de las siete hojas de ventas
        están guardadas con capitalización mixta ("Sebastian Padilla (VENTAS)")
        y el frontend las pide en mayúsculas.
        """
        pedido = str(sheet_name or "")
        if not pedido:
            return pedido
        if self._indice_hojas is None:
            indice: Dict[str, str] = {}
            for fila in self.engine.select(TABLA, columnas=["source_sheet"]):
                real = fila.get("source_sheet")
                if real and _clave_hoja(real) not in indice:
                    indice[_clave_hoja(real)] = real
            self._indice_hojas = indice
        return self._indice_hojas.get(_clave_hoja(pedido), pedido)

    def invalidar_caches(self) -> None:
        self._indice_hojas = None
        self._personas = None

    # --- lectura --------------------------------------------------------

    def listar(self, sheet_name: str) -> List[QuoteRead]:
        real = self.resolver_hoja(sheet_name)
        filas = self.engine.select(TABLA, donde={"source_sheet": real})
        return [QuoteRead.model_validate(f) for f in filas]

    def particionar(self, sheet_name: str) -> Tuple[List[QuoteRead], List[QuoteRead]]:
        """(abiertas, cerradas) de una hoja de ventas."""
        abiertas: List[QuoteRead] = []
        cerradas: List[QuoteRead] = []
        for cotizacion in self.listar(sheet_name):
            (cerradas if esta_cerrada(cotizacion) else abiertas).append(cotizacion)
        return abiertas, cerradas

    def por_folios(self, folios: Sequence[str]) -> Dict[Tuple[str, str], QuoteRead]:
        """
        Cotizaciones ya guardadas con esos folios, indexadas por `(folio, hoja)`.

        Se consulta por folio —que es lo que trae la petición— pero se indexa
        por el par: el mismo folio puede tener fila en la tabla de quien reparte
        y en la de quien recibe, y confundirlas haría que una actualización en
        una hoja se validara contra la fila de la otra.
        """
        if not folios:
            return {}
        filas = self.engine.select(TABLA, donde_en={"folio": list(folios)})
        return {
            (f["folio"], f["source_sheet"]): QuoteRead.model_validate(f)
            for f in filas
            if f.get("folio") and f.get("source_sheet")
        }

    # --- directorio ------------------------------------------------------

    def _mapa_personas(self) -> Dict[str, str]:
        if self._personas is None:
            mapa: Dict[str, str] = {}
            for fila in self.engine.select("people", columnas=["id", "nombre"]):
                nombre = normalize_staff_name(fila.get("nombre"))
                if nombre and nombre not in mapa:
                    mapa[nombre] = fila.get("id")
            self._personas = mapa
        return self._personas

    def resolver_vendedor_id(self, vendedor_raw: Any) -> Optional[str]:
        primero = normalize_staff_name(primera_persona(vendedor_raw))
        if not primero:
            return None
        return self._mapa_personas().get(primero)

    # --- escritura -------------------------------------------------------

    def preparar_fila(
        self,
        cotizacion: QuoteWrite,
        sheet_name: str,
        *,
        previa: Optional[QuoteRead],
    ) -> Optional[Dict[str, Any]]:
        """
        `QuoteWrite` -> fila lista para el upsert.

        Lo único delicado está en `source_sheet`, y son dos cosas a la vez:

        * **Hay que mandarla siempre.** Es NOT NULL, y el upsert de PostgREST
          es un `INSERT ... ON CONFLICT`: Postgres valida el NOT NULL sobre la
          tupla del INSERT antes de resolver el conflicto, así que omitirla en
          una actualización devuelve un 23502. Comprobado contra la base.
        * **Es parte de la identidad de la fila.** Se manda la hoja que se está
          guardando, siempre. Antes se congelaba el valor almacenado porque con
          `folio` como clave primaria una cotización vivía en una sola hoja y
          esa congelación era lo único que evitaba que el "Reverse Sync" hacia
          `ANTONIA_VENTAS` (AGENTS.md §3) se llevara la cotización de un
          vendedor. Con la clave compuesta esa defensa sobra: cada hoja tiene su
          propia fila, y escribir en una no puede mover la otra.
        """
        columnas = cotizacion.columnas()
        for prohibida in SOLO_LECTURA:
            columnas.pop(prohibida, None)

        folio = columnas.get("folio")
        folio = str(folio).strip() if folio is not None else ""
        if not folio:
            return None
        columnas["folio"] = folio

        fila: Dict[str, Any] = dict(columnas)
        fila["source_sheet"] = sheet_name

        if fila.get("vendedor_raw"):
            vendedor = self.resolver_vendedor_id(fila["vendedor_raw"])
            if vendedor:
                fila["vendedor_id"] = vendedor

        return fila

    def guardar_lote(self, sheet_name: str, cotizaciones: Sequence[QuoteWrite]) -> List[QuoteRead]:
        """Guarda un lote con `merge-duplicates` sobre `(folio, source_sheet)`."""
        if not self.settings.escritura_habilitada:
            raise EscrituraDeshabilitada(
                "La escritura de cotizaciones está deshabilitada "
                "(BACKEND_TASKS_WRITE_ENABLED=0)."
            )
        if not cotizaciones:
            return []

        folios = [
            str(c.folio).strip()
            for c in cotizaciones
            if c.folio is not None and str(c.folio).strip()
        ]
        existentes = self.por_folios(folios)

        filas: List[Dict[str, Any]] = []
        for cotizacion in cotizaciones:
            folio = str(cotizacion.folio or "").strip()
            fila = self.preparar_fila(cotizacion, sheet_name,
                                      previa=existentes.get((folio, sheet_name)))
            if fila:
                filas.append(fila)
        if not filas:
            return []

        self._validar_altas(filas, existentes)

        guardadas: List[Dict[str, Any]] = []
        with self.engine.transaccion():
            for grupo in _agrupar_por_columnas(filas):
                guardadas.extend(self.engine.upsert(TABLA, grupo, en_conflicto=CLAVE_UPSERT))
        return [QuoteRead.model_validate(f) for f in guardadas]

    def _validar_altas(
        self, filas: Sequence[Dict[str, Any]], existentes: Dict[Tuple[str, str], QuoteRead]
    ) -> None:
        faltantes = [
            (fila.get("folio"), sorted(OBLIGATORIAS_AL_INSERTAR - set(fila)))
            for fila in filas
            if (fila.get("folio"), fila.get("source_sheet")) not in existentes
            and (OBLIGATORIAS_AL_INSERTAR - set(fila))
        ]
        if faltantes:
            detalle = "; ".join(f"folio {folio!r} sin {', '.join(cols)}" for folio, cols in faltantes)
            raise ColumnaObligatoriaFaltante(
                f"No se puede dar de alta una cotización sin las columnas obligatorias: {detalle}"
            )


def _agrupar_por_columnas(filas: Iterable[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    PostgREST exige que todos los objetos de un mismo arreglo tengan las mismas
    claves, y rellenar las que faltan con nulo borraría en la base columnas que
    el cliente no mandó. Por eso se agrupa antes de mandar.
    """
    grupos: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for fila in filas:
        grupos.setdefault(tuple(sorted(fila.keys())), []).append(fila)
    return list(grupos.values())
