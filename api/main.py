from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, File, Form

# AI Utils
try:
    from api.ai_utils import transcribir_audio, extraer_informacion
    from api.engineering_agent import process_audio
except ImportError:
    import sys
    sys.path.append("api")
    from ai_utils import transcribir_audio, extraer_informacion
    from engineering_agent import process_audio

# Services
from api.services.sheets import gs_manager, get_directory_from_db, find_header_row, ALL_DEPTS, INITIAL_DIRECTORY
from api.services import organigrama
from api.services.work_order import process_and_save_work_order, get_next_sequence

# MCP Server
from api.mcp_server import mcp

# Load environment variables from .env file manually
def load_env_file(filepath=".env"):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()

if os.path.exists(".env"):
    load_env_file(".env")
elif os.path.exists("../.env"):
    load_env_file("../.env")

app = FastAPI(title="Holtmont Workspace Backend")

# CORS Configuration
#
# `allow_origins=["*"]` junto con `allow_credentials=True` es una combinación
# que los navegadores rechazan y que, de aplicarse, dejaría la API abierta a
# cualquier origen. Los orígenes permitidos se declaran por entorno
# (CORS_ORIGINS, separados por coma); sin ellos no se permiten credenciales.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=bool(_cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP Server SSE App
try:
    app.mount("/mcp", mcp.sse_app)
except Exception as e:
    print(f"Error mounting MCP server: {e}")

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def home():
    path = os.path.join(os.path.dirname(__file__), "../index.html")
    with open(path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/api_service.js")
async def serve_api_service():
    path = os.path.join(os.path.dirname(__file__), "../api_service.js")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="File not found")

from api.paperclip_agents import run_paperclip_agency

class PaperclipRequest(BaseModel):
    text: str

@app.post("/api/run_paperclip_agency")
async def api_run_paperclip_agency(req: PaperclipRequest):
    try:
        result = run_paperclip_agency(user_request=req.text)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Error desconocido en Paperclip Agency"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LoginRequest(BaseModel):
    username: str
    password: str

class SavePPCRequest(BaseModel):
    payload: List[Dict[str, Any]]
    activeUser: str

