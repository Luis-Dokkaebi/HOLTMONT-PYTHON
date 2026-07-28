import os
import gspread
from google.oauth2.service_account import Credentials
from api.services.supabase_manager import sb_manager

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

# --- Relational schema adapter ---
# api/services/sheets.py used to treat every "hoja" (sheet) as its own Supabase
# table (the Google Sheets model). The current Supabase schema (schema.sql)
# instead unifies everything into a handful of relational tables, keeping the
# original hoja name in a `source_sheet` column for traceability. These maps
# reconstruct the legacy 2D [headers, ...rows] shape the rest of this module
# and api/main.py's /api/data parsing already expect, from the real tables.

PEOPLE_HEADER_MAP = [
    ("NOMBRE", "nombre"),
    ("DEPARTAMENTO", "departamento"),
    ("TIPO_HOJA", "tipo_hoja"),
]

TASK_HEADER_MAP = [
    ("FOLIO", "folio"),
    ("RESPONSABLE", "assignee_raw"),
    ("AREA", "departamento"),
    ("FECHA", "fecha_alta"),
    ("CLASIFICACION", "clasificacion"),
    ("CONCEPTO", "concepto"),
    ("AVANCE", "avance"),
    ("FECHA_ESTIMADA_FIN", "fecha_estimada_fin"),
    ("RELOJ", "reloj"),
    ("RESTRICCIONES", "restricciones"),
    ("PRIORIDAD", "prioridad"),
    ("RIESGOS", "riesgos"),
    ("FECHA_RESPUESTA", "fecha_respuesta"),
    ("CUMPLIMIENTO", "cumplimiento"),
    ("COMENTARIOS", "comentarios"),
    ("ESTATUS", "status"),
]

QUOTE_HEADER_MAP = [
    ("FOLIO", "folio"),
    ("AREA", "area"),
    ("CLIENTE", "cliente"),
    ("CONCEPTO", "concepto"),
    ("CLASIFICACION", "clasificacion"),
    ("VENDEDOR", "vendedor_raw"),
    ("F. VISITA", "f_visita"),
    ("F. INICIO", "f_inicio"),
    ("F. ENTREGA", "f_entrega"),
    ("DIAS", "dias"),
    ("AVANCE", "avance"),
    ("ESTATUS", "estatus"),
    ("COMENTARIOS", "comentarios"),
    ("REQUISITOR", "requisitor"),
    ("PRIO. COT.", "prio_cot"),
    ("INFO CLIENTE", "info_cliente"),
    ("F2", "f2"),
    ("COTIZACION", "cotizacion"),
    ("TIMELINE", "timeline"),
    ("LAYOUT", "layout"),
]

def _rows_to_values(rows, header_map):
    if not rows:
        return None
    headers = [h for h, _ in header_map]
    values = [headers]
    for row in rows:
        values.append([str(row.get(col, "") or "") for _, col in header_map])
    return values


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
        # La hoja "USERS" traía las contraseñas reales de producción escritas en
        # el fuente, y el login caía aquí siempre que no hubiera base de datos.
        # Se eliminó: el login de desarrollo se define ahora por entorno con
        # DEV_LOGIN_USERS (ver .env.example y api/main.py).
        self.sheets = {
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
        # DB_DIRECTORY -> people
        if sheet_name == "DB_DIRECTORY":
            rows = sb_manager.select("people")
            values = _rows_to_values(rows, PEOPLE_HEADER_MAP)
            if values:
                return values

        # USERS has no equivalent table in the relational schema (no auth data
        # was migrated) - always fall through to the mock login below.
        elif sheet_name == "USERS":
            pass

        else:
            # Sales/quote hojas (e.g. ANTONIA_VENTAS) live in `quotes`,
            # everything else (staff trackers, PPCV3, ADMINISTRADOR mirror,
            # etc.) lives in `tasks`. Both keep the original hoja name in
            # `source_sheet`.
            rows = sb_manager.select("quotes", {"source_sheet": sheet_name})
            values = _rows_to_values(rows, QUOTE_HEADER_MAP)
            if values:
                return values

            rows = sb_manager.select("tasks", {"source_sheet": sheet_name})
            values = _rows_to_values(rows, TASK_HEADER_MAP)
            if values:
                return values

        # Legacy path: sheet_name used directly as a Supabase table name
        # (only relevant for tables not covered by the relational schema).
        res = sb_manager.get_sheet_values(sheet_name)
        if res:
            return res

        # Fallback to mock if table doesn't exist or errors out
        try:
            if self.is_mock:
                return self.ss.worksheet(sheet_name).get_all_values()
            sheet = self.ss.worksheet(sheet_name)
            return sheet.get_all_values()
        except Exception as e:
            return None

    def write_values(self, sheet_name, values):
        """
        Reemplaza el contenido completo de una hoja/tabla.

        Necesario para el motor del tracker (auto-archivado y reordenamiento
        de filas), que recalcula la matriz entera. Precedencia:
          1. Google Sheets real (gspread) -> clear + update.
          2. Modo mock -> reemplazo en memoria.
          3. Supabase relacional -> aún no soporta reemplazo de matriz; se
             insertan solo las filas nuevas y se avisa por consola.
        """
        if not values:
            return False
        try:
            if self.is_mock:
                self.ss.sheets[sheet_name] = [list(r) for r in values]
                return True

            try:
                sheet = self.ss.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                sheet = self.ss.add_worksheet(title=sheet_name, rows=max(len(values) + 50, 100), cols=26)

            sheet.clear()
            sheet.update(values)
            return True
        except Exception as e:
            print(f"Error writing values to sheet {sheet_name}: {e}")
            return False

    def append_row(self, sheet_name, values):
        # Using Supabase instead of Google Sheets
        res = sb_manager.append_row(sheet_name, values)
        if res:
            return res
            
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

def get_directory_from_db():
    rows = sb_manager.select("people")
    if not rows:
        return INITIAL_DIRECTORY

    directory = []
    for row in rows:
        name = (row.get("nombre") or "").strip()
        if name:
            directory.append({
                "name": name,
                "dept": (row.get("departamento") or "GENERAL").strip(),
                "type": (row.get("tipo_hoja") or "ESTANDAR").strip()
            })
    return directory

def find_header_row(values):
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
