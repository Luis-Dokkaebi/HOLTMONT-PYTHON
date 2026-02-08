from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

app = FastAPI(title="Holtmont Workspace Backend")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify domains
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

# --- Helpers ---

class MockSheet:
    def __init__(self, name, data):
        self.title = name
        self._data = data

    def get_all_values(self):
        return self._data

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
            ],
            "PPCV3": [
                ["FOLIO", "CONCEPTO", "CLASIFICACION", "AREA", "INVOLUCRADOS", "FECHA", "RELOJ", "ESTATUS",
                 "PRIORIDAD", "RESTRICCIONES", "RIESGOS", "FECHA_RESPUESTA", "AVANCE", "COMENTARIOS", "ARCHIVO",
                 "CUMPLIMIENTO", "COMENTARIOS PREVIOS", "REQUISITOR", "CONTACTO", "CELULAR", "FECHA_COTIZACION",
                 "CLIENTE", "TRABAJO", "DETALLES_EXTRA"]
            ],
            "DB_WO_MATERIALES": [
                ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"]
            ],
            "DB_WO_MANO_OBRA": [
                ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "TOTAL"]
            ],
            "DB_WO_HERRAMIENTAS": [
                ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"]
            ],
            "DB_WO_EQUIPOS": [
                ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"]
            ],
            "DB_WO_PROGRAMA": [
                ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "SECCION", "ESTATUS"]
            ]
        }

    def worksheet(self, name):
        if name in self.sheets:
            return MockSheet(name, self.sheets[name])
        # Create mock sheet if not found (auto-create behavior)
        # BUT: For 'get_data', we might want to return 404 if it really doesn't exist
        # However, api_save_ppc relies on creation.
        # Let's keep auto-create but handle empty in get_data logic better.
        self.sheets[name] = [[]]
        return MockSheet(name, self.sheets[name])

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = [[]]
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
            print(f"Error fetching sheet {sheet_name}: {e}")
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

def format_date_value(val):
    if not val:
        return ""
    # In Python gspread returns values as strings usually, but if value_render_option is different it might be formatted.
    # We assume string or maybe datetime object if gspread parses it (it usually doesn't by default).
    return str(val)

def generate_work_order_folio(client_name: str, dept_name: str) -> str:
    """
    Generates a Folio similar to GAS logic: SEQ + CLIENT_ABBR + DEPT_ABBR + DATE
    """
    # Simple sequence simulation. In real app, this should be stored in DB or Properties.
    seq = "0001"

    # Client Abbr
    clean_client = "".join([c for c in (client_name or "XX").upper() if c.isalnum() or c.isspace()]).strip()
    words = clean_client.split()
    client_str = "XX"
    if len(words) >= 2:
        client_str = words[0][0] + words[1][0]
    elif len(words) == 1:
        client_str = words[0][:2]

    # Dept Abbr
    raw_dept = (dept_name or "General").strip().upper()
    abbr_map = {
        "ELECTROMECANICA": "Electro", "CONSTRUCCION": "Const", "MANTENIMIENTO": "Mtto",
        "REMODELACION": "Remod", "REPARACION": "Repar", "RECONFIGURACION": "Reconf",
        "POLIZA": "Poliza", "INSPECCION": "Insp", "ADMINISTRACION": "Admin",
        "MAQUINARIA": "Maq", "DISEÑO": "Diseño", "COMPRAS": "Compras",
        "VENTAS": "Ventas", "HVAC": "HVAC", "SEGURIDAD": "EHS", "EHS": "EHS"
    }
    dept_str = abbr_map.get(raw_dept)
    if not dept_str:
        dept_str = raw_dept[:1] + raw_dept[1:5].lower() if len(raw_dept) > 6 else raw_dept.capitalize()

    date_str = datetime.now().strftime("%d%m%y")
    return f"{seq}{client_str} {dept_str} {date_str}"