@app.get("/api/config")
def api_get_system_config(
    role: str = Query(..., description="Rol del usuario"),
    username: str = Query("", description="Cuenta activa: habilita las ramas por usuario"),
):
    """
    Port de `getSystemConfig(role, username)`.

    `username` es opcional en la firma pero necesario en la práctica: sin él no
    se pueden resolver las ramas que el original cablea por cuenta (JUANY,
    JESUS_CANTU) ni el tracker propio de un STAFF_USER. Se deja con valor por
    defecto para no romper a un cliente viejo que solo mande `role`; en ese caso
    el comportamiento degrada a "sin rama por usuario", nunca a permisos de más.
    """
    full_directory = get_directory_from_db()
    cuenta = organigrama.clave_usuario(username)

    ppc_module_master = { "id": "PPC_MASTER", "label": "PPC Maestro", "icon": "fa-tasks", "color": "#fd7e14", "type": "ppc_native" }
    # JESUS_CANTU ve el módulo PPC con otro nombre. Es una etiqueta, no un
    # permiso, y por eso se resuelve aquí y no en la rama de rol.
    if cuenta == "JESUS_CANTU":
        ppc_module_master = { **ppc_module_master, "label": "INTERDICIPLINARIA" }

    ppc_module_weekly = { "id": "WEEKLY_PLAN", "label": "Planeación Semanal", "icon": "fa-calendar-alt", "color": "#6f42c1", "type": "weekly_plan_view" }
    kpi_module = { "id": "KPI_DASHBOARD", "label": "KPI Performance", "icon": "fa-chart-line", "color": "#d63384", "type": "kpi_dashboard_view" }
    wo_module = { "id": "WORK_ORDER_FORM", "label": "Pre Work Order", "icon": "fa-clipboard-list", "color": "#fd7e14", "type": "work_order_form" }
    ppc_modules = [ ppc_module_master, ppc_module_weekly ]

    if role == 'TONITA':
        return {
            "departments": { "VENTAS": ALL_DEPTS["VENTAS"] },
            "allDepartments": ALL_DEPTS,
            "staff": [ { "name": "ANTONIA_VENTAS", "dept": "VENTAS" } ],
            "directory": full_directory,
            "specialModules": [
                # Su tracker personal es una hoja distinta de la tabla maestra
                # de ventas: `ANTONIA PINEDA LOPEZ` vs `ANTONIA_VENTAS`. Faltaba
                # y con él faltaba el acceso a sus propias tareas.
                { "id": "MY_TRACKER", "label": "Tracker", "icon": "fa-table",
                  "color": ALL_DEPTS.get("PRESUPUESTOS", {}).get("color", "#6f42c1"),
                  "type": "mirror_staff", "target": "ANTONIA PINEDA LOPEZ" },
                ppc_module_master,
                ppc_module_weekly,
            ],
            "accessProjects": False,
            "canSeeBancoJuntas": False,
        }

    # Rama por cuenta: JUANY_RODRIGUEZ es STAFF_USER pero con vista ampliada a
    # tres departamentos. Va ANTES de la rama de rol, igual que en el original.
    if cuenta == "JUANY_RODRIGUEZ":
        claves = ["COMPRAS", "FACTURACION", "FINANZAS"]
        return {
            "departments": { k: ALL_DEPTS[k] for k in claves if k in ALL_DEPTS },
            "allDepartments": ALL_DEPTS,
            "staff": [ d for d in full_directory if d.get("dept") in claves ],
            "directory": full_directory,
            "specialModules": ppc_modules,
            "accessProjects": False,
            "canSeeBancoJuntas": False,
        }

    if role == 'STAFF_USER':
        # Esta rama no existía. Sin ella, los 30+ usuarios de personal caían al
        # `return` final —la configuración de ADMIN— y recibían los 19
        # departamentos, el directorio completo y accessProjects=True.
        perfil = organigrama.perfil(cuenta)
        hoja = organigrama.nombre_de_hoja(cuenta)
        color = ALL_DEPTS.get(perfil.get("dept", ""), {}).get("color", "#0d6efd")
        modulos = [
            { "id": "MY_TRACKER", "label": "Tracker", "icon": "fa-table", "color": color,
              "type": "mirror_staff", "target": hoja },
            { "id": "PPC_MASTER", "label": "Agregar Actividad", "icon": "fa-tasks",
              "color": "#fd7e14", "type": "ppc_native" },
        ]
        if perfil.get("seller"):
            modulos.append({ "id": "MY_SALES", "label": "Cotizaciones", "icon": "fa-hand-holding-usd",
                             "color": "#0dcaf0", "type": "mirror_staff", "target": f"{hoja} (VENTAS)" })
        return {
            "departments": {},
            "allDepartments": ALL_DEPTS,
            "staff": [ { "name": hoja, "dept": perfil.get("dept", "") } ],
            "directory": full_directory,
            "specialModules": modulos,
            "accessProjects": False,
            "canSeeBancoJuntas": False,
        }

    if role == 'WORKORDER_USER':
        return {
            "departments": {},
            "allDepartments": ALL_DEPTS,
            "staff": [],
            "directory": full_directory,
            "specialModules": [ wo_module ],
            "accessProjects": False,
            "canSeeBancoJuntas": False,
        }

    if role == 'PPC_ADMIN':
        return {
            "departments": {},
            "allDepartments": ALL_DEPTS,
            "staff": [],
            "directory": full_directory,
            "specialModules": ppc_modules,
            "accessProjects": True,
            "canSeeBancoJuntas": True,
        }

    if role == 'ADMIN_CONTROL':
        return {
            "departments": ALL_DEPTS,
            "allDepartments": ALL_DEPTS,
            "staff": full_directory,
            "directory": full_directory,
            "specialModules": [
                { "id": "PPC_DINAMICO", "label": "Tracker", "icon": "fa-layer-group", "color": "#e83e8c", "type": "ppc_dynamic_view" },
                *ppc_modules,
                { "id": "MIRROR_TONITA", "label": "Monitor Toñita", "icon": "fa-eye", "color": "#0dcaf0", "type": "mirror_staff", "target": "ANTONIA_VENTAS" },
                { "id": "ADMIN_TRACKER", "label": "Control", "icon": "fa-clipboard-list", "color": "#6f42c1", "type": "mirror_staff", "target": "ADMINISTRADOR" },
            ],
            "accessProjects": True,
            "canSeeBancoJuntas": True,
        }

    # ADMIN y cualquier rol no reconocido. El original también cae aquí, pero
    # ahora todos los roles conocidos tienen rama propia, así que este default
    # solo lo alcanza ADMIN o un rol nuevo sin definir.
    default_modules = [ *ppc_modules,
        { "id": "MIRROR_TONITA", "label": "Monitor Toñita", "icon": "fa-eye", "color": "#0dcaf0", "type": "mirror_staff", "target": "ANTONIA_VENTAS" } ]
    if role == 'ADMIN':
        default_modules.insert(0, wo_module)
        default_modules.append(kpi_module)
        default_modules.append({ "id": "OBSIDIAN_GRAPH", "label": "Grafo de Conocimiento",
                                 "icon": "fa-project-diagram", "color": "#8b5cf6", "type": "obsidian_graph_view" })

    return {
        "departments": ALL_DEPTS,
        "allDepartments": ALL_DEPTS,
        "staff": full_directory,
        "directory": full_directory,
        "specialModules": default_modules,
        "accessProjects": True,
        "canSeeBancoJuntas": True,
    }

