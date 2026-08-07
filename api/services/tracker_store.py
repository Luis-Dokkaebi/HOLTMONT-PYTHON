"""
======================================================================
ORQUESTADOR DEL TRACKER — capa de persistencia sobre tracker_rules
======================================================================
Aplica las reglas de negocio (idénticas a las de CODIGO.js) sobre los
datos reales y los persiste en Supabase: cada fila cae en la partición
`source_sheet` de su dueño, en `tasks` o en `quotes` según la hoja.

La lectura sigue entrando por `gs_manager`, que reconstruye la matriz de la
hoja desde las tablas; la escritura va por `backend/services/persistencia.py`,
que trabaja con columnas y claves en vez de con una matriz de texto.

Los imports de la capa de datos son perezosos a propósito: `tracker_rules`
debe poder probarse sin credenciales de Supabase.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from api.services import asignacion
from api.services import tracker_rules as rules
from backend.services import auditoria

MAKE_WEBHOOK_ENV = "MAKE_WEBHOOK_URL"
GEMINI_KEY_ENV = "GEMINI_API_KEY"
GEMINI_MODEL = "gemini-1.5-flash"

# Último reporte del agente de métricas (en producción conviene persistirlo
# en la base; aquí se mantiene en memoria del proceso, como el Properties
# Service de Apps Script).
_LAST_AGENT_REPORT: Dict[str, Any] = {}


# ----------------------------------------------------------------------
# Acceso a datos
# ----------------------------------------------------------------------

def _manager():
    from api.services.sheets import gs_manager
    return gs_manager


def read_values(sheet_name: str) -> List[List[Any]]:
    try:
        values = _manager().get_sheet_values(sheet_name)
        return [list(r) for r in values] if values else []
    except Exception as exc:  # pragma: no cover - depende de la infraestructura
        print(f"[tracker_store] No se pudo leer {sheet_name}: {exc}")
        return []


def read_rows(sheet_name: str):
    """(activas, historial, encabezados) de una hoja."""
    return rules.rows_to_dicts(read_values(sheet_name))


def find_row_object(sheet_name: str, folio: str) -> Optional[Dict[str, Any]]:
    active, history, _ = read_rows(sheet_name)
    target = str(folio).upper().strip()
    for row in list(active) + list(history):
        if str(row.get("FOLIO") or row.get("ID") or "").upper().strip() == target:
            return row
    return None


def sheet_exists(sheet_name: str) -> bool:
    return bool(read_values(sheet_name))


def resolve_worker_sheet(worker_name: str) -> Optional[str]:
    clean = rules.SALES_SUFFIX_RE.sub("", str(worker_name or "")).strip()
    if not clean:
        return None
    if sheet_exists(clean):
        return clean
    if sheet_exists(f"{clean} (VENTAS)"):
        return f"{clean} (VENTAS)"
    return None


# ----------------------------------------------------------------------
# Notificaciones Make.com -> Outlook
# ----------------------------------------------------------------------

def send_to_outlook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Envía el webhook. Nunca lanza: una falla no debe romper el guardado."""
    url = os.environ.get(MAKE_WEBHOOK_ENV, "").strip()
    if not url:
        return {"success": False, "message": "MAKE_WEBHOOK_URL no configurada"}
    if not payload.get("email"):
        return {"success": False, "message": "Responsable sin correo corporativo"}
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return {"success": 200 <= response.status < 300, "code": response.status}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[tracker_store] Webhook fallido: {exc}")
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# Guardado de tareas
# ----------------------------------------------------------------------

def _persistencia():
    """
    Puente hacia la base relacional, construido en cada llamada.

    Diferido a propósito: `tracker_rules` y este módulo tienen que poder
    importarse (y probarse) sin credenciales de Supabase, y en serverless cada
    invocación es un proceso nuevo, así que cachear el motor solo escondería de
    qué entorno vino.
    """
    from backend.services.persistencia import PersistenciaTracker

    return PersistenciaTracker()


# Encabezados con los que se estrena la hoja de alguien que todavía no tiene
# tareas. Sin esto, el primer guardado de una persona nueva moría con "Sin
# cabeceras válidas": `apply_batch_update` necesita una fila de encabezados para
# saber en qué columna va cada dato, y una partición vacía no tiene ninguna.
# Son los nombres de `TASK_HEADER_MAP` / `QUOTE_HEADER_MAP`, es decir, los
# mismos que devuelve la lectura cuando la hoja sí tiene filas.
ENCABEZADOS_TAREA = [
    "FOLIO", "RESPONSABLE", "AREA", "FECHA", "CLASIFICACION", "CONCEPTO", "AVANCE",
    "FECHA_ESTIMADA_FIN", "RELOJ", "RESTRICCIONES", "PRIORIDAD", "RIESGOS",
    "FECHA_RESPUESTA", "CUMPLIMIENTO", "COMENTARIOS", "ESTATUS",
]
ENCABEZADOS_VENTAS = [
    "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION", "VENDEDOR", "F. VISITA",
    "F. INICIO", "F. ENTREGA", "DIAS", "AVANCE", "ESTATUS", "COMENTARIOS", "REQUISITOR",
    "PRIO. COT.", "INFO CLIENTE", "F2", "COTIZACION", "TIMELINE", "LAYOUT", "MONTO",
]


def _matriz_de_trabajo(sheet_name: str) -> List[List[Any]]:
    """La matriz de la hoja, o solo sus encabezados si la partición está vacía."""
    values = read_values(sheet_name)
    if values:
        return values
    return [list(ENCABEZADOS_VENTAS if rules.is_sales_sheet(sheet_name) else ENCABEZADOS_TAREA)]


def _secuencia_desde_la_base(persistencia, sheet_name: str):
    """
    Proveedor de consecutivos para `apply_batch_update`, anclado en la base.

    El proveedor por defecto de `tracker_rules` es un contador en memoria del
    proceso; en serverless devolvía 1001 en cada invocación y la segunda tarea
    sin folio de una hoja acababa con el mismo que la primera. Aquí se parte del
    mayor consecutivo que ya existe. El folio se rellena a cuatro dígitos, que
    es como están los 4.626 existentes (`SP-0007`, `AV-3250`).

    La lectura es perezosa: solo se consulta la base si el lote trae de verdad
    alguna fila sin folio.
    """
    prefijo = rules.generate_prefix(sheet_name)
    estado = {"n": None}

    def siguiente(_clave: str) -> str:
        if estado["n"] is None:
            estado["n"] = persistencia.ultimo_consecutivo(prefijo, sheet_name)
        estado["n"] += 1
        return str(estado["n"]).zfill(4)

    return siguiente


def _persist_batch(sheet_name: str, tasks: List[Dict[str, Any]], skip_notify: bool = False,
                   username: str = "", persistencia=None,
                   como_copia: bool = False) -> rules.BatchResult:
    """
    Aplica las reglas y **persiste el resultado en Supabase**.

    Las dos mitades tienen dueños distintos y conviene verlas separadas:

    1. `rules.apply_batch_update` decide qué pasa con cada fila (búsqueda por
       folio, gatekeeper por `_tempId`, fallback CONCEPTO+FECHA, asignación de
       folio con prefijo, estatus por defecto y notificaciones). Sigue operando
       sobre la matriz de la hoja porque ahí está la paridad probada con
       `CODIGO.js`, y esa matriz ahora se construye leyendo la base.
    2. `PersistenciaTracker` escribe las filas resultantes en `tasks` o en
       `quotes`, cada una bajo el `source_sheet` de su dueño.

    Antes, el paso 2 era `gs_manager.write_values()`, que sin `credentials.json`
    cae en el modo mock y guarda en un diccionario en memoria. En Vercel ese
    diccionario muere al terminar la invocación: el usuario veía "Guardado
    exitoso" y su captura no existía en ningún lado. Es el fallo que describe
    §1.8 del plan y el motivo de esta integración.

    `persistencia` se recibe de fuera cuando un mismo guardado toca varias
    hojas (papa caliente, reverse sync): el puente cachea el índice de
    `source_sheet` y el directorio de `people`, y rehacerlo por cada hoja
    multiplicaría las lecturas de un guardado.
    """
    persistencia = persistencia or _persistencia()
    values = _matriz_de_trabajo(sheet_name)
    result = rules.apply_batch_update(
        values, tasks, sheet_name,
        sequence_provider=_secuencia_desde_la_base(persistencia, sheet_name),
        skip_notify=skip_notify,
    )
    if not result.success:
        return result

    guardado = persistencia.guardar(sheet_name, result.data, como_copia=como_copia)
    if not guardado.exito:
        # Un fallo de escritura NO puede salir como éxito: el frontend marcaría
        # `_isNew = false` y borraría el borrador local del usuario.
        return rules.BatchResult(result.values, [], False, 0, [], message=guardado.mensaje)

    _auditar(persistencia, guardado, username)
    for payload in result.notifications:
        send_to_outlook(payload)
    return result


