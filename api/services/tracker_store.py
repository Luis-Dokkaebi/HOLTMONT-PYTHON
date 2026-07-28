"""
======================================================================
ORQUESTADOR DEL TRACKER — capa de persistencia sobre tracker_rules
======================================================================
Aplica las reglas de negocio (idénticas a las de CODIGO.js) sobre los
datos reales y los persiste con `gs_manager`. Los imports de la capa de
datos son perezosos a propósito: `tracker_rules` debe poder probarse sin
credenciales de Supabase.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
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


def write_values(sheet_name: str, values: List[List[Any]]) -> bool:
    try:
        return bool(_manager().write_values(sheet_name, values))
    except Exception as exc:  # pragma: no cover
        print(f"[tracker_store] No se pudo escribir {sheet_name}: {exc}")
        return False


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

def _persist_batch(sheet_name: str, tasks: List[Dict[str, Any]], skip_notify: bool = False) -> rules.BatchResult:
    values = read_values(sheet_name)
    result = rules.apply_batch_update(values, tasks, sheet_name, skip_notify=skip_notify)
    if result.success:
        write_values(sheet_name, result.values)
        for payload in result.notifications:
            send_to_outlook(payload)
    return result


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

    processed: List[Dict[str, Any]] = []
    for raw_task in tasks:
        task = dict(raw_task)
        if is_antonia:
            folio = rules.pick_task_value(task, ["FOLIO", "ID"])
            master = find_row_object(target, folio) if folio else None
            hot = rules.apply_hot_potato(target, task, master, username)
            if hot:
                for worker, row in zip(hot["workers"], hot["rows"]):
                    worker_sheet = resolve_worker_sheet(worker)
                    if worker_sheet:
                        _persist_batch(worker_sheet, [row])
        processed.append(task)

    result = _persist_batch(target, processed)
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
                _persist_batch(rules.SALES_MASTER_SHEET, [payload], skip_notify=True)

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
    result = _persist_batch(sheet, [dict(task)], skip_notify=True)
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

    Reconstruir PPCV3 es entonces una decisión de negocio con tres respuestas
    posibles y resultados muy distintos (1.701 filas, 1.056 o 1.180 casi
    vacías). Mientras no se tome, esta función deja de fingir: marca la
    respuesta con `_notImplemented`, igual que las lecturas no portadas.
    """
    sheet = "PPCV4" if rules.normalize_staff_name(username) == "ANTONIA VENTAS" else "PPCV3"
    active, history, headers = read_rows(sheet)
    respuesta: Dict[str, Any] = {
        "success": True,
        "data": active,
        "history": history,
        "headers": headers,
    }
    if not active and not history and not headers:
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
    """Vuelca los KPIs a la hoja/tabla KPI_COTIZACIONES."""
    metrics = fetch_quote_metrics(month, year)["metrics"]
    rows: List[List[Any]] = [
        ["KPI COTIZACIONES", "PERIODO", f"{metrics['month']}/{metrics['year']}", "GENERADO", rules.to_iso_z(datetime.utcnow())],
        [],
        ["INDICADOR", "VALOR"],
        ["Cotizaciones totales", metrics["totalCount"]],
        ["Ganadas", metrics["winLoss"]["ganada"]],
        ["Perdidas", metrics["winLoss"]["perdida"]],
        ["En proceso", metrics["winLoss"]["enProceso"]],
        ["Tasa de cierre (%)", metrics["closeRate"]],
        [],
        ["CLASE", "SLA (días)", "TOTAL", "EN TIEMPO", "FUERA DE SLA", "PROMEDIO DÍAS", "% CUMPLIMIENTO"],
    ]
    for clase in ("A", "AA", "AAA"):
        s = metrics["slaSummary"][clase]
        rows.append([clase, s["slaLimit"], s["count"], s["ok"], s["fail"], s["avgDays"], s["pctOk"]])
    rows.append([])
    rows.append(["COTIZADOR", "TOTAL", "GANADAS", "PERDIDAS", "EN PROCESO"])
    for v in metrics["byCotizadorArr"]:
        rows.append([v["nombre"], v["total"], v["ganada"], v["perdida"], v["enProceso"]])

    width = max(len(r) for r in rows)
    normalized = [r + [""] * (width - len(r)) for r in rows]
    ok = write_values("KPI_COTIZACIONES", normalized)
    return {"success": ok, "message": "KPI_COTIZACIONES actualizado" if ok else "No se pudo escribir la hoja de KPIs"}


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
    """
    target = username or ""
    work_tasks: List[Dict[str, Any]] = []
    if target:
        active, _history, _headers = read_rows(target)
        work_tasks = [t for t in active if str(t.get("CLIENTE", "")).upper() != "PERSONAL"]
        if not work_tasks and not rules.is_sales_sheet(target):
            active, _history, _headers = read_rows(f"{target} (VENTAS)")
            work_tasks = list(active)

    personal_active, _h, _hd = read_rows("AGENDA_PERSONAL")
    personal_events = [e for e in personal_active
                       if not e.get("USUARIO") or str(e["USUARIO"]).upper() == str(username).upper()]

    habits_active, _h2, _hd2 = read_rows("HABITOS_LOG")
    habits = [h for h in habits_active
              if not h.get("USUARIO") or str(h["USUARIO"]).upper() == str(username).upper()]

    return {"success": True, "workTasks": work_tasks, "personalEvents": personal_events, "habits": habits}


def log_date_change(payload: Dict[str, Any], username: str = "") -> Dict[str, Any]:
    """Auditoría de cambios de fecha en la tabla de ventas."""
    detail = (f"Hoja: {payload.get('hoja', '-')} | Folio: {payload.get('folio', '-')} | "
              f"Campo: {payload.get('campo', '-')} | {payload.get('anterior') or '(vacío)'} -> "
              f"{payload.get('nuevo') or '(vacío)'}")
    try:
        _manager().append_row("LOG_SISTEMA", [rules.to_iso_z(datetime.utcnow()), username or "DESCONOCIDO",
                                              "CAMBIO_FECHA", detail])
    except Exception as exc:  # pragma: no cover
        print(f"[tracker_store] No se pudo registrar el cambio de fecha: {exc}")
    return {"success": True}