@app.get("/api/nextSeq")
def api_get_next_seq():
    seq_str = get_next_sequence('WORKORDER_SEQ', increment=False)
    next_val = int(seq_str) + 1
    return str(next_val).zfill(4)

@app.get("/api/graph_data")
def api_get_graph_data():
    nodes = []
    links = []
    nodes_dict = {}

    def add_node(n_id, label, group, val=1):
        if n_id not in nodes_dict:
            node = {"id": n_id, "name": label, "group": group, "val": val}
            nodes.append(node)
            nodes_dict[n_id] = node

    notas_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Notas", "Prework_Orders")
    if not os.path.exists(notas_dir):
        return {"success": True, "data": {"nodes": [], "links": []}}

    import re
    for filename in os.listdir(notas_dir):
        if filename.endswith(".md"):
            filepath = os.path.join(notas_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # Extract basic info
                folio_match = re.search(r"# Folio: (\S+) - (.+)", content)
                especialidad_match = re.search(r"\*\*Especialidad:\*\* (.+)", content)
                
                if folio_match:
                    folio = folio_match.group(1).strip()
                    cliente = folio_match.group(2).strip()
                    especialidad = especialidad_match.group(1).strip() if especialidad_match else "General"
                    
                    # Create nodes
                    add_node(f"cliente_{cliente}", cliente, "cliente", 3)
                    add_node(f"folio_{folio}", folio, "folio", 2)
                    add_node(f"esp_{especialidad}", especialidad, "especialidad", 2)
                    
                    # Create links
                    links.append({"source": f"folio_{folio}", "target": f"cliente_{cliente}"})
                    links.append({"source": f"folio_{folio}", "target": f"esp_{especialidad}"})
            except Exception as e:
                print(f"Error parsing graph node {filename}: {e}")

    return {"success": True, "data": {"nodes": nodes, "links": links}}

@app.post("/api/transcribe_and_analyze")
async def api_transcribe_analyze(file: UploadFile = File(...), apiKey: Optional[str] = Form(None)):
    groq_key = apiKey or os.environ.get("GROQ_API_KEY")
    if not groq_key:
         raise HTTPException(status_code=400, detail="Falta GROQ_API_KEY")

    try:
        content = await file.read()
        transcription = transcribir_audio(groq_key, content, filename=file.filename)
        if "Error" in transcription:
            return {"success": False, "message": transcription}
            
        extraction_res = extraer_informacion(groq_key, transcription)
        if extraction_res.get("error"):
             return {"success": False, "message": extraction_res["error"], "transcription": transcription}
             
        return {
            "success": True,
            "transcription": transcription,
            "data": extraction_res["extraction"]
        }

    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/generate-engineering-questions")
async def api_generate_engineering_questions(file: UploadFile = File(...), apiKey: Optional[str] = Form(None)):
    if apiKey:
        os.environ["GROQ_API_KEY"] = apiKey

    try:
        content = await file.read()
        result = process_audio(content, filename=file.filename)
        if result.get("success"):
            return {
                "success": True,
                "transcription": result["transcription"],
                "data": result["questions"]
            }
        else:
            return {"success": False, "message": result.get("message", "Error desconocido")}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/savePPC")
def api_save_ppc_data(req: SavePPCRequest):
    return process_and_save_work_order(req.payload, req.activeUser)

@app.post("/api/login")
def api_login(creds: LoginRequest):
    username_key = creds.username.strip().upper()
    values = gs_manager.get_sheet_values("USERS")
    user_found = None

    if values and len(values) > 1:
        headers = [h.upper().strip() for h in values[0]]
        try:
            user_idx = headers.index("USERNAME")
            pass_idx = headers.index("PASSWORD")
            role_idx = headers.index("ROLE")
            label_idx = headers.index("LABEL")

            for row in values[1:]:
                if len(row) > user_idx and row[user_idx].strip().upper() == username_key:
                    if len(row) > pass_idx and row[pass_idx] == creds.password:
                        user_found = {
                            "success": True,
                            "role": row[role_idx] if len(row) > role_idx else "USER",
                            "name": row[label_idx] if len(row) > label_idx else username_key,
                            "username": username_key
                        }
                    break
        except ValueError:
            pass

    # NOTA: aquí vivía un diccionario de usuarios con contraseñas reales y
    # funcionales escritas en el fuente. Se eliminó: unas credenciales
    # versionadas en el repo son un riesgo, no un modo de prueba. Para
    # desarrollo sin base, define DEV_LOGIN_USERS en el entorno.
    if not user_found and gs_manager.is_mock:
        user_found = _login_desde_entorno(username_key, creds.password)

    # Auditoría: `registrarLog()` de Apps Script deja una línea por intento de
    # acceso y ahí están las 16.196 entradas históricas de `system_log`. El
    # backend Python no escribía ninguna, así que desde la migración no había
    # rastro de quién entró (§1.11 del plan).
    try:
        from backend.services import auditoria

        auditoria.registrar(
            username_key,
            auditoria.ACCION_LOGIN,
            f"Acceso exitoso ({user_found['role']})" if user_found
            else "Acceso denegado: usuario o contraseña incorrectos",
        )
    except Exception as exc:  # noqa: BLE001 - auditar no puede impedir el login
        print(f"[login] No se pudo auditar el acceso: {exc}")

    if user_found:
        return user_found

    return {"success": False, "message": "Usuario o contraseña incorrectos."}


def _login_desde_entorno(username_key: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Login de desarrollo definido por entorno, nunca por código fuente.

    Formato de `DEV_LOGIN_USERS` (ver .env.example):
        USUARIO:contrasena:ROL:Etiqueta,OTRO:...

    Es un puente temporal hasta que la Fase 4 del plan sustituya este endpoint
    por Supabase Auth con JWT (docs/PLAN_BACKEND_PYTHON.md).
    """
    crudo = os.environ.get("DEV_LOGIN_USERS", "").strip()
    if not crudo:
        return None

    for entrada in crudo.split(","):
        partes = [p.strip() for p in entrada.split(":")]
        if len(partes) < 3 or not partes[0]:
            continue
        usuario, clave, rol = partes[0].upper(), partes[1], partes[2]
        etiqueta = partes[3] if len(partes) > 3 else usuario
        # compare_digest evita filtrar la contraseña por tiempo de respuesta.
        if usuario == username_key and secrets.compare_digest(clave, password):
            return {"success": True, "role": rol, "name": etiqueta, "username": username_key}
    return None

@app.get("/api/data")
def get_data(sheet: str = Query(..., description="Name of the sheet to fetch")):
    values = gs_manager.get_sheet_values(sheet)

    if not values:
        return {"success": True, "data": [], "history": [], "headers": [], "message": f"Falta hoja: {sheet}"}

    if len(values) < 2:
        return {"success": True, "data": [], "history": [], "headers": [], "message": "Vacía"}

    header_row_index = find_header_row(values)
    if header_row_index == -1:
        return {"success": True, "data": [], "headers": [], "message": "Sin formato válido"}

    raw_headers = [str(h).strip() for h in values[header_row_index]]
    valid_indices = [i for i, h in enumerate(raw_headers) if h]
    clean_headers = [raw_headers[i] for i in valid_indices]

    data_rows = values[header_row_index + 1:]
    active_tasks = []
    history_tasks = []
    is_reading_history = False

    for i, row in enumerate(data_rows):
        row_str = "|".join([str(c).upper() for c in row])
        if "TAREAS REALIZADAS" in row_str:
            is_reading_history = True
            continue

        if not any(str(c).strip() for c in row):
            continue

        if valid_indices and len(row) > valid_indices[0] and str(row[valid_indices[0]]).upper() == str(clean_headers[0]).upper():
            continue

        row_obj = {}
        has_data = False

        for k, col_index in enumerate(valid_indices):
            header_name = clean_headers[k]
            val = row[col_index] if col_index < len(row) else ""
            if str(val).strip():
                has_data = True
            row_obj[header_name] = val

        if has_data:
            row_obj['_rowIndex'] = header_row_index + i + 2
            if is_reading_history:
                history_tasks.append(row_obj)
            else:
                active_tasks.append(row_obj)

    return {
        "success": True,
        "data": active_tasks,
        "history": history_tasks,
        "headers": clean_headers
    }

# ======================================================================
# API LEGACY DEL TRACKER (paridad con CODIGO.js / google.script.run)
# ======================================================================
# Cada endpoint es el equivalente en Python de una función del backend de
# Apps Script. El adaptador `api_service.js` los consume para que el
# frontend monolítico funcione igual sobre FastAPI que sobre GAS.
from api.services import tracker_store


class TrackerBatchRequest(BaseModel):
    sheetName: str
    tasks: List[Dict[str, Any]]
    username: Optional[str] = ""


class TrackerTaskRequest(BaseModel):
    sheetName: Optional[str] = ""
    task: Dict[str, Any]
    username: Optional[str] = ""


class GeminiKeyRequest(BaseModel):
    key: str


class DateChangeRequest(BaseModel):
    payload: Dict[str, Any]
    username: Optional[str] = ""


class QuoteAgentRequest(BaseModel):
    month: Optional[int] = None
    year: Optional[int] = None


@app.post("/api/legacy/saveTrackerBatch")
def api_legacy_save_tracker_batch(req: TrackerBatchRequest):
    """apiSaveTrackerBatch: ruteo protegido, folios con prefijo, papa caliente y reverse sync."""
    return tracker_store.save_tracker_batch(req.sheetName, req.tasks, req.username or "")


@app.post("/api/legacy/updateTask")
def api_legacy_update_task(req: TrackerTaskRequest):
    """apiUpdateTask / internalUpdateTask (una fila)."""
    return tracker_store.update_task(req.sheetName or "", req.task, req.username or "")


@app.post("/api/legacy/updatePPCV3")
def api_legacy_update_ppcv3(req: TrackerTaskRequest):
    """apiUpdatePPCV3: PPCV4 para ANTONIA_VENTAS, PPCV3 para el resto."""
    return tracker_store.update_ppcv3(req.task, req.username or "")


@app.get("/api/legacy/weeklyPlan")
def api_legacy_weekly_plan(username: str = Query("", description="Usuario activo")):
    """apiFetchWeeklyPlanData."""
    return tracker_store.fetch_weekly_plan(username)


@app.get("/api/legacy/salesHistory")
def api_legacy_sales_history():
    """apiFetchSalesHistory: cotizaciones agrupadas por vendedor."""
    return tracker_store.fetch_sales_history()


@app.get("/api/legacy/quoteMetrics")
def api_legacy_quote_metrics(month: Optional[int] = Query(None), year: Optional[int] = Query(None)):
    """apiFetchQuoteAgentMetrics: KPIs por reglas (incluye el historial cerrado)."""
    return tracker_store.fetch_quote_metrics(month, year)


@app.post("/api/legacy/runQuoteAgent")
def api_legacy_run_quote_agent(req: QuoteAgentRequest):
    """runQuoteMetricsAgent: reglas + análisis Gemini + notificación."""
    return tracker_store.run_quote_metrics_agent(req.month, req.year)


@app.get("/api/legacy/lastAgentReport")
def api_legacy_last_agent_report():
    """apiGetLastAgentReport."""
    return tracker_store.get_last_agent_report()


@app.post("/api/legacy/writeQuoteMetrics")
def api_legacy_write_quote_metrics(req: QuoteAgentRequest):
    """apiWriteQuoteMetricsToSheet: vuelca los KPIs a KPI_COTIZACIONES."""
    return tracker_store.write_quote_metrics_to_sheet(req.month, req.year)


@app.get("/api/legacy/geminiKey")
def api_legacy_check_gemini_key():
    """apiCheckGeminiKey: solo devuelve un preview, nunca la key completa."""
    return tracker_store.check_gemini_key()


@app.post("/api/legacy/geminiKey")
def api_legacy_save_gemini_key(req: GeminiKeyRequest):
    """apiSaveGeminiKey."""
    return tracker_store.save_gemini_key(req.key)


@app.post("/api/legacy/trackerProductivity")
def api_legacy_tracker_productivity(req: QuoteAgentRequest):
    """runTrackerProductivityAgent: productividad por persona del directorio."""
    month = req.month or datetime.now().month
    year = req.year or datetime.now().year
    resumen = []
    total_activas = 0
    total_cerradas = 0

    for person in {u["name"] for u in get_directory_from_db()}:
        active, history, _ = tracker_store.read_rows(person)
        if not active and not history:
            continue

        def en_periodo(row):
            from api.services import tracker_rules as _rules
            fecha = _rules.parse_sheet_date(_rules.pick_task_value(row, ["FECHA", "FECHA ALTA", "ALTA"]))
            return bool(fecha) and fecha.month == month and fecha.year == year

        activas = [r for r in active if en_periodo(r)]
        cerradas = [r for r in history if en_periodo(r)]
        if not activas and not cerradas:
            continue

        total_activas += len(activas)
        total_cerradas += len(cerradas)
        total = len(activas) + len(cerradas)
        resumen.append({
            "nombre": person,
            "activas": len(activas),
            "cerradas": len(cerradas),
            "cumplimiento": round((len(cerradas) / total) * 100, 1) if total else 0,
        })

    resumen.sort(key=lambda r: r["cerradas"], reverse=True)
    return {
        "success": True,
        "data": {
            "month": month,
            "year": year,
            "totalActivas": total_activas,
            "totalCerradas": total_cerradas,
            "personas": resumen,
            "emailSent": False,
        },
    }


@app.get("/api/legacy/infoBankCompanies")
def api_legacy_info_bank_companies(year: str = Query(...), month: str = Query(...)):
    """apiFetchInfoBankCompanies."""
    return tracker_store.fetch_info_bank_companies(year, month)


@app.get("/api/legacy/unifiedAgenda")
def api_legacy_unified_agenda(username: str = Query("", description="Usuario activo")):
    """apiFetchUnifiedAgenda: tareas, eventos personales y hábitos."""
    return tracker_store.fetch_unified_agenda(username)


@app.post("/api/legacy/logDateChange")
def api_legacy_log_date_change(req: DateChangeRequest):
    """apiLogDateChange: auditoría de cambios de fecha en la tabla de ventas."""
    return tracker_store.log_date_change(req.payload, req.username or "")


@app.post("/api/legacy/resyncDirectory")
def api_legacy_resync_directory():
    """apiResyncDirectory: agrega al directorio los registros base faltantes."""
    existing = {(u["name"].upper().strip(), u["dept"].upper().strip()) for u in get_directory_from_db()}
    missing = [u for u in INITIAL_DIRECTORY
               if (u["name"].upper().strip(), u["dept"].upper().strip()) not in existing]
    for user in missing:
        gs_manager.append_row("DB_DIRECTORY", [user["name"], user["dept"], user["type"]])
    return {
        "success": True,
        "message": (f"Directorio sincronizado: {len(missing)} registro(s) agregado(s)."
                    if missing else "El directorio ya estaba sincronizado."),
    }


# ======================================================================
# CAPA RELACIONAL (Fase 1) — /api/v2
# ======================================================================
# Convive con los endpoints de arriba en vez de sustituirlos: el sistema está
# en uso diario y el corte por módulo es la última fase del plan. Si el paquete
# no puede importarse, la app arranca igual: `/api/v2` simplemente no existe.
try:
    from backend.routers.tasks import router as tasks_v2_router

    app.include_router(tasks_v2_router)
except Exception as exc:  # pragma: no cover - depende del entorno
    print(f"Capa relacional /api/v2 no disponible: {exc}")


app.mount("/", StaticFiles(directory=".", html=True), name="root")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
