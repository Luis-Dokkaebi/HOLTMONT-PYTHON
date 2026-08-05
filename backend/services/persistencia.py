"""
El puente entre el motor de reglas y la base relacional.

`api/services/tracker_rules.py` es el activo más valioso del repo: tiene
paridad probada con `CODIGO.js` y decide el ruteo, la papa caliente, el
reverse sync y la asignación de folios. Pero habla en filas de hoja. Este
módulo toma esas filas y las persiste donde corresponde:

    hoja de ventas  ->  `quotes`   (clave: folio)
    cualquier otra  ->  `tasks`    (clave: dedupe_key = hoja + folio)

Y con eso queda contestada la pregunta de "en qué tabla guarda cada usuario":
**cada usuario escribe en su propia partición `source_sheet`**, que es como el
esquema relacional representa lo que en Google Sheets era la hoja personal de
cada quien. `resolver_hoja()` traduce el nombre que pide el frontend al que
está realmente almacenado, así que una tarea de "LILIANA AYLIN MARTINEZ IBARRA"
cae en la partición existente (` LILIANA AYLIN MARTINEZ IBARRA`, con su espacio
inicial) y no estrena una hoja fantasma.

Por qué existe este módulo y no se llama al repositorio directamente: el camino
vivo (`/api/legacy/saveTrackerBatch`, que es el que usa `index.html`) entrega
filas con encabezados de hoja y mezcladas con metadatos del frontend. La
traducción a columnas, la elección de tabla y la proyección de
`task_involucrados` son una sola decisión y conviene que vivan juntas.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from api.services.tracker_rules import is_sales_sheet
from backend.services.identity import PREFIJOS_GLOBALES
from backend.core.engine import DataEngine, construir_engine
from backend.core.errors import BackendError
from backend.repositories.quotes import QuoteRepository
from backend.repositories.tasks import TaskRepository
from backend.schemas.hoja import lista_de_personas
from backend.schemas.quote import QuoteWrite
from backend.schemas.task import TaskWrite
from backend.services.identity import compute_dedupe_key, primera_persona

# `PPCV3` es el nombre de la vista del PPC maestro, no el de una hoja: no
# existe como `source_sheet` en ninguna tabla. Ver `_guardar_en_ppc_maestro`.
PPC_MAESTRO = "PPCV3"

# Donde caen las tareas nuevas del PPC que no traen responsable. Es la hoja que
# hoy concentra el PPC en la base: 1.019 de sus 1.143 filas con folio `PPC-`.
HOJA_PPC_POR_DEFECTO = "ADMINISTRADOR"


def _es_ppc_maestro(sheet_name: Any) -> bool:
    return str(sheet_name or "").strip().upper() == PPC_MAESTRO


def _clave(nombre: Any) -> str:
    """Nombre normalizado **solo para comparar**, nunca para almacenar."""
    return " ".join(str(nombre or "").split()).upper()


def _misma_persona(a: Any, b: Any) -> bool:
    return bool(_clave(primera_persona(a))) and _clave(primera_persona(a)) == _clave(primera_persona(b))


class ResultadoGuardado:
    """Qué se guardó, dónde y con qué forma de vuelta para el frontend."""

    def __init__(
        self,
        tabla: str,
        hoja: str,
        filas: Sequence[Any],
        mensaje: str = "",
    ):
        self.tabla = tabla
        self.hoja = hoja
        self.filas = list(filas)
        self.mensaje = mensaje
        self.exito = not mensaje

    def __repr__(self) -> str:  # pragma: no cover - ayuda al depurar
        return f"<ResultadoGuardado {self.tabla}/{self.hoja} {len(self.filas)} filas>"


class PersistenciaTracker:
    """
    Guarda filas con forma de hoja en la tabla relacional que les toca.

    Se construye una vez por petición: los repositorios cachean el índice de
    `source_sheet` y el directorio de `people`, y en serverless cada invocación
    empieza de cero de todos modos.
    """

    def __init__(self, engine: Optional[DataEngine] = None):
        self.engine = engine or construir_engine()
        self.tareas = TaskRepository(self.engine)
        self.cotizaciones = QuoteRepository(self.engine)

    # --- resolución -----------------------------------------------------

    def resolver_hoja(self, sheet_name: str) -> str:
        """El `source_sheet` real de una hoja, sea de tareas o de ventas."""
        repo = self.cotizaciones if is_sales_sheet(sheet_name) else self.tareas
        return repo.resolver_hoja(sheet_name)

    # --- escritura ------------------------------------------------------

    def guardar(self, sheet_name: str, filas: Sequence[Dict[str, Any]],
                como_copia: bool = False) -> ResultadoGuardado:
        """
        Persiste un lote de filas de hoja.

        Devuelve un `ResultadoGuardado` en vez de lanzar cuando la base
        rechaza el lote: quien llama (el camino legacy) tiene que poder
        convertir el fallo en un `{success: false, message}` que el frontend ya
        sabe pintar. Lo que **no** se hace nunca es devolver éxito sin haber
        escrito: esa es la mentira que la Fase 0 se dedicó a erradicar.

        `como_copia` marca que estas filas son copias de actividades asignadas o
        delegadas: necesitan fila propia en la hoja de quien las recibe aunque
        el folio sea de secuencia global. Ver `TaskRepository.resolver_clave`.
        """
        if not filas:
            return ResultadoGuardado("", sheet_name, [])

        if _es_ppc_maestro(sheet_name):
            return self._guardar_en_ppc_maestro(filas)

        hoja = self.resolver_hoja(sheet_name)
        de_ventas = is_sales_sheet(sheet_name)
        tabla = "quotes" if de_ventas else "tasks"

        try:
            if de_ventas:
                modelos = [QuoteWrite.desde_hoja(f) for f in filas]
                guardadas = self.cotizaciones.guardar_lote(hoja, modelos)
                con_responsable = set()
            else:
                modelos = [TaskWrite.desde_hoja(f) for f in filas]
                # Solo las filas que trajeron responsable necesitan refrescar la
                # proyección; el resto la deja como estaba.
                con_responsable = {
                    compute_dedupe_key(m.folio, hoja)
                    for m in modelos
                    if "assignee_raw" in m.columnas()
                }
                guardadas = self.tareas.guardar_lote(hoja, modelos, como_copia=como_copia)
        except BackendError as exc:
            return ResultadoGuardado(tabla, hoja, [], mensaje=str(exc))
        except Exception as exc:  # validación de Pydantic, sobre todo
            return ResultadoGuardado(tabla, hoja, [], mensaje=f"Fila inválida: {exc}")

        if con_responsable:
            self._proyectar_involucrados(guardadas, con_responsable)

        return ResultadoGuardado(tabla, hoja, guardadas)

    # --- consecutivos de folio -------------------------------------------

    def ultimo_consecutivo(self, prefijo: str, sheet_name: str) -> int:
        """
        Mayor consecutivo ya usado con ese prefijo.

        El proveedor de secuencias de `tracker_rules` es un contador **en
        memoria del proceso** que arranca en 1000. En serverless cada
        invocación es un proceso nuevo, así que devolvía 1001 una y otra vez:
        la segunda tarea que necesitara folio en una hoja recibía el mismo que
        la primera y, con la escritura ya conectada, el upsert la sobrescribía.

        El alcance de la búsqueda depende del prefijo, y no es un detalle:

        * Los prefijos de secuencia global (`AV-`, `PPC-`, `TG-`…) identifican
          la fila por sí solos, así que hay que mirar **toda la tabla**. Se
          comprobó que 25 folios `AV-` viven en hojas de vendedores y no en la
          maestra: buscar solo en `ANTONIA_VENTAS` habría generado un folio ya
          usado y el upsert habría pisado la cotización de otro.
        * Los prefijos de iniciales (`SP-`, `JO-`) solo son únicos dentro de su
          hoja, que es justo lo que permite la difusión lateral, así que basta
          con mirar esa partición.
        """
        de_ventas = is_sales_sheet(sheet_name)
        tabla = "quotes" if de_ventas else "tasks"
        es_global = prefijo.upper() in PREFIJOS_GLOBALES

        donde = None if es_global else {"source_sheet": self.resolver_hoja(sheet_name)}
        patron = re.compile(rf"^{re.escape(prefijo)}(\d+)$", re.IGNORECASE)

        maximo = 1000
        try:
            for fila in self.engine.select(tabla, columnas=["folio"], donde=donde):
                coincide = patron.match(str(fila.get("folio") or "").strip())
                if coincide:
                    maximo = max(maximo, int(coincide.group(1)))
        except Exception as exc:  # noqa: BLE001
            print(f"[persistencia] No se pudo leer el consecutivo de {prefijo!r}: {exc}")
        return maximo

    # --- PPC maestro ------------------------------------------------------

    def _guardar_en_ppc_maestro(self, filas: Sequence[Dict[str, Any]]) -> ResultadoGuardado:
        """
        Guarda lo que llega desde la vista del PPC maestro (`PPCV3`).

        `PPCV3` **no es una partición**: no existe como `source_sheet` en
        `tasks` ni como tabla. La migración partió la hoja en dos (§7.7 del
        plan): las columnas de tarea se repartieron entre los trackers
        personales (963 en `ADMINISTRADOR`, 39 en `PPCV4`…) y `plan_semanal`
        quedó como índice, con 1.180 filas `source_sheet='PPCV3'` que apuntan
        por `task_folio` a las tareas que forman el PPC.

        Escribir aquí con `source_sheet='PPCV3'` habría estrenado una partición
        que **nadie lee**: la vista reconstruye el PPC resolviendo el índice, no
        consultando esa hoja. La captura habría desaparecido de la pantalla en
        la que se hizo.

        Así que cada fila va a la hoja de su dueño:

        * si la tarea ya existe, a la suya (`preparar_fila` conserva el
          `source_sheet` almacenado);
        * si es nueva, a la del responsable que traiga, y si no trae ninguno a
          `ADMINISTRADOR`, que es donde vive el grueso del PPC.

        Y en ambos casos se asegura su renglón en el índice `plan_semanal`,
        que es lo que la hace parte del PPC maestro.
        """
        por_hoja: Dict[str, List[Dict[str, Any]]] = {}
        for fila in filas:
            por_hoja.setdefault(self._hoja_duena(fila), []).append(fila)

        guardadas: List[Any] = []
        for hoja, del_grupo in por_hoja.items():
            resultado = self.guardar(hoja, del_grupo)
            if not resultado.exito:
                return resultado
            guardadas.extend(resultado.filas)

        self._indexar_en_ppc_maestro(guardadas)
        return ResultadoGuardado("tasks", PPC_MAESTRO, guardadas)

    def _hoja_duena(self, fila: Dict[str, Any]) -> str:
        """
        Hoja a la que pertenece una fila del PPC.

        Por orden: la que ya tiene la tarea en la base, la de su responsable si
        esa hoja existe, y `ADMINISTRADOR` como último recurso. La búsqueda es
        por `folio` y no por `dedupe_key` porque desde el PPC no se sabe en qué
        hoja vive la tarea, que es justo lo que se quiere averiguar.
        """
        modelo = TaskWrite.desde_hoja(fila)
        responsable = primera_persona(modelo.assignee_raw or "")

        folio = str(modelo.folio or "").strip()
        if folio:
            existentes = self.engine.select(
                "tasks", columnas=["source_sheet", "assignee_raw"], donde={"folio": folio}
            )
            hojas = [f["source_sheet"] for f in existentes if f.get("source_sheet")]
            if hojas:
                # Un folio con iniciales puede vivir en varias hojas por
                # difusión lateral; gana la del responsable de esta captura.
                for f in existentes:
                    if responsable and _misma_persona(f.get("assignee_raw"), responsable):
                        return f["source_sheet"]
                return hojas[0]

        if responsable:
            if self.tareas.hoja_existe(responsable):
                return self.tareas.resolver_hoja(responsable)
            # Persona del directorio que todavía no tiene tareas: estrena su
            # partición con el nombre tal como está en `people`, para no crear
            # una hoja con una grafía distinta a la del directorio.
            del_directorio = self.tareas.nombre_de_persona(responsable)
            if del_directorio:
                return del_directorio

        return HOJA_PPC_POR_DEFECTO

    def _indexar_en_ppc_maestro(self, guardadas: Sequence[Any]) -> None:
        """
        Da de alta en `plan_semanal` los folios que aún no estén en el índice.

        Sin este renglón la tarea existe pero no forma parte del PPC maestro, y
        la vista de Planeación Semanal no la muestra. Nunca lanza: la tarea ya
        está guardada.
        """
        folios = [f for f in (getattr(t, "folio", None) for t in guardadas) if f]
        if not folios:
            return
        try:
            indexados = {
                fila.get("task_folio")
                for fila in self.engine.select(
                    "plan_semanal",
                    columnas=["task_folio"],
                    donde={"source_sheet": PPC_MAESTRO},
                    donde_en={"task_folio": folios},
                )
            }
            nuevos = [
                {"task_folio": folio, "source_sheet": PPC_MAESTRO}
                for folio in dict.fromkeys(folios)
                if folio not in indexados
            ]
            if nuevos:
                self.engine.insertar("plan_semanal", nuevos)
        except Exception as exc:  # noqa: BLE001
            print(f"[persistencia] No se pudo indexar en el PPC maestro: {exc}")

    # --- proyección de involucrados --------------------------------------

    def _proyectar_involucrados(self, guardadas: Sequence[Any], claves: set) -> None:
        """
        Refresca `task_involucrados` a partir del string `INVOLUCRADOS`.

        Decisión D del plan: la fuente de verdad sigue siendo la columna de
        texto y esta tabla es una **proyección derivada**, así que se reemplaza
        entera para la tarea en vez de intentar un diff. Son 7.246 filas para
        4.626 tareas: es la vista que permite preguntar "¿en qué anda cada
        persona?" sin recorrer strings con comas.

        Nunca lanza: si la proyección falla, la tarea ya está guardada y perder
        un índice derivado no justifica devolver un error al usuario.
        """
        for tarea in guardadas:
            task_id = getattr(tarea, "id", None)
            if not task_id or getattr(tarea, "dedupe_key", None) not in claves:
                continue
            nombres = lista_de_personas(getattr(tarea, "assignee_raw", None))
            try:
                self.engine.borrar("task_involucrados", {"task_id": task_id})
                if nombres:
                    self.engine.insertar(
                        "task_involucrados",
                        [
                            {
                                "task_id": task_id,
                                "raw_name": n,
                                # `person_id` puede quedar en nulo: hay nombres
                                # en las hojas que no están en `people` y la
                                # columna lo admite. Se conserva el crudo, que
                                # es la fuente de verdad (decisión D).
                                "person_id": self.tareas.resolver_assignee_id(n),
                            }
                            for n in nombres
                        ],
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[persistencia] No se pudo proyectar involucrados de {task_id}: {exc}")


def guardar_filas(
    sheet_name: str,
    filas: Sequence[Dict[str, Any]],
    engine: Optional[DataEngine] = None,
) -> ResultadoGuardado:
    """Atajo de un solo uso, para quien no necesita reutilizar los cachés."""
    return PersistenciaTracker(engine).guardar(sheet_name, filas)
