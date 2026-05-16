import os
import gspread
from google.oauth2.service_account import Credentials

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
