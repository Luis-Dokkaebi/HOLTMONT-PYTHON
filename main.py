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
            ]
        }

    def worksheet(self, name):
        if name in self.sheets:
            return MockSheet(name, self.sheets[name])
        raise gspread.WorksheetNotFound(name)

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

# --- Endpoints ---

class LoginRequest(BaseModel):
    username: str
    password: str

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
