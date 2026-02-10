from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, File, Form

# AI Utils
try:
    from api.ai_utils import transcribir_audio, extraer_informacion
except ImportError:
    # Fallback if running from root without api package context
    import sys
    sys.path.append("api")
    from ai_utils import transcribir_audio, extraer_informacion

app = FastAPI(title="Holtmont Workspace Backend")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_ID = None # Can be set via env var or config. If None, mock gspread will look for "Holtmont Workspace" by name or create a mock.

# --- Constants ---
INITIAL_DIRECTORY = [
    { "name": "ANTONIA_VENTAS", "dept": "VENTAS", "type": "VENTAS" },
    { "name": "JUDITH ECHAVARRIA", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "EDUARDO MANZANARES", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "RAMIRO RODRIGUEZ", "dept": "VENTAS", "type": "HIBRIDO" },
    { "name": "SEBASTIAN PADILLA", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "CESAR GOMEZ", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "ALFONSO CORREA", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "TERESA GARZA", "dept": "VENTAS", "type": "HIBRIDO" },
    { "name": "GUILLERMO DAMICO", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "ANGEL SALINAS", "dept": "VENTAS", "type": "HIBRIDO" },
    { "name": "JUAN JOSE SANCHEZ", "dept": "VENTAS", "type": "ESTANDAR" },
    { "name": "LUIS CARLOS", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "ANTONIO SALAZAR", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "ROCIO CASTRO", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "DANIA GONZALEZ", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "JUANY RODRIGUEZ", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "LAURA HUERTA", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "LILIANA MARTINEZ", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "DANIELA CASTRO", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "EDUARDO BENITEZ", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "ANTONIO CABRERA", "dept": "ADMINISTRACION", "type": "ESTANDAR" },
    { "name": "ADMINISTRADOR", "dept": "ADMINISTRACION", "type": "HIBRIDO" },
    { "name": "EDUARDO MANZANARES", "dept": "HVAC", "type": "ESTANDAR" },
    { "name": "JUAN JOSE SANCHEZ", "dept": "HVAC", "type": "ESTANDAR" },
    { "name": "SELENE BALDONADO", "dept": "HVAC", "type": "ESTANDAR" },
    { "name": "ROLANDO MORENO", "dept": "HVAC", "type": "ESTANDAR" },
    { "name": "MIGUEL GALLARDO", "dept": "ELECTROMECANICA", "type": "ESTANDAR" },
    { "name": "SEBASTIAN PADILLA", "dept": "ELECTROMECANICA", "type": "ESTANDAR" },
    { "name": "JEHU MARTINEZ", "dept": "ELECTROMECANICA", "type": "ESTANDAR" },
    { "name": "MIGUEL GONZALEZ", "dept": "ELECTROMECANICA", "type": "ESTANDAR" },
    { "name": "ALICIA RIVERA", "dept": "ELECTROMECANICA", "type": "ESTANDAR" },
    { "name": "RICARDO MENDO", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "CARLOS MENDEZ", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "REYNALDO GARCIA", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "INGE OLIVO", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "EDUARDO TERAN", "dept": "CONSTRUCCION", "type": "HIBRIDO" },
    { "name": "EDGAR HOLT", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "ALEXIS TORRES", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "TERESA GARZA", "dept": "CONSTRUCCION", "type": "HIBRIDO" },
    { "name": "RAMIRO RODRIGUEZ", "dept": "CONSTRUCCION", "type": "HIBRIDO" },
    { "name": "GUILLERMO DAMICO", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "RUBEN PESQUEDA", "dept": "CONSTRUCCION", "type": "ESTANDAR" },
    { "name": "JUDITH ECHAVARRIA", "dept": "COMPRAS", "type": "ESTANDAR" },
    { "name": "GISELA DOMINGUEZ", "dept": "COMPRAS", "type": "ESTANDAR" },
    { "name": "VANESSA DE LARA", "dept": "COMPRAS", "type": "ESTANDAR" },
    { "name": "NELSON MALDONADO", "dept": "COMPRAS", "type": "ESTANDAR" },
    { "name": "VICTOR ALMACEN", "dept": "COMPRAS", "type": "ESTANDAR" },
    { "name": "DIMAS RAMOS", "dept": "EHS", "type": "ESTANDAR" },
    { "name": "CITLALI GOMEZ", "dept": "EHS", "type": "ESTANDAR" },
    { "name": "AIMEE RAMIREZ", "dept": "EHS", "type": "ESTANDAR" },
    { "name": "EDGAR HOLT", "dept": "MAQUINARIA", "type": "ESTANDAR" },
    { "name": "ALEXIS TORRES", "dept": "MAQUINARIA", "type": "ESTANDAR" },
    { "name": "ANGEL SALINAS", "dept": "DISEÑO", "type": "HIBRIDO" },
    { "name": "EDGAR HOLT", "dept": "DISEÑO", "type": "ESTANDAR" },
    { "name": "EDGAR LOPEZ", "dept": "DISEÑO", "type": "HIBRIDO" }
]

