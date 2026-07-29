"""
Repositorio de `quotes`: las cotizaciones de las hojas de ventas.

Gemelo de `backend/repositories/tasks.py` para el otro lado del sistema. La
diferencia de fondo entre ambos está en la identidad de la fila:

* En `tasks` la clave es `dedupe_key`, que **incluye la hoja** para los folios
  no globales. Por eso `JO-0009` puede vivir en diez trackers a la vez: cada
  copia es una fila legítima de la difusión lateral ("papa caliente").
* En `quotes` la clave primaria es `folio` a secas. Una cotización existe una
  sola vez y pertenece a una sola hoja. Se verificó: 661 folios, ninguno
  repetido, ninguno compartido entre hojas.

De ahí la regla que más importa aquí: **`source_sheet` se escribe al dar de
alta y no se vuelve a tocar**. Sin ella, el "Reverse Sync" hacia
`ANTONIA_VENTAS` (AGENTS.md §3) no sincronizaría la cotización de un vendedor:
se la llevaría, cambiándole el dueño en la base.
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
CLAVE_UPSERT = "folio"


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

    def por_folios(self, folios: Sequence[str]) -> Dict[str, QuoteRead]:
        if not folios:
            return {}
        filas = self.engine.select(TABLA, donde_en={CLAVE_UPSERT: list(folios)})
        return {f[CLAVE_UPSERT]: QuoteRead.model_validate(f) for f in filas if f.get(CLAVE_UPSERT)}

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
        * **No puede cambiar de valor.** Si la cotización ya existe se manda la
          hoja *almacenada*, no la que pidió el cliente. Con `folio` como clave
          primaria una cotización vive en una sola hoja, y sin esta regla el
          "Reverse Sync" hacia `ANTONIA_VENTAS` (AGENTS.md §3) no sincronizaría
          la cotización de un vendedor: se la llevaría.
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
        fila["source_sheet"] = (previa.source_sheet if previa else None) or sheet_name

        if fila.get("vendedor_raw"):
            vendedor = self.resolver_vendedor_id(fila["vendedor_raw"])
            if vendedor:
                fila["vendedor_id"] = vendedor

        return fila

    def guardar_lote(self, sheet_name: str, cotizaciones: Sequence[QuoteWrite]) -> List[QuoteRead]:
        """Guarda un lote de cotizaciones con `merge-duplicates` sobre `folio`."""
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
            fila = self.preparar_fila(cotizacion, sheet_name, previa=existentes.get(folio))
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
        self, filas: Sequence[Dict[str, Any]], existentes: Dict[str, QuoteRead]
    ) -> None:
        faltantes = [
            (fila.get("folio"), sorted(OBLIGATORIAS_AL_INSERTAR - set(fila)))
            for fila in filas
            if fila.get("folio") not in existentes and (OBLIGATORIAS_AL_INSERTAR - set(fila))
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