def save_child_data(sheet_name: str, items: List[Dict], headers: List[str]):
    """
    Saves a list of dictionaries to a specific sheet with given headers.
    """
    if not items:
        return

    # In a real app, we would get the sheet, check headers, and append rows.
    # For mock/MVP, we just verify we can access the sheet.

    # Prepare rows
    rows = []
    for item in items:
        row = []
        for h in headers:
            # Handle nested objects like 'papaCaliente' if flattened in logic or passed directly
            # Logic in GAS: item[h] || item[h.replace(" ", "_")]
            # Also handle keys that might be lowercase in item but uppercase in header

            # 1. Exact match
            val = item.get(h)

            # 2. Key with spaces replaced by underscore (typical in DB headers)
            if val is None:
                val = item.get(h.replace("_", " "))

            # 3. Lowercase keys (common in payload vs DB headers)
            if val is None:
                # Try finding case-insensitive key
                for k in item.keys():
                    if k.upper().replace("_", " ") == h.upper().replace("_", " "):
                        val = item[k]
                        break

            row.append(str(val if val is not None else ""))
        rows.append(row)

    if gs_manager.is_mock:
        # Just append to mock data
        if sheet_name not in gs_manager.ss.sheets:
             gs_manager.ss.sheets[sheet_name] = [headers]
        gs_manager.ss.sheets[sheet_name].extend(rows)
    else:
        # Real GSpread Logic
        try:
            try:
                sheet = gs_manager.ss.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                sheet = gs_manager.ss.add_worksheet(title=sheet_name, rows=1000, cols=20)
                sheet.append_row(headers)

            sheet.append_rows(rows)
        except Exception as e:
            print(f"Error saving child data to {sheet_name}: {e}")


# --- Endpoints ---

class LoginRequest(BaseModel):
    username: str
    password: str

class SavePPCRequest(BaseModel):
    # Flexible payload to accept list of items or single item
    payload: List[Dict[str, Any]]
    activeUser: str = "ANONYMOUS"