ALL_DEPTS = {
    "CONSTRUCCION": { "label": "Construcción", "icon": "fa-hard-hat", "color": "#e83e8c" },
    "COMPRAS": { "label": "Compras/Almacén", "icon": "fa-shopping-cart", "color": "#198754" },
    "EHS": { "label": "Seguridad (EHS)", "icon": "fa-shield-alt", "color": "#dc3545" },
    "DISEÑO": { "label": "Diseño & Ing.", "icon": "fa-drafting-compass", "color": "#0d6efd" },
    "ELECTROMECANICA": { "label": "Electromecánica", "icon": "fa-bolt", "color": "#ffc107" },
    "HVAC": { "label": "HVAC", "icon": "fa-fan", "color": "#fd7e14" },
    "ADMINISTRACION": { "label": "Administración", "icon": "fa-briefcase", "color": "#6f42c1" },
    "VENTAS": { "label": "Ventas", "icon": "fa-handshake", "color": "#0dcaf0" },
    "MAQUINARIA": { "label": "Maquinaria", "icon": "fa-truck", "color": "#20c997" }
}

# --- Helpers ---

SEQUENCES_FILE = "sequences.json"

def get_next_sequence(key, increment=False):
    sequences = {}
    if os.path.exists(SEQUENCES_FILE):
        try:
            with open(SEQUENCES_FILE, 'r') as f:
                sequences = json.load(f)
        except json.JSONDecodeError:
            pass

    current_val = int(sequences.get(key, 1000))
    if increment:
        current_val += 1
        sequences[key] = current_val
        with open(SEQUENCES_FILE, 'w') as f:
            json.dump(sequences, f)

    return str(current_val)

class MockSheet:
    def __init__(self, name, data):
        self.title = name
        self._data = data

    def get_all_values(self):
        return self._data

    def append_row(self, values):
        self._data.append(values)
        return {'updates': {'updatedRows': 1}}

class MockSpreadsheet:
    def __init__(self):
        self.sheets = {
            "USERS": [
                ["USERNAME", "PASSWORD", "ROLE", "LABEL"],
                ["LUIS_CARLOS", "admin2025", "ADMIN", "Administrador"],
                ["ANTONIA_VENTAS", "tonita2025", "TONITA", "Ventas"],
                ["JESUS_CANTU", "ppc2025", "PPC_ADMIN", "PPC Manager"]
            ],
            "ANTONIA_VENTAS": [
                ["FOLIO", "CLIENTE", "CONCEPTO", "FECHA", "ESTATUS", "AVANCE"],
                ["1001", "CLIENTE A", "TEST TASK", "01/01/25", "PENDIENTE", "0%"]
            ]
        }

    def worksheet(self, name):
        if name in self.sheets:
            return MockSheet(name, self.sheets[name])
        raise gspread.WorksheetNotFound(name)

    def add_worksheet(self, title, rows=100, cols=20):
        self.sheets[title] = []
        return MockSheet(title, self.sheets[title])

