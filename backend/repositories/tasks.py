"""
Repositorio de `tasks`: lectura tipada y escritura transaccional.

Sustituye al camino `sheets.py` -> matriz 2D de strings. Las diferencias que
importan frente al adaptador anterior:

* devuelve objetos con tipos, no celdas de texto;
* **escribe de verdad** (`GSheetsManager.write_values` no tenía ruta a Supabase
  pese a que su docstring lo afirmaba, así que en Vercel todo guardado se
  perdía al terminar la invocación);
* el auto-archivado es un estado calculado de la fila, no un reordenamiento de
  filas alrededor de un separador "TAREAS REALIZADAS".
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from api.services.tracker_rules import (
    is_progress_complete_pct,
    is_terminal_status,
    normalize_staff_name,
    normalize_status,
)
from backend.core.config import Settings, cargar_settings
from backend.core.engine import DataEngine
from backend.core.errors import ColumnaObligatoriaFaltante, EscrituraDeshabilitada
from backend.schemas.task import (
    OBLIGATORIAS_AL_INSERTAR,
    SOLO_LECTURA,
    TaskRead,
    TaskWrite,
)
from backend.services.identity import compute_dedupe_key, primera_persona

TABLA = "tasks"
CLAVE_UPSERT = "dedupe_key"


def _clave_hoja(nombre: Any) -> str:
    """Nombre de hoja normalizado **solo para comparar**, nunca para almacenar."""
    return " ".join(str(nombre or "").split()).upper()


def esta_archivada(fila: Any) -> bool:
    """
    ¿La tarea cuenta como terminada?

    Misma regla que el auto-archivado de `CODIGO.js`: avance al 100 %, estatus
    terminal o CUMPLIMIENTO = SI. Lo que cambia es que aquí es una **propiedad
    calculada de la fila**, no su posición debajo de un separador.

    Ojo con el avance: se usa `is_progress_complete_pct`, no
    `is_progress_complete`. En la base el valor ya está en escala 0-100 y el
    número `1` significa 1 %; con la regla de la hoja, una tarea al 1 % se
    archivaría como terminada.
    """
    avance = getattr(fila, "avance", None) if not isinstance(fila, dict) else fila.get("avance")
    status = getattr(fila, "status", None) if not isinstance(fila, dict) else fila.get("status")
    cumplimiento = (
        getattr(fila, "cumplimiento", None)
        if not isinstance(fila, dict)
        else fila.get("cumplimiento")
    )
    if is_progress_complete_pct(avance):
        return True
    if is_terminal_status(status):
        return True
    return str(cumplimiento or "").upper().strip() == "SI"


class TaskRepository:
    """Acceso a `tasks` sobre cualquier `DataEngine`."""

    def __init__(self, engine: DataEngine, settings: Optional[Settings] = None):
        self.engine = engine
        self.settings = settings or cargar_settings()
        self._indice_hojas: Optional[Dict[str, str]] = None
        self._personas: Optional[Dict[str, str]] = None

    # --- resolución de nombre de hoja -----------------------------------

    def resolver_hoja(self, sheet_name: str) -> str:
        """
        Traduce el nombre que pide el frontend al `source_sheet` almacenado.

        `source_sheet` no está normalizado: hay capitalización mixta
        ("Sebastian Padilla (VENTAS)") y hojas con espacio inicial. El frontend
        pide en mayúsculas, así que una comparación exacta dejaba cinco de las
        siete hojas de ventas en cero filas. Si no hay coincidencia se devuelve
        lo pedido sin tocar, para no inventar hojas.
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

    def listar(self, sheet_name: str) -> List[TaskRead]:
        """Todas las tareas de una hoja, con tipos."""
        real = self.resolver_hoja(sheet_name)
        filas = self.engine.select(TABLA, donde={"source_sheet": real})
        return [TaskRead.model_validate(f) for f in filas]

    def particionar(self, sheet_name: str) -> Tuple[List[TaskRead], List[TaskRead]]:
        """
        (activas, archivadas) de una hoja.

        Reemplaza al separador "TAREAS REALIZADAS": la partición se calcula,
        y el frontend sigue recibiendo la misma forma `{data, history}`.
        """
        activas: List[TaskRead] = []
        archivadas: List[TaskRead] = []
        for tarea in self.listar(sheet_name):
            (archivadas if esta_archivada(tarea) else activas).append(tarea)
        return activas, archivadas

    def por_dedupe_keys(self, claves: Sequence[str]) -> Dict[str, TaskRead]:
        if not claves:
            return {}
        filas = self.engine.select(TABLA, donde_en={CLAVE_UPSERT: list(claves)})
        return {f[CLAVE_UPSERT]: TaskRead.model_validate(f) for f in filas if f.get(CLAVE_UPSERT)}

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

    def resolver_assignee_id(self, assignee_raw: Any) -> Optional[str]:
        """
        `assignee_id` a partir del texto de RESPONSABLE/INVOLUCRADOS.

        Toma **la primera** persona del string. Guardar el compuesto ya llenó
        `people` de filas tipo "RAMIRO RODRIGUEZ, ALFONSO CORREA".
        """
        primero = normalize_staff_name(primera_persona(assignee_raw))
        if not primero:
            return None
        return self._mapa_personas().get(primero)

    # --- escritura -------------------------------------------------------

    def preparar_fila(self, tarea: TaskWrite, sheet_name: str) -> Optional[Dict[str, Any]]:
        """
        `TaskWrite` -> fila lista para el upsert.

        Solo se incluyen las columnas que la petición trajo: en un upsert con
        merge, una columna ausente conserva lo que ya había en la base en vez de
        borrarlo.
        """
        columnas = tarea.columnas()
        for prohibida in SOLO_LECTURA:
            columnas.pop(prohibida, None)

        clave = compute_dedupe_key(columnas.get("folio"), sheet_name)
        if not clave:
            return None

        fila: Dict[str, Any] = {CLAVE_UPSERT: clave, "source_sheet": sheet_name}
        fila.update(columnas)

        if "status" in fila:
            # Un valor no reconocido se conserva tal cual, igual que en
            # `SupabaseSync.normalizeStatus`: si el equipo empieza a usar un
            # estatus nuevo, tirarlo en silencio perdería el dato.
            canonico = normalize_status(fila["status"])
            crudo = "" if fila["status"] is None else str(fila["status"]).strip()
            # NOT NULL: `tasks.status` rechaza el nulo con 23502. La cadena
            # vacía es el "sin estatus" de esta tabla (143 filas reales la usan).
            fila["status"] = canonico or crudo

        # `avance` también es NOT NULL, con DEFAULT 0. Si la petición lo trae
        # vacío se **omite la columna** en vez de mandar nulo: mandarlo aborta
        # el upsert con 23502, y escribir un 0 fabricaría un "0 %" que nadie
        # capturó. Omitida, el merge conserva lo que ya había y un INSERT toma
        # el default.
        if "avance" in fila and fila["avance"] is None:
            fila.pop("avance")

        # Misma razón para el resto de columnas NOT NULL que el cliente puede
        # dejar vacías: nunca se manda nulo a una de ellas.
        for columna in ("folio", "concepto"):
            if columna in fila and fila[columna] is None:
                fila.pop(columna)

        if fila.get("assignee_raw"):
            persona = self.resolver_assignee_id(fila["assignee_raw"])
            if persona:
                fila["assignee_id"] = persona

        return fila

    def guardar_lote(self, sheet_name: str, tareas: Sequence[TaskWrite]) -> List[TaskRead]:
        """
        Guarda un lote en una transacción.

        Las filas se agrupan por su conjunto de columnas y cada grupo va en un
        solo `upsert`. No es un detalle de rendimiento: PostgREST exige que
        todos los objetos de un mismo arreglo tengan las mismas claves, y
        rellenar las que faltan con nulo borraría en la base columnas que el
        cliente no mandó.
        """
        if not self.settings.escritura_habilitada:
            raise EscrituraDeshabilitada(
                "La escritura de tareas está deshabilitada. `SupabaseSync` aún no está "
                f"desplegado, así que Supabase no refleja lo que Sheets tiene hoy; "
                f"escribir ahora pisaría datos vivos. Actívala con BACKEND_TASKS_WRITE_ENABLED=1 "
                f"cuando el puente esté desplegado y la base re-sincronizada."
            )
        if not tareas:
            return []

        filas = [f for f in (self.preparar_fila(t, sheet_name) for t in tareas) if f]
        if not filas:
            return []

        self._validar_altas(filas)

        guardadas: List[Dict[str, Any]] = []
        with self.engine.transaccion():
            for grupo in _agrupar_por_columnas(filas):
                guardadas.extend(
                    self.engine.upsert(TABLA, grupo, en_conflicto=CLAVE_UPSERT)
                )
        return [TaskRead.model_validate(f) for f in guardadas]

    def _validar_altas(self, filas: Sequence[Dict[str, Any]]) -> None:
        """
        Comprueba que las filas **nuevas** traigan las columnas NOT NULL que no
        tienen DEFAULT.

        `tasks` tiene nueve columnas NOT NULL, no solo `status` como decía el
        documento de partida. De ellas, `folio`, `dedupe_key`, `concepto` y
        `source_sheet` no tienen valor por defecto: un alta sin `concepto`
        aborta con 23502. Se detecta aquí para devolver qué falta y en qué
        folio, en vez de un error crudo de Postgres a mitad del lote.

        Solo aplica a las altas: en una actualización el merge conserva lo que
        ya está en la base.
        """
        existentes = set(self.por_dedupe_keys([f[CLAVE_UPSERT] for f in filas]))
        faltantes = [
            (fila.get("folio"), sorted(OBLIGATORIAS_AL_INSERTAR - set(fila)))
            for fila in filas
            if fila[CLAVE_UPSERT] not in existentes and (OBLIGATORIAS_AL_INSERTAR - set(fila))
        ]
        if faltantes:
            detalle = "; ".join(f"folio {folio!r} sin {', '.join(cols)}" for folio, cols in faltantes)
            raise ColumnaObligatoriaFaltante(
                f"No se puede dar de alta una tarea sin las columnas obligatorias: {detalle}"
            )


def _agrupar_por_columnas(filas: Iterable[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    grupos: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for fila in filas:
        grupos.setdefault(tuple(sorted(fila.keys())), []).append(fila)
    return list(grupos.values())