def _auditar(persistencia, guardado, username: str) -> None:
    """Una línea en `system_log` por fila guardada, como hacía `registrarLog()`."""
    from backend.services import auditoria

    auditoria.registrar_lote(
        [
            auditoria.evento(
                username,
                auditoria.ACCION_ACTUALIZAR,
                auditoria.detalle_tarea(getattr(fila, "folio", None), guardado.hoja),
            )
            for fila in guardado.filas
        ],
        engine=persistencia.engine,
    )


# Prefijo de folio -> hoja maestra a la que hay que devolver el avance.
# `AV-` son las cotizaciones que nacen en la tabla de ventas de Toñita; `AP-`
# las que nacen en el tracker personal de Antonia Pineda, que es otra hoja.
HOJAS_MAESTRAS_POR_PREFIJO = {
    "AV-": rules.SALES_MASTER_SHEET,
    "AP-": rules.ANTONIA_PERSONAL_SHEET,
}


def _hoja_maestra_de_folio(folio: Any) -> Optional[str]:
    texto = str(folio or "").upper().strip()
    for prefijo, hoja in HOJAS_MAESTRAS_POR_PREFIJO.items():
        if texto.startswith(prefijo):
            return hoja
    return None


def _espejar_asignaciones(origen: str, tareas: List[Dict[str, Any]], username: str,
                          persistencia) -> None:
    """
    Escribe una copia de cada actividad en la tabla de quien la recibe.

    Es el "al asignarla como responsable le debe aparecer en su tabla a
    Geraldine y a él": la fila se queda en la tabla de quien asigna **y**
    aparece en la de cada responsable.

    Nunca escribe en `ANTONIA_VENTAS` (`asignacion.hoja_de_persona` la traduce
    al tracker personal de Antonia): esa tabla es de ventas y solo Toñita la
    captura. Y nunca toca las microtareas de papa caliente, que tienen su propio
    reparto por fases más arriba.

    Las copias se agrupan **por hoja destino** y cada hoja recibe un solo
    `_persist_batch`. "Guardar todo" manda la tabla entera, así que una llamada
    por fila convertía un guardado de 50 renglones en 50 viajes a la base.
    """
    por_destino: Dict[str, List[Dict[str, Any]]] = {}
    for tarea in tareas:
        for destino in asignacion.destinos_espejo(origen, tarea, username):
            espejo = asignacion.construir_espejo(origen, tarea, destino, username)
            por_destino.setdefault(destino, []).append(espejo)

    for destino, filas in por_destino.items():
        _persist_batch(destino, filas, skip_notify=True, username=username,
                       persistencia=persistencia, como_copia=True)


def _tabla_de(hoja_origen: Any) -> str:
    """Tabla donde viven las copias de lo que se guarda en esta hoja."""
    return "quotes" if rules.is_sales_sheet(hoja_origen) else "tasks"


def _copias_de(persistencia, folio: Any, tabla: str = "tasks") -> List[Dict[str, Any]]:
    """
    Filas que comparten folio: las copias de una misma actividad o cotización.

    El vínculo entre copias es el **folio**, que ya está en la base y no exige
    columna nueva ni metadato que el frontend tenga que recordar. Nunca lanza:
    la tarea ya se guardó y perder la sincronización de una copia no justifica
    devolverle un error a quien capturó.

    `tabla` la decide quien llama a partir de la hoja de origen, porque una
    cotización repartida vive en `quotes` y una actividad asignada en `tasks`.
    Buscar siempre en `tasks` dejaba las copias de cotización sin sincronizar:
    Antonia cerraba al 100 % y la fila del vendedor se quedaba en su avance
    viejo. `quotes` no tiene `assignee_raw`, así que la columna equivalente es
    `vendedor_raw` y se expone con el mismo nombre para que el resto del módulo
    no tenga que distinguir.
    """
    if not persistencia or not folio:
        return []
    de_ventas = tabla == "quotes"
    columna_responsable = "vendedor_raw" if de_ventas else "assignee_raw"
    try:
        filas = list(persistencia.engine.select(
            tabla,
            columnas=["source_sheet", columna_responsable, "concepto", "created_at"],
            donde={"folio": str(folio).strip()}))
        if de_ventas:
            for fila in filas:
                fila["assignee_raw"] = fila.get("vendedor_raw")
        return filas
    except Exception as exc:  # noqa: BLE001
        print(f"[tracker_store] No se pudieron buscar las copias de {folio!r}: {exc}")
        return []


def _hoja_originadora(copias: Sequence[Dict[str, Any]]) -> Optional[str]:
    """
    Hoja donde nació la actividad: la fila más antigua de las que comparten folio.

    No hace falta columna nueva para saberlo. La copia se escribe **después** del
    original —el espejo corre al final del guardado—, así que `created_at` ya
    distingue una cosa de la otra. Las filas sin fecha se van al final, porque
    ordenar `None` junto a texto reventaría la comparación.
    """
    con_hoja = [c for c in copias if c.get("source_sheet")]
    if not con_hoja:
        return None
    return min(con_hoja, key=lambda c: str(c.get("created_at") or "9999"))["source_sheet"]


def _hojas_con_folio(persistencia, folio: str, excepto: Iterable[str] = (),
                     tabla: str = "tasks") -> List[str]:
    """Hojas con una copia de este folio, salvo las indicadas. Sin repetir."""
    fuera = {rules.normalize_staff_name(h) for h in excepto}
    hojas: List[str] = []
    for fila in _copias_de(persistencia, folio, tabla):
        hoja = fila.get("source_sheet")
        if not hoja or rules.normalize_staff_name(hoja) in fuera:
            continue
        hojas.append(hoja)
        fuera.add(rules.normalize_staff_name(hoja))
    return hojas


def _motivo_de_bloqueo_por_reasignacion(persistencia, origen: str,
                                        tareas: List[Dict[str, Any]]) -> str:
    """
    Comprueba la regla "solo el originador reasigna" (decisión del dueño).

    Quien recibe una actividad puede avanzarla y cerrarla, pero no pasársela a
    un tercero: para eso se la devuelve a quien se la dio. Una actividad que
    todavía no existe en la base no tiene originador que proteger — se está
    creando, y crear no es reasignar.

    Devuelve el motivo, o cadena vacía si no hay bloqueo. Se comprueba **antes**
    de escribir nada: guardar la mitad del lote y rechazar la otra dejaría las
    dos tablas contándose historias distintas.
    """
    tabla = _tabla_de(origen)
    for tarea in tareas:
        folio = rules.pick_task_value(tarea, ["FOLIO", "ID"])
        copias = _copias_de(persistencia, folio, tabla)
        originadora = _hoja_originadora(copias)
        if not originadora or rules.normalize_staff_name(originadora) == rules.normalize_staff_name(origen):
            continue

        propia = next(
            (c for c in copias
             if rules.normalize_staff_name(c.get("source_sheet")) == rules.normalize_staff_name(origen)),
            {},
        )
        if asignacion.cambia_el_responsable(tarea, propia.get("assignee_raw")):
            return (f"Solo {originadora} puede reasignar la actividad {folio}: "
                    f"es quien la creó. Puedes avanzarla o cerrarla, y si hay que "
                    f"pasarla a alguien más, pídeselo a {originadora}.")
    return ""