class GSheetsManager:
    def __init__(self):
        self.client = None
        self.ss = None
        self.is_mock = False
        self.connect()

    def connect(self):
        if os.path.exists(CREDENTIALS_FILE):
            try:
                creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
                self.client = gspread.authorize(creds)
                # Try to open spreadsheet. Usually by name or ID.
                # For this task, we assume there is one main spreadsheet.
                # We'll try to find one named "Holtmont Workspace" or similar, or just pick the first one if possible (not possible with gspread without listing).
                # We will rely on SPREADSHEET_ID env var or a default name.
                try:
                    self.ss = self.client.open("Holtmont Workspace") # Default name assumption
                except gspread.SpreadsheetNotFound:
                    # Fallback: Create one? Or just use mock if not found?
                    print("Spreadsheet 'Holtmont Workspace' not found. Using Mock.")
                    self.is_mock = True
                    self.ss = MockSpreadsheet()
            except Exception as e:
                print(f"Error connecting to GSheets: {e}. Using Mock.")
                self.is_mock = True
                self.ss = MockSpreadsheet()
        else:
            print("credentials.json not found. Using Mock mode.")
            self.is_mock = True
            self.ss = MockSpreadsheet()

    def get_sheet_values(self, sheet_name):
        try:
            if self.is_mock:
                return self.ss.worksheet(sheet_name).get_all_values()

            sheet = self.ss.worksheet(sheet_name)
            return sheet.get_all_values()
        except Exception as e:
            # print(f"Error fetching sheet {sheet_name}: {e}")
            return None

    def append_row(self, sheet_name, values):
        try:
            if self.is_mock:
                try:
                    sheet = self.ss.worksheet(sheet_name)
                except gspread.WorksheetNotFound:
                    self.ss.sheets[sheet_name] = []
                    sheet = self.ss.worksheet(sheet_name)
                return sheet.append_row(values)

            # Real implementation
            try:
                sheet = self.ss.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                sheet = self.ss.add_worksheet(title=sheet_name, rows=1000, cols=26)

            return sheet.append_row(values)
        except Exception as e:
            print(f"Error appending to sheet {sheet_name}: {e}")
            return None

gs_manager = GSheetsManager()

# --- Logic Ported from GAS ---

def find_header_row(values):
    """
    Replicates findHeaderRow from CODIGO.js
    """
    limit = min(100, len(values))
    for i in range(limit):
        # Join columns with |, normalize spaces, uppercase
        row_str = "|".join([str(c).upper().replace("\n", " ").strip() for c in values[i]])

        if "ID_SITIO" in row_str or "ID_PROYECTO" in row_str:
            return i

        has_folio = "FOLIO" in row_str
        has_concepto = "CONCEPTO" in row_str
        has_date_status = any(x in row_str for x in ["ALTA", "AVANCE", "STATUS", "FECHA"])

        if has_folio and has_concepto and has_date_status:
            return i

        if "ID" in row_str and "RESPONSABLE" in row_str:
            return i

        if (("FOLIO" in row_str or "ID" in row_str) and
            ("DESCRIPCI" in row_str or "RESPONSABLE" in row_str or "CONCEPTO" in row_str)):
            return i

        if "CLIENTE" in row_str and ("VENDEDOR" in row_str or "AREA" in row_str or "CLASIFICACION" in row_str):
            return i

        # Extra checks from original code
        if "ID" in row_str and "TITULO" in row_str and "USUARIO" in row_str: return i
        if "ID" in row_str and "HABITO" in row_str and "USUARIO" in row_str: return i

    return -1

def get_directory_from_db():
    values = gs_manager.get_sheet_values("DB_DIRECTORY")
    if not values or len(values) < 2:
        return INITIAL_DIRECTORY

    # Simple parse assuming headers [NOMBRE, DEPARTAMENTO, TIPO_HOJA]
    headers = [str(h).upper().strip() for h in values[0]]
    try:
        name_idx = headers.index("NOMBRE")
        dept_idx = headers.index("DEPARTAMENTO")
        type_idx = headers.index("TIPO_HOJA")
    except ValueError:
        return INITIAL_DIRECTORY # Headers not matching

    directory = []
    for row in values[1:]:
        if len(row) > name_idx and row[name_idx].strip():
            directory.append({
                "name": row[name_idx].strip(),
                "dept": row[dept_idx].strip() if len(row) > dept_idx else "GENERAL",
                "type": row[type_idx].strip() if len(row) > type_idx else "ESTANDAR"
            })
    return directory

def format_date_value(val):
    if not val:
        return ""
    # In Python gspread returns values as strings usually, but if value_render_option is different it might be formatted.
    # We assume string or maybe datetime object if gspread parses it (it usually doesn't by default).
    return str(val)

