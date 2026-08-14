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

    def hoja_existe(self, sheet_name: str) -> bool:
        """
        ¿Hay ya una partición con ese nombre?

        Distinto de `resolver_hoja`, que devuelve lo pedido cuando no hay
        coincidencia y por tanto no permite distinguir "existe con ese mismo
        nombre" de "no existe".
        """
        self.resolver_hoja(sheet_name)  # asegura el índice
        return _clave_hoja(sheet_name) in (self._indice_hojas or {})

    def nombre_de_persona(self, valor: Any) -> Optional[str]:
        """El `people.nombre` almacenado, para no estrenar hojas mal escritas."""
        buscado = normalize_staff_name(primera_persona(valor))
        if not buscado:
            return None
        for fila in self.engine.select("people", columnas=["nombre"]):
            if normalize_staff_name(fila.get("nombre")) == buscado:
                return fila.get("nombre")
        return None

    def invalidar_caches(self) -> None:
        self._indice_hojas = None
        self._personas = None

    # --- lectura --------------------------------------------------------

    def hojas_del_tracker(self, sheet_name: str) -> List[str]:
        """
        Particiones que forman el tracker de una hoja, la pedida primero.

        Son dos cuando la misma persona tiene tareas guardadas bajo sus dos
        nombres —el del organigrama, que es el que abre su vista, y el del
        directorio, con el que se le asignaban—. Es la misma regla que aplica
        `sheets.particiones_del_tracker` en el camino legacy; vive en los dos
        porque los dos leen, y la regla es una sola:
        `organigrama.hojas_de_persona`.
        """
        from api.services import organigrama

        principal = self.resolver_hoja(sheet_name)  # además, asegura el índice
        indice = self._indice_hojas or {}
        hojas = [principal]
        vistas = {_clave_hoja(principal)}
        for alias in organigrama.hojas_de_persona(sheet_name):
            real = indice.get(_clave_hoja(alias))
            if real and _clave_hoja(real) not in vistas:
                vistas.add(_clave_hoja(real))
                hojas.append(real)
        return hojas

    def listar(self, sheet_name: str) -> List[TaskRead]:
        """Todas las tareas de una hoja, con tipos."""
        hojas = self.hojas_del_tracker(sheet_name)
        if len(hojas) == 1:
            filas = self.engine.select(TABLA, donde={"source_sheet": hojas[0]})
        else:
            filas = self.engine.select(TABLA, donde_en={"source_sheet": hojas})
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

    # --- identidad de fila -----------------------------------------------

    def resolver_clave(self, folio: Any, sheet_name: str,
                       como_copia: bool = False) -> Optional[str]:
        """
        `dedupe_key` de una fila, distinguiendo el original de la copia asignada.

        `compute_dedupe_key` devuelve el folio a secas cuando lleva prefijo de
        secuencia global (`AV-`, `PPC-`, `TG-`…). Eso es correcto para la fila
        que nació con ese folio, pero hace **imposible** la copia asignada: dos
        filas en dos hojas distintas comparten clave, el upsert las colapsa y
        `_completar_obligatorias` devuelve el `source_sheet` del primero que
        escribió. Es la razón por la que la delegación de papa caliente se
        guardaba sin error y no aparecía en la tabla del trabajador.

        `como_copia` **tiene que venir de quien llama**, porque la intención no
        se puede deducir de la fila. Son dos operaciones distintas que llegan
        con los mismos datos:

        * Editar `PPC-500` desde la vista del PPC maestro. No es una copia: hay
          que actualizar la fila que ya existe en la hoja de su responsable, no
          estrenar otra. Lo fija `test_una_tarea_existente_no_cambia_de_dueno`.
        * Asignar o delegar `PPC-500` a alguien. Sí es una copia: tiene que
          existir una fila en la tabla de quien la recibe, con su propio avance.

        Aun pedida como copia, si ya hay una fila con la clave global **en
        alguna hoja de esta misma persona** se conserva esa clave: las 4.626
        filas de la migración no cambian de identidad, porque hacerlo duplicaría
        cada tarea que hoy funciona.

        "De esta misma persona" y no "con este mismo nombre de hoja": una
        persona tiene dos nombres —el de su hoja y el del directorio— y con la
        comparación literal, asignarle algo por el segundo nombre no encontraba
        su fila y estrenaba una copia con clave propia. La lectura une las dos
        particiones (`hojas_del_tracker`), así que esa copia salía como una
        tarea duplicada en su tabla. Reportado por el dueño el 2026-08-14 sobre
        el tracker de Carlos Méndez.

        Para los folios con iniciales de persona las dos claves ya coinciden,
        así que esto no cambia nada donde nada estaba roto.
        """
        from api.services.asignacion import clave_de_copia

        global_ = compute_dedupe_key(folio, sheet_name)
        if not global_ or "::" in global_ or not como_copia:
            return global_

        try:
            existentes = self.engine.select(
                TABLA, columnas=["dedupe_key", "source_sheet"],
                donde={CLAVE_UPSERT: global_})
        except Exception:  # noqa: BLE001 - sin base, manda la clave histórica
            return global_

        for fila in existentes:
            if _clave_hoja(fila.get("source_sheet")) in self._mis_hojas(sheet_name):
                return global_
        return clave_de_copia(folio, sheet_name)

    def _mis_hojas(self, sheet_name: str) -> set:
        """
        Claves de comparación de todas las particiones que son de esta persona.

        La pedida más las que el organigrama reconoce como suyas. No se filtra
        por existencia: aquí se responde "¿esta fila ya es mía?", y una hoja que
        todavía no tiene filas no cambia la respuesta.
        """
        from api.services import organigrama

        claves = {_clave_hoja(sheet_name)}
        claves.update(_clave_hoja(alias) for alias in organigrama.hojas_de_persona(sheet_name))
        return claves

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

    def preparar_fila(self, tarea: TaskWrite, sheet_name: str,
                      como_copia: bool = False) -> Optional[Dict[str, Any]]:
        """
        `TaskWrite` -> fila lista para el upsert.

        Solo se incluyen las columnas que la petición trajo: en un upsert con
        merge, una columna ausente conserva lo que ya había en la base en vez de
        borrarlo.

        `como_copia` marca que esta fila es la copia de una actividad asignada
        o delegada, no la original. Ver `resolver_clave`.
        """
        columnas = tarea.columnas()
        for prohibida in SOLO_LECTURA:
            columnas.pop(prohibida, None)

        clave = self.resolver_clave(columnas.get("folio"), sheet_name, como_copia)
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

    def guardar_lote(self, sheet_name: str, tareas: Sequence[TaskWrite],
                     como_copia: bool = False) -> List[TaskRead]:
        """
        Guarda un lote en una transacción.

        Las filas se agrupan por su conjunto de columnas y cada grupo va en un
        solo `upsert`. No es un detalle de rendimiento: PostgREST exige que
        todos los objetos de un mismo arreglo tengan las mismas claves, y
        rellenar las que faltan con nulo borraría en la base columnas que el
        cliente no mandó.

        `como_copia` marca el lote como copias de actividades asignadas o
        delegadas, para que tengan fila propia en la hoja de quien las recibe.
        Ver `resolver_clave`.
        """
        if not self.settings.escritura_habilitada:
            raise EscrituraDeshabilitada(
                "La escritura de tareas está deshabilitada por BACKEND_TASKS_WRITE_ENABLED=0. "
                "Quita esa variable (o ponla en 1) para volver a guardar en la base; "
                "mientras esté apagada, ningún guardado del tracker se persiste."
            )
        if not tareas:
            return []

        filas = [f for f in (self.preparar_fila(t, sheet_name, como_copia) for t in tareas) if f]
        if not filas:
            return []

        existentes = self.por_dedupe_keys([f[CLAVE_UPSERT] for f in filas])
        self._validar_altas(filas, existentes)
        for fila in filas:
            _completar_obligatorias(fila, existentes.get(fila[CLAVE_UPSERT]))

        guardadas: List[Dict[str, Any]] = []
        with self.engine.transaccion():
            for grupo in _agrupar_por_columnas(filas):
                guardadas.extend(
                    self.engine.upsert(TABLA, grupo, en_conflicto=CLAVE_UPSERT)
                )
        return [TaskRead.model_validate(f) for f in guardadas]

    def _validar_altas(
        self, filas: Sequence[Dict[str, Any]], existentes: Dict[str, TaskRead]
    ) -> None:
        """
        Comprueba que las filas **nuevas** traigan las columnas NOT NULL que no
        tienen DEFAULT.

        `tasks` tiene nueve columnas NOT NULL, no solo `status` como decía el
        documento de partida. De ellas, `folio`, `dedupe_key`, `concepto` y
        `source_sheet` no tienen valor por defecto: un alta sin `concepto`
        aborta con 23502. Se detecta aquí para devolver qué falta y en qué
        folio, en vez de un error crudo de Postgres a mitad del lote.

        Solo aplica a las altas: para una actualización, `_completar_obligatorias`
        rellena lo que falte desde la fila ya almacenada.
        """
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