def _folios_reasignados(origen: str, tareas: List[Dict[str, Any]],
                        persistencia) -> set:
    """
    Folios cuyo responsable cambia en esta captura, medidos **antes** de escribir.

    Se compara contra la fila de la hoja de origen, que es la que el usuario
    tiene delante. Si no hay fila almacenada la actividad se está creando, y
    crear no es reasignar: tampoco hay copias que retirar.
    """
    if not persistencia:
        return set()
    # La fila previa de una cotización vive en `quotes`; buscarla en `tasks`
    # no la encontraría y ninguna reasignación de venta se detectaría.
    tabla = _tabla_de(origen)
    reasignados = set()
    for tarea in tareas:
        folio = rules.pick_task_value(tarea, ["FOLIO", "ID"])
        if not folio:
            continue
        propia = next(
            (c for c in _copias_de(persistencia, folio, tabla)
             if rules.normalize_staff_name(c.get("source_sheet"))
             == rules.normalize_staff_name(origen)),
            None,
        )
        if propia is None:
            continue
        if asignacion.cambia_el_responsable(tarea, propia.get("assignee_raw")):
            reasignados.add(str(folio).strip())
    return reasignados


def _retirar_copias_huerfanas(origen: str, tareas: List[Dict[str, Any]], username: str,
                              persistencia, reasignados: Optional[set] = None) -> None:
    """
    Quita la copia de quien dejó de ser responsable.

    Decisión del dueño: al reasignar, la actividad "se retira de la tabla de
    Geraldine" y aparece en la del nuevo responsable, con rastro en `system_log`.

    Dos filas nunca se tocan, y las dos por la misma razón —comparten folio pero
    no son copias de esta asignación—:

    * la de la hoja que está guardando, que es el original;
    * las microtareas de papa caliente, que llevan marca de fase en el CONCEPTO.
      Cambiar el responsable de una cotización no puede borrar el trabajo ya
      repartido entre sus fases.

    Y, sobre todo, **solo se retira cuando el responsable cambió de verdad**.
    Retirar es la mitad de una reasignación: en un guardado que no toca el
    responsable no hay reasignación que ejecutar, así que no hay nada que
    retirar.

    Sin esa condición el retiro corría en todo guardado, y entonces basta con
    que alguien guarde su propia tabla para que desaparezcan las copias de los
    demás: el responsable de las filas de Sebastián es Sebastián, así que la
    lista de hojas vigentes se reduce a la suya y **toda** otra hoja con ese
    folio parece huérfana. No hace falta ningún dato mal escrito; pasa con los
    nombres completos tal como están guardados.

    El 2026-08-07 eso borró 24 filas de producción con un clic en "Guardar
    Todo", que reenvía la tabla entera y disparaba el retiro una vez por fila.
    `cambia_el_responsable` ya existía —`_bloqueo_por_reasignacion` la usa unas
    líneas más arriba— y su docstring ya advertía del caso; solo faltaba
    consultarla aquí.
    """
    if not persistencia:
        return

    tabla = _tabla_de(origen)
    eventos = []
    for tarea in tareas:
        if asignacion.es_delegacion_de_fase(tarea):
            continue
        folio = rules.pick_task_value(tarea, ["FOLIO", "ID"])
        if not folio:
            continue

        if str(folio).strip() not in (reasignados or set()):
            continue

        copias = _copias_de(persistencia, folio, tabla)
        vigentes = {rules.normalize_staff_name(d)
                    for d in asignacion.destinos_espejo(origen, tarea, username)}
        vigentes.add(rules.normalize_staff_name(origen))

        for copia in copias:
            hoja = copia.get("source_sheet")
            if not hoja or rules.normalize_staff_name(hoja) in vigentes:
                continue
            if asignacion.es_delegacion_de_fase({"CONCEPTO": copia.get("concepto")}):
                continue
            clave = asignacion.clave_de_copia(folio, hoja)
            try:
                persistencia.engine.borrar("tasks", {"dedupe_key": clave})
            except Exception as exc:  # noqa: BLE001 - la tarea ya se guardó
                print(f"[tracker_store] No se pudo retirar la copia {clave!r}: {exc}")
                continue
            eventos.append(auditoria.evento(
                username, auditoria.ACCION_ACTUALIZAR,
                f"Retirada copia de {folio} en {hoja} por reasignacion desde {origen}"))

    if eventos:
        auditoria.registrar_lote(eventos, engine=persistencia.engine)


def _sincronizar_copias(origen: str, tareas: List[Dict[str, Any]], username: str,
                        persistencia) -> None:
    """
    Propaga el cambio de estado a las demás copias de la misma actividad.

    Es la otra mitad de la bilateralidad: cuando Geraldine pone su actividad al
    100 %, la copia de Antonio recibe AVANCE y ESTATUS, y el auto-archivado la
    manda a TAREAS REALIZADAS también en su tabla.

    Solo viaja el estado (`asignacion.CAMPOS_BILATERALES`), nunca el CONCEPTO ni
    el RESPONSABLE: quien recibió la actividad no reescribe el texto ni la
    reasigna en la tabla de quien se la dio.

    Igual que el espejo, se agrupa por hoja destino: dos actividades cerradas en
    el mismo guardado que viven en la tabla de la misma persona se le mandan en
    una sola escritura.
    """
    tabla = _tabla_de(origen)
    por_destino: Dict[str, List[Dict[str, Any]]] = {}
    for tarea in tareas:
        cambios = asignacion.campos_sincronizables(tarea)
        if not cambios:
            continue
        # `origen` ya se guardó; la maestra de un folio AV-/AP- la atiende el
        # reverse sync, que además cierra la fase en el timeline.
        maestra = _hoja_maestra_de_folio(cambios["FOLIO"])
        excepto = [origen] + ([maestra] if maestra else [])
        for hoja in _hojas_con_folio(persistencia, cambios["FOLIO"], excepto, tabla):
            por_destino.setdefault(hoja, []).append(dict(cambios))

    for hoja, filas in por_destino.items():
        _persist_batch(hoja, filas, skip_notify=True, username=username,
                       persistencia=persistencia)