def save_child_data(sheet_name, items, headers):
    if not items:
        return

    # Ensure sheet exists or create headers
    current_values = gs_manager.get_sheet_values(sheet_name)
    if not current_values or len(current_values) == 0:
        # Sheet doesn't exist or is empty, add headers
        gs_manager.append_row(sheet_name, headers)

    # Map items to rows
    rows_to_append = []
    for item in items:
        row = []
        for h in headers:
            # Handle key variations (space vs underscore) if needed, but we try to be strict for now based on CODIGO.js
            val = item.get(h)
            if val is None:
                # Fallback to key with underscores if header has them but payload key might have spaces or vice versa
                # Actually CODIGO.js says: item[h] || item[h.replace(" ", "_")]
                val = item.get(h.replace(" ", "_"), "")
            row.append(str(val))

        # Append one by one or collect (gspread append_rows is better but we only implemented append_row for mock)
        # Mock supports append_row. Real gspread supports append_row or append_rows.
        # Let's iterate and append row by row for simplicity with our wrapper.
        gs_manager.append_row(sheet_name, row)

def generate_work_order_folio(client_name, dept_name):
    # Get next sequence
    seq_str = get_next_sequence('WORKORDER_SEQ', increment=True)
    seq_padded = seq_str.zfill(4)

    # Clean Client Name
    clean_client = (client_name or "XX").upper().strip()
    # Remove non-alphanumeric chars (keep spaces for splitting)
    import re
    clean_client = re.sub(r'[^A-Z0-9 ]', '', clean_client)
    words = [w for w in clean_client.split() if w]

    client_str = "XX"
    if len(words) >= 2:
        client_str = words[0][0] + words[1][0]
    elif len(words) == 1:
        client_str = words[0][:2]

    # Department
    raw_dept = (dept_name or "General").strip().upper()
    abbr_map = {
        "ELECTROMECANICA": "Electro",
        "ELECTROMECÁNICA": "Electro",
        "CONSTRUCCION": "Const",
        "CONSTRUCCIÓN": "Const",
        "MANTENIMIENTO": "Mtto",
        "REMODELACION": "Remod",
        "REMODELACIÓN": "Remod",
        "REPARACION": "Repar",
        "REPARACIÓN": "Repar",
        "RECONFIGURACION": "Reconf",
        "RECONFIGURACIÓN": "Reconf",
        "POLIZA": "Poliza",
        "PÓLIZA": "Poliza",
        "INSPECCION": "Insp",
        "INSPECCIÓN": "Insp",
        "ADMINISTRACION": "Admin",
        "ADMINISTRACIÓN": "Admin",
        "MAQUINARIA": "Maq",
        "DISEÑO": "Diseño",
        "COMPRAS": "Compras",
        "VENTAS": "Ventas",
        "HVAC": "HVAC",
        "SEGURIDAD": "EHS",
        "EHS": "EHS"
    }

    dept_str = abbr_map.get(raw_dept)
    if not dept_str:
        if len(raw_dept) > 6:
            dept_str = raw_dept[0] + raw_dept[1:5].lower()
        else:
            dept_str = raw_dept[0] + raw_dept[1:].lower()

    # Date
    now = datetime.now()
    date_str = now.strftime("%d%m%y")

    return f"{seq_padded}{client_str} {dept_str} {date_str}"

# --- Endpoints ---

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "API de Holtmont-Python funcionando correctamente",
        "version": "1.0.0"
    }

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

    # Default Logic for other roles (Partial Implementation)
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
    # Returns the next sequence string padded to 4 digits
    # Does not increment, just predicts
    # CODIGO.js says: let seq = Number(props.getProperty('WORKORDER_SEQ') || 0) + 1;
    seq_str = get_next_sequence('WORKORDER_SEQ', increment=False)
    # Actually get_next_sequence returns current value (default 1000).
    # If file doesn't exist, get_next_sequence returns '1000'.
    # If we want to simulate starting from 0 if undefined, we should adjust helper or logic here.
    # CODIGO.js default is 0. My helper default is 1000.
    # Let's align with helper for now or just take int and +1.
    next_val = int(seq_str) + 1
    return str(next_val).zfill(4)