@app.post("/api/savePPC")
def api_save_ppc(req: SavePPCRequest):
    """
    Replicates apiSavePPCData from CODIGO.js.
    Handles Work Order creation and child sheets.
    """
    items = req.payload
    active_user = req.activeUser
    generated_ids = []

    # Config from CODIGO.js
    APP_CONFIG = {
        "ppcSheetName": "PPCV3",
        "woMaterialsSheet": "DB_WO_MATERIALES",
        "woLaborSheet": "DB_WO_MANO_OBRA",
        "woToolsSheet": "DB_WO_HERRAMIENTAS",
        "woEquipSheet": "DB_WO_EQUIPOS",
        "woProgramSheet": "DB_WO_PROGRAMA"
    }

    try:
        for item in items:
            # ID Generation
            item_id = item.get("id")
            if not item_id:
                if active_user == "PREWORK_ORDER":
                    item_id = generate_work_order_folio(item.get("cliente"), item.get("especialidad"))
                else:
                    item_id = f"PPC-{int(datetime.now().timestamp())}"

            generated_ids.append(item_id)

            # --- Save Child Data ---

            # A. Materials
            if "materiales" in item and item["materiales"]:
                mat_items = []
                for m in item["materiales"]:
                    # Flatten papaCaliente
                    pc = m.get("papaCaliente", {})
                    new_m = {
                        "FOLIO": item_id,
                        **m,
                        "RESIDENTE": pc.get("residente", ""),
                        "COMPRAS": pc.get("compras", ""),
                        "CONTROLLER": pc.get("controller", ""),
                        "ORDEN_COMPRA": pc.get("ordenCompra", ""),
                        "PAGOS": pc.get("pagos", ""),
                        "ALMACEN": pc.get("almacen", ""),
                        "LOGISTICA": pc.get("logistica", ""),
                        "RESIDENTE_OBRA": pc.get("residenteObra", "")
                    }
                    mat_items.append(new_m)

                save_child_data(APP_CONFIG["woMaterialsSheet"], mat_items,
                                ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"])

            # B. Labor (Mano de Obra)
            if "manoObra" in item and item["manoObra"]:
                labor_items = [{"FOLIO": item_id, **l} for l in item["manoObra"]]
                save_child_data(APP_CONFIG["woLaborSheet"], labor_items,
                                ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "TOTAL"])

            # C. Tools
            if "herramientas" in item and item["herramientas"]:
                tool_items = []
                for t in item["herramientas"]:
                    pc = t.get("papaCaliente", {})
                    new_t = {
                        "FOLIO": item_id,
                        **t,
                        "RESIDENTE": pc.get("residente", ""),
                        "CONTROLLER": pc.get("controller", ""),
                        "ALMACEN": pc.get("almacen", ""),
                        "LOGISTICA": pc.get("logistica", ""),
                        "RESIDENTE_FIN": pc.get("residenteFin", "")
                    }
                    tool_items.append(new_t)
                save_child_data(APP_CONFIG["woToolsSheet"], tool_items,
                                ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"])

            # D. Equipos
            if "equipos" in item and item["equipos"]:
                equip_items = [{"FOLIO": item_id, **e} for e in item["equipos"]]
                save_child_data(APP_CONFIG["woEquipSheet"], equip_items,
                                ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"])

            # E. Programa
            if "programa" in item and item["programa"]:
                prog_items = []
                for p in item["programa"]:
                    new_p = {
                        "FOLIO": item_id,
                        **p,
                        "SECCION": p.get("seccion", ""),
                        "ESTATUS": p.get("checkStatus") or ("APPLY" if p.get("isActive") else "PENDING")
                    }
                    prog_items.append(new_p)
                save_child_data(APP_CONFIG["woProgramSheet"], prog_items,
                                ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "SECCION", "ESTATUS"])

            # F. Main PPC Entry
            detalles_extra = ""
            if item.get("checkList") or item.get("additionalCosts"):
                detalles_extra = json.dumps({
                    "checkList": item.get("checkList"),
                    "costs": item.get("additionalCosts")
                })

            task_data = {
                'FOLIO': item_id,
                'CONCEPTO': item.get("concepto"),
                'CLASIFICACION': item.get("clasificacion") or "Media",
                'AREA': item.get("especialidad"),
                'INVOLUCRADOS': item.get("responsable"),
                'FECHA': datetime.now().strftime("%d/%m/%y"),
                'RELOJ': item.get("horas"),
                'ESTATUS': "ASIGNADO",
                'PRIORIDAD': item.get("prioridad") or item.get("prioridades"),
                'RESTRICCIONES': item.get("restricciones"),
                'RIESGOS': item.get("riesgos"),
                'FECHA_RESPUESTA': item.get("fechaRespuesta"),
                'AVANCE': "0%",
                'COMENTARIOS': item.get("comentarios", ""),
                'ARCHIVO': item.get("archivoUrl"),
                'CUMPLIMIENTO': item.get("cumplimiento"),
                'COMENTARIOS PREVIOS': item.get("comentariosPrevios", ""),
                'REQUISITOR': item.get("requisitor"),
                'CONTACTO': item.get("contacto"),
                'CELULAR': item.get("celular"),
                'FECHA_COTIZACION': item.get("fechaCotizacion"),
                'CLIENTE': item.get("cliente"),
                'TRABAJO': item.get("TRABAJO"),
                'DETALLES_EXTRA': detalles_extra
            }

            # Save to PPC Sheet
            # Using save_child_data for simplicity as it handles row appending logic
            headers = ["FOLIO", "CONCEPTO", "CLASIFICACION", "AREA", "INVOLUCRADOS", "FECHA", "RELOJ", "ESTATUS",
                       "PRIORIDAD", "RESTRICCIONES", "RIESGOS", "FECHA_RESPUESTA", "AVANCE", "COMENTARIOS", "ARCHIVO",
                       "CUMPLIMIENTO", "COMENTARIOS PREVIOS", "REQUISITOR", "CONTACTO", "CELULAR", "FECHA_COTIZACION",
                       "CLIENTE", "TRABAJO", "DETALLES_EXTRA"]
            save_child_data(APP_CONFIG["ppcSheetName"], [task_data], headers)

        return {"success": True, "message": "Datos procesados correctamente", "ids": generated_ids}

    except Exception as e:
        print(f"Error in api_save_ppc: {e}")
        return {"success": False, "message": str(e)}

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
        # Fix for row length mismatch in Mock/GSpread
        if len(row) < len(raw_headers):
            row = row + ([""] * (len(raw_headers) - len(row)))

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