def save_tracker_batch(person_name: str, tasks: List[Dict[str, Any]], username: str = "") -> Dict[str, Any]:
    """
    Equivalente de `apiSaveTrackerBatch`: ruteo protegido, papa caliente,
    distribución a vendedores y reverse sync saneado hacia ANTONIA_VENTAS.
    """
    if not tasks:
        return {"success": True, "data": [], "message": "Sin cambios"}

    routing = rules.resolve_tracker_target(person_name, username)
    target = routing["sheet"]
    is_antonia = target.upper() == rules.SALES_MASTER_SHEET.upper()
    # Un solo puente para todo el guardado: la papa caliente y el reverse sync
    # tocan varias hojas y cada uno rehaciéndolo volvería a leer el índice de
    # `source_sheet` y el directorio de `people`.
    persistencia = _persistencia()

    # Solo el originador reasigna. Se comprueba antes de escribir nada.
    bloqueo = _motivo_de_bloqueo_por_reasignacion(persistencia, target, tasks)
    if bloqueo:
        return {"success": False, "message": bloqueo}

    processed: List[Dict[str, Any]] = []
    for raw_task in tasks:
        task = dict(raw_task)
        if is_antonia:
            folio = rules.pick_task_value(task, ["FOLIO", "ID"])
            master = find_row_object(target, folio) if folio else None
            try:
                hot = rules.apply_hot_potato(target, task, master, username)
            except rules.FaseEnCurso as exc:
                # Delegar salteándose una fase abierta no es un error técnico:
                # se contesta con el motivo y sin escribir nada, porque guardar
                # la mitad del lote dejaría el proceso en un estado que el
                # timeline no sabe pintar.
                return {"success": False, "message": str(exc)}
            if hot:
                # Distribución lateral: cada trabajador recibe la fila en SU
                # hoja, es decir, en su propia partición `source_sheet`.
                for worker, row in zip(hot["workers"], hot["rows"]):
                    worker_sheet = resolve_worker_sheet(worker)
                    if worker_sheet:
                        # `como_copia`: la microtarea necesita fila propia en la
                        # hoja del trabajador. Sin esto, las delegaciones de un
                        # folio `AV-` compartían clave y se colapsaban en una.
                        _persist_batch(worker_sheet, [row], username=username,
                                       persistencia=persistencia, como_copia=True)
        processed.append(task)

    # Quién era el responsable ANTES de escribir. Tiene que leerse aquí: el
    # upsert deja en la fila el responsable nuevo, así que preguntárselo después
    # siempre respondería "no cambió" y el retiro no se ejecutaría nunca.
    reasignados = _folios_reasignados(target, processed, persistencia)

    result = _persist_batch(target, processed, username=username,
                            persistencia=persistencia)
    if not result.success:
        return {"success": False, "message": result.message}

    _espejar_asignaciones(target, result.data, username, persistencia)
    _retirar_copias_huerfanas(target, result.data, username, persistencia,
                              reasignados=reasignados)
    _sincronizar_copias(target, result.data, username, persistencia)

    # Reverse Sync: el trabajador cierra su parte y la maestra se entera.
    #
    # El disparo es por **prefijo de folio**, no por nombre de hoja. Antes la
    # condición era `"(VENTAS)" in target`, lo que dejaba fuera el caso normal:
    # una tarea `AV-` delegada por papa caliente cae en la hoja propia del
    # trabajador (`MIGUEL GALLARDO`), que no contiene "(VENTAS)", así que al
    # completarla no se sincronizaba nada y Toñita nunca veía la fase cerrada.
    # Los folios `AP-` (tracker personal de Antonia Pineda) no se sincronizaban
    # en absoluto.
    #
    # Es la regla del original (`apiSaveTrackerBatch`): AV- -> tabla maestra de
    # ventas, AP- -> tracker de Antonia Pineda, desde cualquier hoja de origen.
    for task in processed:
        folio = str(rules.pick_task_value(task, ["FOLIO", "ID"]) or "").upper().strip()
        maestra = _hoja_maestra_de_folio(folio)
        if not maestra:
            continue
        # Sin auto-sincronización: si ya se está guardando en la maestra, el
        # `_persist_batch` de arriba hizo el trabajo.
        if rules.normalize_staff_name(target) == rules.normalize_staff_name(maestra):
            continue
        payload = rules.build_reverse_sync_payload(
            target, task,
            find_row_object(target, folio),
            find_row_object(maestra, folio),
        )
        if payload:
            _persist_batch(maestra, [payload], skip_notify=True,
                           username=username, persistencia=persistencia)

    return {
        "success": True,
        "message": "Guardado exitoso",
        "data": result.data,
        "routing": routing if routing["redirected"] else None,
    }


