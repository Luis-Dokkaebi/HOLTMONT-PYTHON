from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
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

from api.routers import auth
app = FastAPI(title="Holtmont Workspace Backend")
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.mount("/", StaticFiles(directory=".", html=True), name="static")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
def api_get_system_config(role: str = Query(..., description="User Role")):
    full_directory = get_directory_from_db()

    ppc_module_master = { "id": "PPC_MASTER", "label": "PPC Maestro", "icon": "fa-tasks", "color": "#fd7e14", "type": "ppc_native" }
    ppc_module_weekly = { "id": "WEEKLY_PLAN", "label": "Planeación Semanal", "icon": "fa-calendar-alt", "color": "#6f42c1", "type": "weekly_plan_view" }
    kpi_module = { "id": "KPI_DASHBOARD", "label": "KPI Performance", "icon": "fa-chart-line", "color": "#d63384", "type": "kpi_dashboard_view" }
    wo_module = { "id": "WORK_ORDER_FORM", "label": "Pre Work Order", "icon": "fa-clipboard-list", "color": "#fd7e14", "type": "work_order_form" }

    if role == 'WORKORDER_USER':
        return {
            "departments": {},
            "allDepartments": ALL_DEPTS,
            "staff": [],
            "directory": full_directory,
            "specialModules": [ wo_module ],
            "accessProjects": False
        }

    # Default Logic for other roles
    ppc_modules = [ ppc_module_master, ppc_module_weekly ]
    special_modules = []

    if role == 'TONITA':
        special_modules = [ ppc_module_master, ppc_module_weekly ]
        return {
            "departments": { "VENTAS": ALL_DEPTS["VENTAS"] },
            "allDepartments": ALL_DEPTS,
            "staff": [ { "name": "ANTONIA_VENTAS", "dept": "VENTAS" } ],
            "directory": full_directory,
            "specialModules": special_modules,
            "accessProjects": False
        }

    if role == 'PPC_ADMIN':
        special_modules = ppc_modules
        return {
            "departments": {},
            "allDepartments": ALL_DEPTS,
            "staff": [],
            "directory": full_directory,
            "specialModules": special_modules,
            "accessProjects": True
        }

    if role == 'ADMIN_CONTROL':
        special_modules = [
            { "id": "PPC_DINAMICO", "label": "Tracker", "icon": "fa-layer-group", "color": "#e83e8c", "type": "ppc_dynamic_view" },
            *ppc_modules,
            { "id": "MIRROR_TONITA", "label": "Monitor Toñita", "icon": "fa-eye", "color": "#0dcaf0", "type": "mirror_staff", "target": "ANTONIA_VENTAS" },
            { "id": "ADMIN_TRACKER", "label": "Control", "icon": "fa-clipboard-list", "color": "#6f42c1", "type": "mirror_staff", "target": "ADMINISTRADOR" }
        ]
        return {
            "departments": ALL_DEPTS,
            "allDepartments": ALL_DEPTS,
            "staff": full_directory,
            "directory": full_directory,
            "specialModules": special_modules,
            "accessProjects": True
        }

    # Default ADMIN
    default_modules = [ *ppc_modules, { "id": "MIRROR_TONITA", "label": "Monitor Toñita", "icon": "fa-eye", "color": "#0dcaf0", "type": "mirror_staff", "target": "ANTONIA_VENTAS" } ]
    if role == 'ADMIN':
        default_modules.insert(0, wo_module)
        default_modules.append(kpi_module)
        obsidian_module = { "id": "OBSIDIAN_GRAPH", "label": "Grafo de Conocimiento", "icon": "fa-project-diagram", "color": "#8b5cf6", "type": "obsidian_graph_view" }
        default_modules.append(obsidian_module)

    return {
        "departments": ALL_DEPTS,
        "allDepartments": ALL_DEPTS,
        "staff": full_directory,
        "directory": full_directory,
        "specialModules": default_modules,
        "accessProjects": True
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

    if not user_found and gs_manager.is_mock:
        MOCK_USER_DB = {
            "LUIS_CARLOS":      {"pass": "admin2025", "role": "ADMIN", "label": "Administrador (Mock)"},
            "ANTONIA_VENTAS":   {"pass": "tonita2025", "role": "TONITA", "label": "Ventas (Mock)"},
            "PREWORK_ORDER":    {"pass": "workorder2026", "role": "WORKORDER_USER", "label": "Workorder (Mock)"},
        }

        if username_key in MOCK_USER_DB:
            u = MOCK_USER_DB[username_key]
            if u["pass"] == creds.password:
                user_found = {
                    "success": True,
                    "role": u["role"],
                    "name": u["label"],
                    "username": username_key
                }

    if user_found:
        return user_found

    return {"success": False, "message": "Usuario o contraseña incorrectos."}

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