def _completar_obligatorias(fila: Dict[str, Any], previa: Optional[TaskRead]) -> None:
    """
    Rellena desde la fila almacenada las columnas NOT NULL que la petición no
    trajo.

    Sin esto, **toda actualización parcial fallaba con un 400**. La razón es
    que un upsert de PostgREST es un `INSERT ... ON CONFLICT DO UPDATE`, y
    Postgres valida las restricciones NOT NULL sobre la tupla del INSERT
    *antes* de resolver el conflicto. Guardar solo el AVANCE de una tarea que
    ya existe mandaba `{dedupe_key, avance}` y la base contestaba:

        null value in column "folio" of relation "tasks" violates not-null
        constraint   (código 23502)

    Comprobado contra la base real. Es el mismo agujero que tiene hoy
    `SupabaseSync.buildTaskRow` en `CODIGO.js`, que también descarta las
    columnas sin valor antes de mandar el lote.
    """
    if previa is None:
        return
    for columna in OBLIGATORIAS_AL_INSERTAR:
        if fila.get(columna) is None:
            valor = getattr(previa, columna, None)
            if valor is not None:
                fila[columna] = valor

    # `source_sheet` de una fila que ya existe NO se pisa: manda el dueño
    # almacenado.
    #
    # Para los folios con iniciales de persona (`JO-0009`) da igual: la hoja va
    # dentro del `dedupe_key`, así que la fila encontrada ya es la de esa hoja.
    # Importa para los folios de secuencia global (`PPC-`, `AV-`), cuya clave es
    # el folio a secas y por tanto tienen **una sola** fila en toda la base.
    # Sin esta regla, abrir una tarea desde el PPC maestro y guardarla se la
    # llevaría de la hoja de su responsable, y una distribución lateral se la
    # robaría al dueño anterior.
    #
    # Es una divergencia deliberada con `SupabaseSync.mirrorBatch` de
    # `CODIGO.js`, que sí reescribe `source_sheet` en cada espejo; conviene
    # alinear el puente en esa dirección cuando se despliegue.
    if previa.source_sheet:
        fila["source_sheet"] = previa.source_sheet


def _agrupar_por_columnas(filas: Iterable[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    grupos: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for fila in filas:
        grupos.setdefault(tuple(sorted(fila.keys())), []).append(fila)
    return list(grupos.values())