def update_task(person_name: str, task: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    """Equivalente de `apiUpdateTask` (una sola fila)."""
    res = save_tracker_batch(person_name, [task], username)
    if res.get("success") and res.get("data"):
        res["data"] = res["data"][0]
    return res


def update_ppcv3(task: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    """Equivalente de `apiUpdatePPCV3`: PPCV4 para Toñita, PPCV3 para el resto."""
    sheet = "PPCV4" if rules.normalize_staff_name(username) == "ANTONIA VENTAS" else "PPCV3"
    result = _persist_batch(sheet, [dict(task)], skip_notify=True, username=username)
    if not result.success:
        return {"success": False, "message": result.message}
    return {"success": True, "data": result.data[0] if result.data else None}


def fetch_weekly_plan(username: str = "") -> Dict[str, Any]:
    """
    Equivalente de `apiFetchWeeklyPlanData`.

    `PPCV4` (Toñita) sí resuelve: existe como `source_sheet` en `tasks` con 51
    filas. `PPCV3` **no existe en ninguna tabla con esa forma**, así que para
    todos los demás usuarios esta vista devolvía una tabla vacía con
    `success: true` mientras la consola registraba un `PGRST205` buscando una
    tabla `public.PPCV3` inexistente. Es el mismo fallo silencioso que la Fase 0
    erradicó de `api_service.js`: el usuario no distingue "no hay nada
    planeado" de "la lectura está rota".

    Qué se sabe de `PPCV3` (verificado contra la base):

      * `plan_semanal` tiene 1.180 filas con `source_sheet = 'PPCV3'`, pero solo
        **62** llevan contenido real de planeación (`zona`, `ruta_critica`,
        `cuantificacion_req`, `dias`, `contratista`, `nota_cnc`) y ninguna de
        esas 62 tiene `task_folio`. Son filas de Last Planner, una forma que
        esta vista no sabe pintar: no tiene columna de fecha, así que la
        columna SEMANA que calcula `apiFetchWeeklyPlanData` saldría vacía.
      * Las otras 1.118 son cascarones con `task_folio` + `especialidad` +
        `cumplimiento`. De sus 1.098 folios, **1.056 resuelven a `tasks`**,
        repartidos entre varias hojas (963 en `ADMINISTRADOR`, 39 en `PPCV4`…),
        no bajo un único `source_sheet`.

    Decisión del dueño (2026-07) entre las tres reconstrucciones posibles:
    **`PPCV3` son las tareas cuyo folio aparece en `plan_semanal.task_folio`**,
    resueltas contra `tasks`. `plan_semanal` actúa de índice del PPC maestro.
    La resolución vive en `sheets.py::_filas_del_ppc_maestro()`.
    """
    sheet = "PPCV4" if rules.normalize_staff_name(username) == "ANTONIA VENTAS" else "PPCV3"
    active, history, headers = read_rows(sheet)

    # La vista pinta `S{{ row.SEMANA }}` y espera los encabezados renombrados,
    # igual que devolvía `apiFetchWeeklyPlanData`. Sin esto los datos llegan
    # pero la tabla no los sabe colocar.
    plan = rules.build_weekly_plan(active)
    respuesta: Dict[str, Any] = {
        "success": True,
        "data": plan["data"],
        "history": history,
        "headers": plan["headers"] or headers,
    }
    if not plan["data"] and not history:
        respuesta["_notImplemented"] = True
        respuesta["message"] = (
            f"La hoja {sheet} no tiene equivalente en la base relacional todavía; "
            "no es que no haya actividad planeada. Ver fetch_weekly_plan() y "
            "docs/PLAN_BACKEND_PYTHON.md §7.7."
        )
        print(f"[tracker_store] {sheet} sin origen en la base: se devuelve vacío marcado.")
    return respuesta


def fetch_sales_history() -> Dict[str, Any]:
    """Equivalente de `apiFetchSalesHistory`: cotizaciones agrupadas por vendedor."""
    active, history, headers = read_rows(rules.SALES_MASTER_SHEET)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in list(active) + list(history):
        vendedor = str(rules.pick_task_value(row, ["VENDEDOR", "RESPONSABLE"]) or "SIN ASIGNAR").upper().strip()
        grouped.setdefault(vendedor, []).append(row)
    return {"success": True, "data": grouped, "headers": headers}


# ----------------------------------------------------------------------
# Agente de métricas
# ----------------------------------------------------------------------

def fetch_quote_metrics(month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
    active, history, _ = read_rows(rules.SALES_MASTER_SHEET)
    metrics = rules.compute_quote_metrics(list(active) + list(history), month, year)
    return {"success": True, "metrics": metrics}


def call_gemini(prompt: str) -> Dict[str, Any]:
    key = os.environ.get(GEMINI_KEY_ENV, "").strip()
    if not key:
        return {"success": False, "text": "Sin GEMINI_API_KEY configurada: el reporte se generó solo con reglas."}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        return {"success": True, "text": str(text).strip()}
    except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as exc:
        return {"success": False, "text": f"Error al consultar Gemini: {exc}"}


def run_quote_metrics_agent(month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
    """Equivalente de `runQuoteMetricsAgent`: reglas + Gemini + notificación."""
    global _LAST_AGENT_REPORT
    metrics = fetch_quote_metrics(month, year)["metrics"]
    gemini = call_gemini(rules.build_quote_metrics_prompt(metrics))

    last_run = {
        "timestamp": rules.to_iso_z(datetime.utcnow()),
        "month": metrics["month"],
        "year": metrics["year"],
        "alerts": metrics["alerts"],
        "geminiSummary": gemini["text"],
        "geminiOk": gemini["success"],
        "metrics": metrics,
    }
    _LAST_AGENT_REPORT = last_run

    send_to_outlook({
        "evento": "REPORTE_METRICAS_COTIZACIONES",
        "origen": "tabla de ventas",
        "periodo": f"{metrics['month']}/{metrics['year']}",
        "email": rules.resolve_user_email("ANTONIA_VENTAS"),
        "tasaCierre": metrics["closeRate"],
        "alertas": len(metrics["alerts"]),
        "resumen": gemini["text"],
        "enviadoEn": rules.to_iso_z(datetime.utcnow()),
    })

    return {"success": True, "lastRun": last_run}


def get_last_agent_report() -> Dict[str, Any]:
    if not _LAST_AGENT_REPORT:
        return {"success": True, "hasReport": False, "lastRun": None}
    return {"success": True, "hasReport": True, "lastRun": _LAST_AGENT_REPORT}


def save_gemini_key(key: str) -> Dict[str, Any]:
    clean = str(key or "").strip()
    if not clean:
        return {"success": False, "message": "La key no puede estar vacía."}
    os.environ[GEMINI_KEY_ENV] = clean
    return {"success": True, "message": "Key guardada"}


def check_gemini_key() -> Dict[str, Any]:
    key = os.environ.get(GEMINI_KEY_ENV, "").strip()
    if not key:
        return {"success": True, "hasKey": False, "keyPreview": ""}
    return {"success": True, "hasKey": True, "keyPreview": key[:6] + "***"}


def write_quote_metrics_to_sheet(month: Optional[int] = None, year: Optional[int] = None) -> Dict[str, Any]:
    """
    Guarda una instantánea de los KPIs de cotizaciones en `kpi_cotizaciones`.

    En la hoja, esto pintaba un reporte de varias secciones (indicadores, SLA
    por clase, desglose por cotizador). La tabla relacional tiene otra forma y
    es mejor: `(departamento, total, ganadas, perdidas, snapshot_at)`, una fila
    por cotizador y por corrida, así que las instantáneas se acumulan y se puede
    ver la evolución en vez de solo el último volcado.

    El reporte completo sigue disponible en `/api/legacy/quoteMetrics`, que lo
    calcula al vuelo; lo que se persiste aquí es el histórico.
    """
    metrics = fetch_quote_metrics(month, year)["metrics"]
    momento = datetime.now(timezone.utc).isoformat()

    filas: List[Dict[str, Any]] = [{
        # "TOTAL" es el agregado del periodo; los demás son por cotizador.
        "departamento": "TOTAL",
        "total": metrics["totalCount"],
        "ganadas": metrics["winLoss"]["ganada"],
        "perdidas": metrics["winLoss"]["perdida"],
        "snapshot_at": momento,
    }]
    for v in metrics["byCotizadorArr"]:
        filas.append({
            "departamento": str(v["nombre"]).upper().strip() or "SIN ASIGNAR",
            "total": v["total"],
            "ganadas": v["ganada"],
            "perdidas": v["perdida"],
            "snapshot_at": momento,
        })

    try:
        from backend.core.engine import construir_engine

        construir_engine().insertar("kpi_cotizaciones", filas)
    except Exception as exc:  # noqa: BLE001
        print(f"[tracker_store] No se pudieron guardar los KPIs: {exc}")
        return {"success": False, "message": f"No se pudieron guardar los KPIs: {exc}"}

    return {
        "success": True,
        "message": (f"Instantánea de KPIs guardada: {len(filas)} fila(s) "
                    f"para {metrics['month']}/{metrics['year']}."),
    }


def fetch_info_bank_companies(year: Any, month: Any) -> Dict[str, Any]:
    """Clientes con cotizaciones en un periodo (Banco de Información)."""
    month_map = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
                 "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
    target_month = month_map.get(str(month).upper().strip())
    if target_month is None:
        try:
            target_month = int(month)
        except (TypeError, ValueError):
            return {"success": False, "message": f"Mes inválido: {month}"}
    try:
        target_year = int(year)
    except (TypeError, ValueError):
        target_year = datetime.now().year

    active, history, _ = read_rows(rules.SALES_MASTER_SHEET)
    companies: Dict[str, Dict[str, Any]] = {}
    for row in list(active) + list(history):
        cliente = str(rules.pick_task_value(row, ["CLIENTE"]) or "").strip()
        if not cliente:
            continue
        fecha = rules.parse_sheet_date(rules.pick_task_value(row, ["FECHA INICIO", "FECHA", "ALTA", "FECHA ALTA"]))
        if not fecha or fecha.month != target_month or fecha.year != target_year:
            continue
        entry = companies.setdefault(cliente.upper(), {"name": cliente.upper(), "count": 0})
        entry["count"] += 1

    return {"success": True, "data": sorted(companies.values(), key=lambda c: c["name"])}


def fetch_unified_agenda(username: str = "") -> Dict[str, Any]:
    """
    Equivalente de `apiFetchUnifiedAgenda`: tareas de trabajo del tracker del
    usuario, eventos personales y hábitos, en una sola respuesta.

    Los eventos y los hábitos se filtran por `usuario_raw`, que es la columna
    real de `personal_agenda` y `habits_log`. Antes se filtraba por `USUARIO`,
    que no existe en ninguna de las dos: la condición nunca se cumplía y todo el
    mundo veía la agenda de todo el mundo (27 eventos en total, así que el fallo
    pasaba desapercibido).
    """
    target = username or ""
    work_tasks: List[Dict[str, Any]] = []
    if target:
        active, _history, _headers = read_rows(target)
        work_tasks = [t for t in active if str(t.get("CLIENTE", "")).upper() != "PERSONAL"]
        if not work_tasks and not rules.is_sales_sheet(target):
            active, _history, _headers = read_rows(f"{target} (VENTAS)")
            work_tasks = list(active)

    quien = rules.normalize_staff_name(username)

    def es_del_usuario(fila: Dict[str, Any]) -> bool:
        dueno = rules.pick_task_value(fila, ["USUARIO_RAW", "USUARIO"])
        # Sin dueño la fila es de todos: así estaban las 27 filas migradas.
        return not dueno or rules.normalize_staff_name(dueno) == quien

    personal_active, _h, _hd = read_rows("AGENDA_PERSONAL")
    personal_events = [e for e in personal_active if es_del_usuario(e)]

    habits_active, _h2, _hd2 = read_rows("HABITOS_LOG")
    habits = [h for h in habits_active if es_del_usuario(h)]

    return {"success": True, "workTasks": work_tasks, "personalEvents": personal_events, "habits": habits}


def log_date_change(payload: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    """
    Auditoría de cambios de fecha en la tabla de ventas.

    Escribía en una hoja `LOG_SISTEMA` que no existe en el esquema relacional
    (la tabla se llama `system_log`), así que cada cambio de fecha se perdía sin
    ruido. Ahora va donde están los otros 16.196 eventos.
    """
    from backend.services import auditoria

    detail = (f"Hoja: {payload.get('hoja', '-')} | Folio: {payload.get('folio', '-')} | "
              f"Campo: {payload.get('campo', '-')} | {payload.get('anterior') or '(vacío)'} -> "
              f"{payload.get('nuevo') or '(vacío)'}")
    registrado = auditoria.registrar(username, auditoria.ACCION_CAMBIO_FECHA, detail)
    return {"success": True, "logged": registrado}


# ----------------------------------------------------------------------
# PROYECTOS / CASCADA
# ----------------------------------------------------------------------
# Las tareas de un proyecto no viven en una tabla aparte: son filas de
# `ADMINISTRADOR` etiquetadas con `[PROY: NOMBRE]` en CONCEPTO o COMENTARIOS.
# Se conserva esa convención porque es la que el frontend escribe y lee, y
# porque `tasks` no tiene una columna con la que relacionarlas.
#
# Lo correcto a futuro es una clave foránea real (`tasks.project_id` ->
# `projects.id_proyecto`), que además haría innecesario buscar por subcadena.
# Requiere DDL, así que queda para cuando el esquema esté versionado; mientras,
# esto funciona con el esquema que hay.

PROJECT_TASKS_SHEET = "ADMINISTRADOR"


def project_tag(project_name: Any) -> str:
    return f"[PROY: {str(project_name or '').upper().strip()}]"


def fetch_project_tasks(project_name: str) -> Dict[str, Any]:
    """
    Equivalente de `apiFetchProjectTasks`.

    **Corrige un fallo del original, no lo replica.** `CODIGO.js:3907` cierra la
    función con `if (sheetName.includes('ANTONIA_VENTAS'))`, y `sheetName` no
    existe en ese ámbito: el parámetro se llama `projectName`. El
    `ReferenceError` cae siempre en el `catch`, así que la función devolvía
    `{success:false}` en el 100% de las llamadas y la vista PROJECT_TASKS_VIEW
    nunca mostró nada.

    Ese bloque era además copia de `internalFetchSheetData` y no tenía sentido
    aquí: esta función lee `ADMINISTRADOR`, nunca `ANTONIA_VENTAS`, así que el
    reordenamiento de `MAP COT` no aplicaba. Se omite en vez de arreglarlo.
    """
    etiqueta = project_tag(project_name)
    if etiqueta == "[PROY: ]":
        return {"success": False, "message": "Falta el nombre del proyecto."}

    active, history, headers = read_rows(PROJECT_TASKS_SHEET)
    if not headers:
        return {"success": False,
                "message": f"No se pudo leer {PROJECT_TASKS_SHEET} o no tiene encabezados."}

    def etiquetada(row: Dict[str, Any]) -> bool:
        # El original mira CONCEPTO y COMENTARIOS, con respaldo a cualquier
        # encabezado que contenga "DESCRIPCI" cuando no hay CONCEPTO.
        campos = [
            rules.pick_task_value(row, ["CONCEPTO", "DESCRIPCION", "DESCRIPCIÓN"]),
            rules.pick_task_value(row, ["COMENTARIOS"]),
        ]
        return any(etiqueta in str(v or "").upper() for v in campos)

    tareas = [r for r in list(active) + list(history) if etiquetada(r)]
    # `.reverse()` del original: lo más reciente primero.
    tareas.reverse()
    return {"success": True, "data": tareas, "headers": headers}


def save_project_task(task: Dict[str, Any], project_name: str,
                      username: str = "") -> Dict[str, Any]:
    """
    Equivalente de `apiSaveProjectTask`.

    Añade la etiqueta del proyecto a COMENTARIOS si falta y guarda por la misma
    ruta que el resto del tracker, con lo que hereda Gatekeeper, resolución de
    folio y auditoría.
    """
    etiqueta = project_tag(project_name)
    if etiqueta == "[PROY: ]":
        return {"success": False, "message": "Falta el nombre del proyecto."}

    fila = dict(task)
    # La columna puede venir con otro nombre según la hoja; se respeta el que
    # traiga la fila para no crear una columna duplicada al guardar.
    clave = next((k for k in fila if str(k).upper().strip() == "COMENTARIOS"), "COMENTARIOS")
    comentarios = str(fila.get(clave) or "")
    if etiqueta not in comentarios.upper():
        fila[clave] = f"{comentarios} {etiqueta}".strip()

    return update_task(PROJECT_TASKS_SHEET, fila, username)


# ----------------------------------------------------------------------
# BANCO DE INFORMACIÓN, PPC MAESTRO Y CALENDARIO
# ----------------------------------------------------------------------

# Hoja maestra del PPC. Se importa de `sheets` para no repetir el literal, que
# es el anti-patrón §23.5 (nombres de tabla como cadenas dispersas).
from api.services.sheets import PPC_MASTER_SHEET  # noqa: E402

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
         "DICIEMBRE": 12}


def _mes_numero(mes: Any) -> Optional[int]:
    numero = MESES.get(str(mes).upper().strip())
    if numero is not None:
        return numero
    try:
        valor = int(mes)
    except (TypeError, ValueError):
        return None
    return valor if 1 <= valor <= 12 else None


def fetch_info_bank_data(year: Any, month: Any, company: Any = "",
                         folder: Any = "") -> Dict[str, Any]:
    """
    Equivalente de `apiFetchInfoBankData`: cotizaciones de un cliente en un mes.

    El original compara el cliente con inclusión **bidireccional**
    (`rowClient.includes(target) || target.includes(rowClient)`) para tolerar que
    en la hoja el nombre esté abreviado o con sufijos. Se conserva: exigir
    igualdad dejaría fuera la mayoría de las filas reales.

    `folder` lo manda el frontend y el original tampoco lo usa para filtrar;
    se acepta y se ignora para no cambiar la firma.
    """
    mes = _mes_numero(month)
    if mes is None:
        return {"success": False, "message": f"Mes inválido: {month}"}
    try:
        anio = int(year)
    except (TypeError, ValueError):
        anio = datetime.now().year

    objetivo = str(company or "").upper().strip()
    active, history, headers = read_rows(rules.SALES_MASTER_SHEET)

    filas = []
    for row in list(active) + list(history):
        cliente = str(rules.pick_task_value(row, ["CLIENTE"]) or "").upper().strip()
        if not cliente:
            continue
        if objetivo and not (objetivo in cliente or cliente in objetivo):
            continue
        fecha = rules.parse_sheet_date(
            rules.pick_task_value(row, ["FECHA INICIO", "F. INICIO", "FECHA", "ALTA", "FECHA ALTA"]))
        if not fecha or fecha.month != mes or fecha.year != anio:
            continue
        filas.append(row)

    return {"success": True, "data": filas, "headers": headers}


def fetch_ppc_data() -> Dict[str, Any]:
    """
    Equivalente de `apiFetchPPCData`: las actividades del PPC maestro.

    Dos detalles del original que se conservan porque el frontend depende de
    ellos: se devuelven **las últimas 300** filas (con 1.180 en `plan_semanal`,
    mandarlas todas hacía lenta la vista) y en orden inverso.
    """
    active, history, _headers = read_rows(PPC_MASTER_SHEET)
    filas = list(active) + list(history)

    salida = []
    for row in filas:
        concepto = rules.pick_task_value(row, ["CONCEPTO", "DESCRIPCION", "DESCRIPCIÓN"])
        if not str(concepto or "").strip():
            continue
        salida.append({
            "id": rules.pick_task_value(row, ["ID", "FOLIO"]) or "",
            "especialidad": rules.pick_task_value(row, ["ESPECIALIDAD"]) or "",
            "concepto": concepto,
            "responsable": rules.pick_task_value(row, ["RESPONSABLE", "INVOLUCRADOS"]) or "",
            "fechaAlta": rules.pick_task_value(row, ["FECHA", "FECHA ALTA", "ALTA"]) or "",
            "horas": rules.pick_task_value(row, ["RELOJ", "HORAS"]) or "",
            "cumplimiento": rules.pick_task_value(row, ["CUMPLIMIENTO"]) or "",
            "archivoUrl": rules.pick_task_value(row, ["ARCHIVO", "CLIP"]) or "",
            "comentarios": rules.pick_task_value(row, ["COMENTARIOS"]) or "",
            "comentariosPrevios": rules.pick_task_value(
                row, ["COMENTARIOS PREVIOS", "PREVIOS", "COMENTARIOS_PREVIOS"]) or "",
        })

    salida = salida[-300:]
    salida.reverse()
    return {"success": True, "data": salida}


def fetch_combined_calendar(sheet_name: str) -> Dict[str, Any]:
    """
    Equivalente de `apiFetchCombinedCalendarData`.

    Une el tracker de la persona, su hoja `(VENTAS)` si la tiene, y sus eventos
    personales marcados como `CLIENTE = PERSONAL`. Deduplica por ID/FOLIO y, a
    falta de ambos, por CONCEPTO+FECHA — la misma cadena de identidad que usa el
    Gatekeeper al guardar.
    """
    base = rules.SALES_SUFFIX_RE.sub("", str(sheet_name or "")).strip()
    if not base:
        return {"success": False, "message": "Falta la hoja a consultar."}

    # Toñita distribuye desde la tabla maestra: no se le suma una hoja (VENTAS).
    if base.upper() == "ANTONIA_VENTAS":
        objetivos = ["ANTONIA_VENTAS"]
    else:
        objetivos = [base, f"{base} (VENTAS)"]

    filas: List[Dict[str, Any]] = []
    for objetivo in objetivos:
        active, _history, _headers = read_rows(objetivo)
        filas.extend(active)

    quien = rules.normalize_staff_name(base)
    personales, _h, _hd = read_rows("AGENDA_PERSONAL")
    for evento in personales:
        dueno = rules.pick_task_value(evento, ["USUARIO_RAW", "USUARIO"])
        if rules.normalize_staff_name(dueno) != quien:
            continue
        copia = dict(evento)
        # El frontend pinta el calendario por CONCEPTO y distingue lo personal
        # por CLIENTE: así lo hacía el original.
        copia["CONCEPTO"] = rules.pick_task_value(evento, ["TITULO"]) or copia.get("CONCEPTO", "")
        copia["CLIENTE"] = "PERSONAL"
        filas.append(copia)

    unicas: Dict[str, Dict[str, Any]] = {}
    for fila in filas:
        clave = str(rules.pick_task_value(fila, ["ID", "FOLIO"]) or "").strip()
        if not clave:
            concepto = str(rules.pick_task_value(fila, ["CONCEPTO"]) or "").strip()
            fecha = str(rules.pick_task_value(fila, ["FECHA"]) or "").strip()
            clave = f"{concepto}{fecha}" if concepto else ""
        if clave:
            unicas[clave] = fila

    return {"success": True, "data": list(unicas.values())}


def logout(username: str = "") -> Dict[str, Any]:
    """
    Equivalente de `apiLogout`: cierra sesión dejando la línea de auditoría.

    No hay sesión que invalidar todavía (la autenticación con JWT es Fase 4 del
    plan), pero el registro sí importa: `system_log` guarda 16.196 entradas
    históricas de accesos y sin esto la mitad del par LOGIN/LOGOUT se perdía.
    """
    try:
        from backend.services import auditoria

        auditoria.registrar(str(username or "DESCONOCIDO").upper().strip(),
                            "LOGOUT", "Sesión cerrada")
    except Exception as exc:  # noqa: BLE001 - auditar no puede impedir el cierre
        print(f"[logout] No se pudo auditar: {exc}")
    return {"success": True}


# ----------------------------------------------------------------------
# BORRADORES, AGENDA Y DIRECTORIO
# ----------------------------------------------------------------------
# Delegan en `backend/repositories/agenda.py`, que es quien conoce las tablas.
# Aquí solo se traduce a la envoltura `{success, ...}` que espera el frontend.


def _repo(clase):
    from backend.core.engine import construir_engine

    return clase(construir_engine())


def _envolver(accion, exito: Dict[str, Any]) -> Dict[str, Any]:
    """Ejecuta y traduce cualquier fallo a un mensaje visible, nunca a un vacío."""
    from backend.repositories.agenda import TablaAusente

    try:
        resultado = accion()
    except TablaAusente as exc:
        return {"success": False, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"{type(exc).__name__}: {exc}"}
    salida = dict(exito)
    if resultado is not None:
        salida["data"] = resultado
    return salida


def fetch_drafts() -> Dict[str, Any]:
    """apiFetchDrafts."""
    from backend.repositories.agenda import RepositorioBorradores

    return _envolver(lambda: _repo(RepositorioBorradores).listar(), {"success": True})


def sync_drafts(drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """apiSyncDrafts: reemplaza la cola completa."""
    from backend.repositories.agenda import RepositorioBorradores

    repo = _repo(RepositorioBorradores)
    res = _envolver(lambda: repo.reemplazar(drafts or []), {"success": True})
    if res.get("success"):
        # `data` sería el conteo; el frontend solo mira `success`.
        res["message"] = f"{res.pop('data', 0)} borrador(es) sincronizado(s)."
    return res


def clear_drafts() -> Dict[str, Any]:
    """apiClearDrafts."""
    from backend.repositories.agenda import RepositorioBorradores

    repo = _repo(RepositorioBorradores)
    return _envolver(lambda: repo.limpiar(), {"success": True})


def save_personal_event(event: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    """apiSavePersonalEvent."""
    from backend.repositories.agenda import RepositorioAgenda

    repo = _repo(RepositorioAgenda)
    return _envolver(lambda: repo.guardar_evento(event, username), {"success": True})


def save_habit_log(habit: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    """apiSaveHabitLog. Falla con instrucciones si `habits_log` no existe."""
    from backend.repositories.agenda import RepositorioAgenda

    repo = _repo(RepositorioAgenda)
    return _envolver(lambda: repo.guardar_habito(habit, username), {"success": True})


def add_employee(name: Any, dept: Any, tipo: Any = "ESTANDAR") -> Dict[str, Any]:
    """
    apiAddEmployee: alta en el directorio (`people`).

    El original valida duplicados por (nombre, departamento) y crea las hojas de
    tracker según `type`. Aquí no hay hojas que crear: una persona nueva empieza
    sin filas en `tasks` y su tracker aparece vacío en cuanto está en `people`.
    """
    from api.services.sheets import get_directory_from_db

    limpio = str(name or "").upper().strip()
    depto = str(dept or "").upper().strip()
    if not limpio or not depto:
        return {"success": False, "message": "Nombre y departamento son obligatorios."}

    existentes = {(u["name"].upper().strip(), u["dept"].upper().strip())
                  for u in get_directory_from_db()}
    if (limpio, depto) in existentes:
        return {"success": False, "message": f"{limpio} ya está en {depto}."}

    fila = _manager().append_row("DB_DIRECTORY", [limpio, depto, str(tipo or "ESTANDAR").upper()])
    if fila is None:
        return {"success": False,
                "message": "No se pudo escribir en el directorio. El alta NO se guardó."}
    return {"success": True, "message": f"{limpio} agregado a {depto}."}


def delete_employee(name: Any) -> Dict[str, Any]:
    """
    apiDeleteEmployee: baja del directorio.

    Se borra por nombre, que es la clave lógica de `people` igual que en la hoja
    `DB_DIRECTORY`. Las tareas de la persona **no** se tocan: son historia y
    borrarlas sería pérdida de datos que el original tampoco hace.
    """
    from backend.core.engine import construir_engine

    limpio = str(name or "").upper().strip()
    if not limpio:
        return {"success": False, "message": "Falta el nombre a dar de baja."}

    try:
        engine = construir_engine()
        filas = engine.select("people", columnas=["nombre"]) or []
        objetivo = next((f["nombre"] for f in filas
                         if str(f.get("nombre") or "").upper().strip() == limpio), None)
        if objetivo is None:
            return {"success": False, "message": f"{limpio} no está en el directorio."}
        engine.borrar("people", {"nombre": objetivo})
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"No se pudo dar de baja: {exc}"}

    return {"success": True, "message": f"{limpio} dado de baja."}


# ----------------------------------------------------------------------
# AGENTE DE PRODUCTIVIDAD Y CORREO
# ----------------------------------------------------------------------

MESES_NOMBRE = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def fetch_tracker_productivity_metrics(month: Optional[int] = None,
                                       year: Optional[int] = None) -> Dict[str, Any]:
    """
    Equivalente de `apiFetchTrackerProductivityMetrics`.

    Recorre el directorio y toma las tareas **cerradas** de cada persona en el
    periodo. Las cerradas son las que el auto-archivado deja en el historial, que
    es lo que el original leía por debajo del separador "TAREAS REALIZADAS".
    """
    from api.services.sheets import get_directory_from_db

    mes = month or datetime.now().month
    anio = year or datetime.now().year

    departamentos: Dict[str, str] = {}
    por_persona: Dict[str, List[Dict[str, Any]]] = {}

    for entrada in get_directory_from_db():
        persona = entrada.get("name")
        if not persona or persona in por_persona:
            continue
        departamentos[persona] = entrada.get("dept") or ""
        _active, history, _headers = read_rows(persona)
        del_periodo = []
        for row in history:
            fecha = rules.parse_sheet_date(
                rules.pick_task_value(row, ["FECHA", "FECHA ALTA", "ALTA"]))
            if fecha and fecha.month == mes and fecha.year == anio:
                del_periodo.append(row)
        if del_periodo:
            por_persona[persona] = del_periodo

    metrics = rules.compute_productivity_metrics(
        por_persona, departamento_de=departamentos.get, month=mes, year=anio)
    return {"success": True, "metrics": metrics}


def run_tracker_productivity_agent(month: Optional[int] = None,
                                   year: Optional[int] = None) -> Dict[str, Any]:
    """
    Equivalente de `runTrackerProductivityAgent`: métricas + 3 reglas + resumen
    de IA + correo.

    Los destinatarios se resuelven **por rol** (ADMIN, ADMIN_CONTROL, PPC_ADMIN).
    El original los buscaba por nombre de cuenta y una de las tres llaves
    —`USER_DB['ADMIN_CONTROL']`— no existe, porque es un rol: el reporte nunca
    llegó a JAIME_OLIVO ni a DIMAS_RAMOS. Ver `api/services/correo.py`.
    """
    from api.services import correo

    mes = month or datetime.now().month
    anio = year or datetime.now().year
    nombre_mes = MESES_NOMBRE[mes - 1]

    resultado = fetch_tracker_productivity_metrics(mes, anio)
    if not resultado.get("success"):
        return {"success": False,
                "message": f"No se pudieron obtener métricas: {resultado.get('message')}"}

    metrics = resultado["metrics"]
    alertas = rules.productivity_alerts(metrics)

    resumen = "No se pudo generar reporte con IA."
    respuesta = call_gemini(rules.build_productivity_prompt(metrics, nombre_mes))
    if respuesta.get("success") and respuesta.get("text"):
        resumen = respuesta["text"]

    filas = "".join(
        f'<tr style="border-bottom:1px solid #eee;"><td style="padding:5px 10px;">{c["name"]}</td>'
        f'<td style="text-align:center;padding:5px 10px;">{c["count"]}</td>'
        f'<td style="text-align:center;padding:5px 10px;color:'
        f'{"#28a745" if c["onTimePct"] >= 80 else "#dc3545"};">{c["onTimePct"]}%</td>'
        f'<td style="text-align:center;padding:5px 10px;">{c["avgDays"]}</td></tr>'
        for c in metrics["byCollabArr"][:8]
    )
    tabla = (
        '<h2 style="font-size:16px;color:#444;margin-top:24px;">Por colaborador</h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<tr style="background:#f1f3f5;"><th style="padding:6px 10px;text-align:left;">Nombre</th>'
        '<th>Tareas</th><th>A tiempo</th><th>Días prom.</th></tr>'
        f'{filas}</table>'
    ) if filas else ""

    envio = correo.enviar(
        asunto=f"Reporte de Productividad — {nombre_mes} {anio}",
        html=correo.cuerpo_reporte(
            titulo=f"📊 Reporte de Productividad — {nombre_mes} {anio}",
            subtitulo="Generado automáticamente por el Agente de Productividad",
            resumen_ia=resumen,
            kpis=[("Total Completadas", metrics["totalTasks"]),
                  ("A Tiempo", f"{metrics['onTimePct']}%"),
                  ("Atrasadas", metrics["lateTasks"]),
                  ("Días Promedio", metrics["avgDurationDays"])],
            alertas=alertas,
            tabla_html=tabla,
        ),
        roles=["ADMIN", "ADMIN_CONTROL", "PPC_ADMIN"],
    )

    return {
        "success": True,
        "data": {
            "metrics": metrics,
            "alerts": alertas,
            "geminiReport": resumen,
            "emailSent": bool(envio.get("success")),
            "emailMessage": envio.get("message", ""),
        },
    }


def send_quote_metrics_email(month: Optional[int] = None,
                             year: Optional[int] = None) -> Dict[str, Any]:
    """
    Equivalente de `_sendAgentEmail`: el reporte de cotizaciones por correo.

    Destinatarios por rol TONITA y ADMIN, que son las dos cuentas que el
    original nombraba (`ANTONIA_VENTAS` y `LUIS_CARLOS`).
    """
    from api.services import correo

    mes = month or datetime.now().month
    anio = year or datetime.now().year
    nombre_mes = MESES_NOMBRE[mes - 1]

    reporte = run_quote_metrics_agent(mes, anio)
    if not reporte.get("success"):
        return reporte

    datos = reporte.get("data") or {}
    metrics = datos.get("metrics") or {}
    envio = correo.enviar(
        asunto=f"Reporte de Cotizaciones — {nombre_mes} {anio}",
        html=correo.cuerpo_reporte(
            titulo=f"📊 Reporte de Cotizaciones — {nombre_mes} {anio}",
            subtitulo="Generado automáticamente por el Agente de Métricas",
            resumen_ia=datos.get("geminiReport", ""),
            kpis=[("Cotizaciones", metrics.get("total", 0)),
                  ("Ganadas", metrics.get("ganadas", metrics.get("won", 0))),
                  ("SLA en tiempo", metrics.get("slaOk", 0))],
            alertas=datos.get("alerts") or [],
            color="#1E3A5F",
        ),
        roles=["TONITA", "ADMIN"],
    )
    datos["emailSent"] = bool(envio.get("success"))
    datos["emailMessage"] = envio.get("message", "")
    return {"success": True, "data": datos}


def auto_update_quote_metrics() -> Dict[str, Any]:
    """
    Equivalente de `autoUpdateQuoteMetrics`, el disparador diario de las 07:00.

    En Apps Script era un trigger de tiempo instalado con
    `setupDailyQuoteMetricsTrigger`. Aquí no hay proceso residente —en serverless
    no existe—, así que lo dispara un cron externo contra
    `POST /api/cron/dailyMetrics`. Ver `.github/workflows/cron-metricas.yml`.
    """
    cotizaciones = write_quote_metrics_to_sheet()
    correo_cotizaciones = send_quote_metrics_email()
    productividad = run_tracker_productivity_agent()

    return {
        "success": True,
        "data": {
            "kpiEscritos": bool(cotizaciones.get("success")),
            "correoCotizaciones": bool((correo_cotizaciones.get("data") or {}).get("emailSent")),
            "correoProductividad": bool((productividad.get("data") or {}).get("emailSent")),
        },
    }