@app.post("/api/transcribe_and_analyze")
async def api_transcribe_analyze(file: UploadFile = File(...), apiKey: Optional[str] = Form(None)):
    """
    Receives an audio file, transcribes it, and extracts structured data.
    """
    # Prefer provided API Key, otherwise env var
    groq_key = apiKey or os.environ.get("GROQ_API_KEY")
    if not groq_key:
         raise HTTPException(status_code=400, detail="Falta GROQ_API_KEY")

    try:
        content = await file.read()

        # 1. Transcribe
        transcription = transcribir_audio(groq_key, content, filename=file.filename)
        if "Error" in transcription:
            return {"success": False, "message": transcription}

        # 2. Extract
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

@app.post("/api/savePPC")
def api_save_ppc_data(req: SavePPCRequest):
    items = req.payload
    active_user = req.activeUser
    generated_ids = []

    # Config (Mirrors APP_CONFIG)
    PPC_SHEET_NAME = "PPCV3"
    WO_MATERIALS_SHEET = "DB_WO_MATERIALES"
    WO_LABOR_SHEET = "DB_WO_MANO_OBRA"
    WO_TOOLS_SHEET = "DB_WO_HERRAMIENTAS"
    WO_EQUIP_SHEET = "DB_WO_EQUIPOS"
    WO_PROGRAM_SHEET = "DB_WO_PROGRAMA"

    # Ensure main sheet exists
    # GSheetsManager.append_row handles creation in mock, but for real we assume it exists or we create headers
    # Let's ensure headers for PPCV3 if empty
    current_ppc = gs_manager.get_sheet_values(PPC_SHEET_NAME)
    if not current_ppc or len(current_ppc) == 0:
        gs_manager.append_row(PPC_SHEET_NAME, ["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA", "CLIENTE", "TRABAJO", "REQUISITOR", "CONTACTO", "CELULAR", "FECHA_COTIZACION"])

    for item in items:
        # ID Generation
        item_id = item.get("id") or item.get("FOLIO")
        if not item_id:
            if active_user == 'PREWORK_ORDER':
                item_id = generate_work_order_folio(item.get("cliente"), item.get("especialidad"))
            else:
                import random
                item_id = "PPC-" + str(random.randint(100000, 999999))

        generated_ids.append(item_id)

        # Child Data Saving
        # A. Materiales
        if item.get("materiales"):
            mat_items = []
            for m in item["materiales"]:
                new_m = m.copy()
                new_m["FOLIO"] = item_id
                # Map Keys
                new_m["CANTIDAD"] = m.get("quantity", "")
                new_m["UNIDAD"] = m.get("unit", "")
                new_m["TIPO"] = m.get("type", "")
                new_m["DESCRIPCION"] = m.get("description", "")
                new_m["COSTO"] = m.get("cost", "")
                new_m["ESPECIFICACION"] = m.get("spec", "")
                new_m["TOTAL"] = m.get("total", "")

                pc = m.get("papaCaliente", {})
                new_m.update({
                    "RESIDENTE": pc.get("residente", ""),
                    "COMPRAS": pc.get("compras", ""),
                    "CONTROLLER": pc.get("controller", ""),
                    "ORDEN_COMPRA": pc.get("ordenCompra", ""),
                    "PAGOS": pc.get("pagos", ""),
                    "ALMACEN": pc.get("almacen", ""),
                    "LOGISTICA": pc.get("logistica", ""),
                    "RESIDENTE_OBRA": pc.get("residenteObra", "")
                })
                mat_items.append(new_m)
            save_child_data(WO_MATERIALS_SHEET, mat_items, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"])

        # B. Mano de Obra
        if item.get("manoObra"):
            labor_items = []
            for l in item["manoObra"]:
                new_l = l.copy()
                new_l["FOLIO"] = item_id
                # Map Keys
                new_l["CATEGORIA"] = l.get("category", "")
                new_l["SALARIO"] = l.get("salary", "")
                new_l["PERSONAL"] = l.get("personnel", "")
                new_l["SEMANAS"] = l.get("weeks", "")
                new_l["EXTRAS"] = l.get("overtime", "")
                new_l["NOCTURNO"] = l.get("night", "")
                new_l["FIN_SEMANA"] = l.get("weekend", "")
                new_l["OTROS"] = l.get("others", "")
                new_l["TOTAL"] = l.get("total", "")
                labor_items.append(new_l)
            save_child_data(WO_LABOR_SHEET, labor_items, ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "TOTAL"])

        # C. Herramientas
        if item.get("herramientas"):
            tool_items = []
            for t in item["herramientas"]:
                new_t = t.copy()
                new_t["FOLIO"] = item_id
                # Map Keys
                new_t["CANTIDAD"] = t.get("quantity", "")
                new_t["UNIDAD"] = t.get("unit", "")
                new_t["DESCRIPCION"] = t.get("description", "")
                new_t["COSTO"] = t.get("cost", "")
                new_t["TOTAL"] = t.get("total", "")

                pc = t.get("papaCaliente", {})
                new_t.update({
                    "RESIDENTE": pc.get("residente", ""),
                    "CONTROLLER": pc.get("controller", ""),
                    "ALMACEN": pc.get("almacen", ""),
                    "LOGISTICA": pc.get("logistica", ""),
                    "RESIDENTE_FIN": pc.get("residenteFin", "")
                })
                tool_items.append(new_t)
            save_child_data(WO_TOOLS_SHEET, tool_items, ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"])

        # D. Equipos
        if item.get("equipos"):
            eq_items = []
            for e in item["equipos"]:
                new_e = e.copy()
                new_e["FOLIO"] = item_id
                # Map Keys
                new_e["CANTIDAD"] = e.get("quantity", "")
                new_e["UNIDAD"] = e.get("unit", "")
                new_e["TIPO"] = e.get("type", "")
                new_e["DESCRIPCION"] = e.get("description", "")
                new_e["ESPECIFICACION"] = e.get("spec", "")
                new_e["DIAS"] = e.get("days", "")
                new_e["HORAS"] = e.get("hours", "")
                new_e["COSTO"] = e.get("cost", "")
                new_e["TOTAL"] = e.get("total", "")
                eq_items.append(new_e)
            save_child_data(WO_EQUIP_SHEET, eq_items, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"])

        # E. Programa
        if item.get("programa"):
            prog_items = []
            for p in item["programa"]:
                new_p = p.copy()
                new_p["FOLIO"] = item_id
                new_p["SECCION"] = p.get("seccion", "")
                new_p["ESTATUS"] = p.get("checkStatus") or ('APPLY' if p.get("isActive") else 'PENDING')

                # Map Keys
                new_p["DESCRIPCION"] = p.get("description", "")
                new_p["FECHA"] = p.get("date", "")
                new_p["DURACION"] = p.get("duration", "")
                new_p["UNIDAD_DURACION"] = p.get("durationUnit", "")
                new_p["UNIDAD"] = p.get("unit", "")
                new_p["CANTIDAD"] = p.get("quantity", "")
                new_p["PRECIO"] = p.get("price", "")
                new_p["TOTAL"] = p.get("total", "")

                resp = p.get("responsable", "")
                if isinstance(resp, list):
                    resp = ", ".join(resp)
                new_p["RESPONSABLE"] = resp

                prog_items.append(new_p)
            save_child_data(WO_PROGRAM_SHEET, prog_items, ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "SECCION", "ESTATUS"])

        # F. Detalles Extra JSON
        detalles_extra = ""
        if item.get("checkList") or item.get("additionalCosts"):
            detalles_extra = json.dumps({
                "checkList": item.get("checkList"),
                "costs": item.get("additionalCosts")
            })

        # Main Task Data
        now_str = datetime.now().strftime("%d/%m/%y")

        task_data = {
            'FOLIO': item_id,
            'CONCEPTO': item.get("concepto", ""),
            'CLASIFICACION': item.get("clasificacion", "Media"),
            'AREA': item.get("especialidad", ""),
            'INVOLUCRADOS': item.get("responsable", ""),
            'FECHA': now_str,
            'RELOJ': item.get("horas", "0"),
            'ESTATUS': "ASIGNADO",
            'PRIORIDAD': item.get("prioridad") or item.get("prioridades", ""),
            'RESTRICCIONES': item.get("restricciones", ""),
            'RIESGOS': item.get("riesgos", ""),
            'FECHA_RESPUESTA': item.get("fechaRespuesta", ""),
            'AVANCE': "0%",
            'COMENTARIOS': item.get("comentarios", ""),
            'ARCHIVO': item.get("archivoUrl", ""),
            'CUMPLIMIENTO': item.get("cumplimiento", "NO"),
            'COMENTARIOS PREVIOS': item.get("comentariosPrevios", ""),
            'REQUISITOR': item.get("requisitor", ""),
            'CONTACTO': item.get("contacto", ""),
            'CELULAR': item.get("celular", ""),
            'FECHA_COTIZACION': item.get("fechaCotizacion", ""),
            'CLIENTE': item.get("cliente", ""),
            'TRABAJO': item.get("TRABAJO", ""),
            'DETALLES_EXTRA': detalles_extra
        }

        # Save to PPCV3
        # We need to map task_data to headers of PPCV3
        ppc_headers = ["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA", "CLIENTE", "TRABAJO", "REQUISITOR", "CONTACTO", "CELULAR", "FECHA_COTIZACION"]

        # Helper to map keys
        ppc_row = []
        for h in ppc_headers:
            # Map aliases
            val = ""
            if h == "ID": val = task_data.get("FOLIO", "")
            elif h == "ESPECIALIDAD": val = task_data.get("AREA", "")
            elif h == "DESCRIPCION": val = task_data.get("CONCEPTO", "")
            elif h == "RESPONSABLE": val = task_data.get("INVOLUCRADOS", "")
            elif h == "FECHA_RESPUESTA": val = task_data.get("FECHA_RESPUESTA", "")
            else: val = task_data.get(h, "")

            ppc_row.append(str(val))

        gs_manager.append_row(PPC_SHEET_NAME, ppc_row)

        # Save to ADMINISTRADOR
        # Ensure ADMINISTRADOR exists
        admin_sheet = "ADMINISTRADOR"
        current_admin = gs_manager.get_sheet_values(admin_sheet)
        if not current_admin or len(current_admin) == 0:
             gs_manager.append_row(admin_sheet, ppc_headers) # Use same headers for simplicity or derive

        # We just append the same row for now as headers match mostly in our simplified logic
        gs_manager.append_row(admin_sheet, ppc_row)

        # Distribution logic (Staff sheets)
        responsables = str(item.get("responsable", "")).split(",")
        for resp in responsables:
            resp_name = resp.strip()
            if resp_name and "(VENTAS)" not in resp_name.upper():
                # Ensure sheet exists
                current_staff = gs_manager.get_sheet_values(resp_name)
                if not current_staff or len(current_staff) == 0:
                    gs_manager.append_row(resp_name, ppc_headers)
                gs_manager.append_row(resp_name, ppc_row)

    return {"success": True, "message": "Datos procesados y distribuidos correctamente.", "ids": generated_ids}

@app.post("/api/login")
def api_login(creds: LoginRequest):
    username_key = creds.username.strip().upper()

    # 1. Try fetching from USERS sheet
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
            # Headers not found, fallback to hardcoded
            pass

    # 2. Fallback to Mock Logic if not found in Sheet (Development Mode)
    # WARNING: Do not store real passwords here in production.
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

    # Extract headers
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

        # Check if empty row
        if not any(str(c).strip() for c in row):
            continue

        # Skip repeated header
        if valid_indices and len(row) > valid_indices[0] and str(row[valid_indices[0]]).upper() == str(clean_headers[0]).upper():
            continue

        row_obj = {}
        has_data = False

        for k, col_index in enumerate(valid_indices):
            header_name = clean_headers[k]
            val = row[col_index] if col_index < len(row) else ""

            # Simple date formatting if needed (gspread returns strings usually)
            # logic from CODIGO.js handles Date objects, here we assume strings

            if str(val).strip():
                has_data = True
            row_obj[header_name] = val

        if has_data:
            row_obj['_rowIndex'] = header_row_index + i + 2 # 1-based index including header
            if is_reading_history:
                history_tasks.append(row_obj)
            else:
                active_tasks.append(row_obj)

    # Sort logic (optional, simpler to do in frontend if needed, but GAS did it)
    # GAS sorted by date desc. We'll skip for MVP to avoid complex date parsing errors,
    # or implement basic string sort if 'FECHA' exists.

    return {
        "success": True,
        "data": active_tasks, # reversed usually means newest first in GAS logic if appended
        "history": history_tasks,
        "headers": clean_headers
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
