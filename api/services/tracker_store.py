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
from typing import Any, Dict, List, Optional

from api.services import tracker_rules as rules

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
                   username: str = "", persistencia=None) -> rules.BatchResult:
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

    guardado = persistencia.guardar(sheet_name, result.data)
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

    processed: List[Dict[str, Any]] = []
    for raw_task in tasks:
        task = dict(raw_task)
        if is_antonia:
            folio = rules.pick_task_value(task, ["FOLIO", "ID"])
            master = find_row_object(target, folio) if folio else None
            hot = rules.apply_hot_potato(target, task, master, username)
            if hot:
                # Distribución lateral: cada trabajador recibe la fila en SU
                # hoja, es decir, en su propia partición `source_sheet`.
                for worker, row in zip(hot["workers"], hot["rows"]):
                    worker_sheet = resolve_worker_sheet(worker)
                    if worker_sheet:
                        _persist_batch(worker_sheet, [row], username=username,
                                       persistencia=persistencia)
        processed.append(task)

    result = _persist_batch(target, processed, username=username,
                            persistencia=persistencia)
    if not result.success:
        return {"success": False, "message": result.message}

    # Reverse Sync: tabla (VENTAS) de un vendedor -> maestra de Toñita
    if not is_antonia and "(VENTAS)" in target.upper():
        for task in processed:
            folio = rules.pick_task_value(task, ["FOLIO", "ID"])
            if not folio:
                continue
            payload = rules.build_reverse_sync_payload(
                target, task,
                find_row_object(target, folio),
                find_row_object(rules.SALES_MASTER_SHEET, folio),
            )
            if payload:
                _persist_batch(rules.SALES_MASTER_SHEET, [payload], skip_notify=True,
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
