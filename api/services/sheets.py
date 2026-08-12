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
# El organigrama (directorio semilla, 19 departamentos y perfiles) vive en
# `organigrama.py`. Aquí solo se reexporta para no romper los importadores
# existentes: tener dos copias fue justo el problema —este módulo mantenía un
# directorio de 55 registros en 9 departamentos y el oficial son 38 en 17, con
# 19 departamentos declarados.
from api.services.organigrama import (  # noqa: F401  (reexportado a propósito)
    ALL_DEPTS,
    INITIAL_DIRECTORY,
    PERFILES,
)


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

# Orden y nombres de la vista `STAFF_TRACKER` del original, columna por columna.
# El orden no es cosmética: el equipo lleva años leyendo esta tabla de izquierda
# a derecha, y cambiarlo es lo que hace que un sistema portado «se sienta»
# distinto aunque traiga los mismos datos. `tests/test_tracker_columnas.py` lo
# fija contra la vista de Apps Script.
#
# El nombre de la izquierda es el que viaja al frontend y el que este devuelve al
# guardar, así que cada uno tiene que estar en `ALIAS_DE_HOJA` de
# `backend/schemas/task.py` o el valor se descarta en silencio.
#
# OJO con los nombres que contienen `FECHA` o `F. INICIO`: `index.html` decide
# por el nombre si la celda lleva selector de fecha (`tests/test_selector_de_fecha.py`).
TASK_HEADER_MAP = [
    ("FOLIO", "folio"),
    ("ALTA", "departamento"),
    ("FECHA", "fecha_alta"),
    ("HORA", "hora_alta"),
    ("CLASIFICACION", "clasificacion"),
    ("CONCEPTO", "concepto"),
    ("INVOLUCRADOS", "assignee_raw"),
    ("AVANCE %", "avance"),
    ("FECHA_ESTIMADA_FIN", "fecha_estimada_fin"),
    ("HORA_ESTIMADA_FIN", "hora_estimada_fin"),
    ("RELOJ", "reloj"),
    ("RESTRICCIONES", "restricciones"),
    ("PRIORIDADES", "prioridad"),
    ("RIESGOS", "riesgos"),
    ("FECHA_RESPUESTA", "fecha_respuesta"),
    ("CORREO", "correo"),
    ("CARPETA", "carpeta"),
    ("STATUS", "status"),
    # Hasta aquí, la vista del original. Lo que sigue existe en la tabla pero no
    # se enseña en esa hoja; va detrás para no alterar el orden que el equipo
    # tiene memorizado.
    ("CUMPLIMIENTO", "cumplimiento"),
    ("COMENTARIOS", "comentarios"),
    ("COMENTARIOS_SEMANA", "comentarios_semana"),
    ("COMENTARIOS_SEMANA_PREVIA", "comentarios_semana_previa"),
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
    # La columna real es `prioridad_cot`. Apuntar a `prio_cot` (que no existe
    # en el esquema) dejaba la columna permanentemente vacía pese a tener
    # datos en 33 de las 661 cotizaciones.
    ("PRIO. COT.", "prioridad_cot"),
    ("INFO CLIENTE", "info_cliente"),
    ("F2", "f2"),
    ("COTIZACION", "cotizacion"),
    ("TIMELINE", "timeline"),
    ("LAYOUT", "layout"),
    # MONTO forma parte de DEFAULT_SALES_HEADERS (CODIGO.js): el frontend lo
    # espera en toda hoja de ventas.
    ("MONTO", "monto"),
    # Alimentan el timeline de cotización ("Papa Caliente") en la vista.
    ("MAP COT", "map_cot"),
    ("PROCESO_LOG", "proceso_log"),
]

def _celda(valor):
    """
    Serializa una celda preservando el cero.

    `str(valor or "")` convertía 0 en cadena vacía, porque en Python `0 or ""`
    es `""`. Eso borraba el avance de 198 cotizaciones que están al 0 %: la
    vista las mostraba en blanco, como si nadie hubiera capturado el dato.
    """
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "SI" if valor else "NO"
    # `numeric` de Postgres llega como float: 0.0 y 45.0 se mostraban como
    # "0.0" y "45.0" en la tabla. Se rinden como enteros cuando no hay parte
    # decimal, que es como se veían en la hoja.
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


# Columnas técnicas: se exponen igual (la vista debe mostrarlo todo), pero al
# final, para que las columnas de trabajo sigan apareciendo primero.
COLUMNAS_TECNICAS = ("source_sheet", "created_at", "vendedor_id", "assignee_id",
                     "dedupe_key", "folio_sintetico", "id")


def _nombre_visible(columna):
    """`prioridad_cot` -> `PRIORIDAD_COT`. Predecible y reversible."""
    return str(columna).upper()


def build_header_map(rows, header_map):
    """
    Mapa de columnas completo: las curadas primero, y detrás **todas** las que
    traiga la tabla y no estén ya cubiertas.

    Los mapas escritos a mano se quedaban cortos y había que ampliarlos en cada
    cambio de esquema: `quotes` exponía 23 de 37 columnas y `tasks` 16 de 28.
    Peor, un nombre mal escrito (el caso real de `prio_cot`, que no existe) no
    lo detectaba nadie hasta que un usuario reportaba la columna vacía.

    Descubriendo las columnas desde los datos, una columna nueva en Postgres
    aparece sola y una mal escrita en el mapa curado se nota enseguida, porque
    la columna real sale igualmente con su nombre crudo.
    """
    mapa = list(header_map)
    ya_mapeadas = {col for _, col in mapa}
    nombres_usados = {h.upper() for h, _ in mapa}

    presentes = []
    vistas = set()
    for fila in rows or []:
        for col in fila.keys():
            if col not in vistas:
                vistas.add(col)
                presentes.append(col)

    def agregar(columnas):
        for col in columnas:
            if col in ya_mapeadas:
                continue
            visible = _nombre_visible(col)
            if visible in nombres_usados:      # no duplicar encabezados
                continue
            nombres_usados.add(visible)
            ya_mapeadas.add(col)
            mapa.append((visible, col))

    agregar([c for c in presentes if c not in COLUMNAS_TECNICAS])
    agregar([c for c in presentes if c in COLUMNAS_TECNICAS])
    return mapa


def _rows_to_values(rows, header_map):
    if not rows:
        return None
    mapa = build_header_map(rows, header_map)
    headers = [h for h, _ in mapa]
    values = [headers]
    for row in rows:
        values.append([_celda(row.get(col)) for _, col in mapa])
    return values


# --- Auto-archivado al leer -----------------------------------------------
# En la hoja, las tareas terminadas viven debajo de un separador literal
# "TAREAS REALIZADAS": `apiFetchStaffTrackerData` corta ahí y devuelve
# `{data, history}`. En la base no hay filas por debajo de nada, así que el
# separador se reconstruye al leer, colocando cada tarea de un lado o del otro
# según su estado (avance al 100 %, estatus terminal o CUMPLIMIENTO = SI).
#
# Sin esto, la tabla del tracker mostraba TODO como activo —incluidas 3.101 de
# las 4.626 tareas, que están terminadas— y el historial salía vacío. El
# frontend no cambia: sigue viendo la misma forma que le daba Apps Script.

SEPARADOR_ARCHIVO = "TAREAS REALIZADAS"


def _esta_archivada(fila, campo_estatus="status", campo_cumplimiento="cumplimiento"):
    """
    ¿La fila va bajo `TAREAS REALIZADAS`?

    Es la regla del original (`CODIGO.js:2485-2560`), que la aplica a **toda**
    hoja: `internalBatchUpdateTasks` corre para la que se esté guardando, sea un
    tracker o una hoja de ventas. Los nombres de columna cambian entre `tasks`
    (`status`, `cumplimiento`) y `quotes` (`estatus`, `completada`), de ahí los
    parámetros; la condición es la misma.
    """
    from api.services.tracker_rules import (
        is_progress_complete_pct,
        is_terminal_status,
    )

    if is_progress_complete_pct(fila.get("avance")):
        return True
    if is_terminal_status(fila.get(campo_estatus)):
        return True
    return str(fila.get(campo_cumplimiento) or "").upper().strip() == "SI"


def _valores_con_archivado(rows, header_map, campo_estatus="status",
                           campo_cumplimiento="cumplimiento"):
    """Matriz de una hoja con su separador `TAREAS REALIZADAS`."""
    if not rows:
        return None

    def archivada(fila):
        return _esta_archivada(fila, campo_estatus, campo_cumplimiento)

    # El mapa de columnas se calcula sobre TODAS las filas, no sobre cada
    # grupo: si se hiciera por grupo, una columna que solo aparece en las
    # archivadas desplazaría los encabezados entre una mitad y otra.
    mapa = build_header_map(rows, header_map)
    headers = [h for h, _ in mapa]

    def a_celdas(fila):
        return [_celda(fila.get(col)) for _, col in mapa]

    activas = [f for f in rows if not archivada(f)]
    archivadas = [f for f in rows if archivada(f)]

    values = [headers]
    values.extend(a_celdas(f) for f in activas)
    if archivadas:
        separador = ["" for _ in headers]
        separador[2 if len(headers) > 2 else 0] = SEPARADOR_ARCHIVO
        values.append(separador)
        values.extend(a_celdas(f) for f in archivadas)
    return values


def _valores_de_tareas(rows):
    """Hoja de tracker: el estatus está en `status` y el cierre en `cumplimiento`."""
    return _valores_con_archivado(rows, TASK_HEADER_MAP)


def _valores_de_cotizaciones(rows):
    """
    Hoja de ventas: mismas reglas, otros nombres de columna.

    Antes pasaba por `_rows_to_values`, que no inserta el separador, así que
    `history` salía siempre vacío y TODA cotización caía en la pestaña
    COTIZACIONES EN PROCESO — incluidas 376 de las 583 de ANTONIA_VENTAS que
    están al 100 %, algunas con fecha de visita de 2025.
    """
    return _valores_con_archivado(rows, QUOTE_HEADER_MAP,
                                  campo_estatus="estatus",
                                  campo_cumplimiento="completada")


# --- Resolución tolerante del nombre de hoja -------------------------------
# `source_sheet` guarda el nombre tal como estaba en el Spreadsheet, sin
# normalizar: hay capitalización mixta ("Sebastian Padilla (VENTAS)") y hojas
# con espacio inicial (" LILIANA AYLIN MARTINEZ IBARRA"). El frontend pide los
# nombres en mayúsculas, así que una comparación exacta fallaba y cinco de las
# siete hojas de ventas devolvían cero filas.
#
# AGENTS.md §4 exige comparación insensible; aquí se traduce el nombre pedido
# al que realmente está almacenado.

_SOURCE_SHEET_CACHE = {}


def _clave_hoja(nombre):
    return " ".join(str(nombre or "").split()).upper()


def _indice_de_hojas(tabla):
    """Clave normalizada -> `source_sheet` tal como está almacenado."""
    indice = _SOURCE_SHEET_CACHE.get(tabla)
    if indice is None:
        indice = {}
        try:
            for fila in sb_manager.select_distinct(tabla, "source_sheet"):
                real = fila.get("source_sheet")
                if real and _clave_hoja(real) not in indice:
                    indice[_clave_hoja(real)] = real
        except Exception as exc:  # la resolución nunca debe tumbar la lectura
            print(f"No se pudo indexar source_sheet de {tabla}: {exc}")
        _SOURCE_SHEET_CACHE[tabla] = indice
    return indice


def resolve_source_sheet(tabla, sheet_name):
    """
    Devuelve el `source_sheet` real que corresponde a `sheet_name`.

    Si no hay coincidencia, devuelve el nombre pedido sin tocar, para que la
    consulta se comporte como antes en vez de inventar una hoja.
    """
    pedido = str(sheet_name or "")
    if not pedido:
        return pedido
    return _indice_de_hojas(tabla).get(_clave_hoja(pedido), pedido)


def particiones_del_tracker(sheet_name):
    """
    Particiones de `tasks` que forman el tracker de una hoja.

    Casi siempre es una sola —la pedida— y entonces esto se comporta igual que
    `resolve_source_sheet`. Son dos cuando la misma persona tiene guardadas
    tareas bajo sus dos nombres: el del organigrama, que es el que abre su
    vista, y el del directorio, que es el que ofrecía el selector de
    involucrados al asignar. Ver `organigrama.hojas_de_persona`.

    Sin esto, el arreglo del guardado solo serviría para lo que se capture de
    hoy en adelante y lo ya archivado con el otro nombre seguiría invisible
    para su dueño.
    """
    from api.services import organigrama

    principal = resolve_source_sheet("tasks", sheet_name)
    hojas = [principal]
    vistas = {_clave_hoja(principal)}

    indice = _indice_de_hojas("tasks")
    for alias in organigrama.hojas_de_persona(sheet_name):
        real = indice.get(_clave_hoja(alias))
        if real and _clave_hoja(real) not in vistas:
            vistas.add(_clave_hoja(real))
            hojas.append(real)
    return hojas


def reset_source_sheet_cache():
    """Invalida el índice (las pruebas y un resync del directorio lo usan)."""
    _SOURCE_SHEET_CACHE.clear()
    _PLAN_SEMANAL_CACHE.clear()


# --- PPCV3: el PPC maestro ------------------------------------------------
# `PPCV3` no existe como `source_sheet` en `tasks` ni como tabla propia: la
# migración partió la hoja en dos. Las columnas de tarea fueron a `tasks`
# etiquetadas con el tracker personal de cada quien (963 en `ADMINISTRADOR`,
# 39 en `PPCV4`, 20 en `ANTONIA PINEDA LOPEZ`…), y `plan_semanal` quedó como
# índice: sus 1.180 filas con `source_sheet='PPCV3'` guardan en `task_folio`
# qué tareas pertenecen al PPC maestro.
#
# Reconstruir la hoja es entonces resolver ese índice contra `tasks`. Decisión
# del dueño (2026-07) entre las tres reconstrucciones posibles; ver
# docs/PLAN_BACKEND_PYTHON.md §7.7.

PPC_MASTER_SHEET = "PPCV3"
_PLAN_SEMANAL_CACHE = {}


# --- Hojas cuyo equivalente relacional cambió de nombre --------------------
# La migración renombró varias hojas al pasarlas a tablas. El código legacy
# sigue pidiéndolas por su nombre de hoja y, al no existir una tabla con ese
# nombre, PostgREST respondía PGRST205 y `supabase_manager` devolvía `[]`: una
# vista vacía indistinguible de "no hay nada", que es justo el fallo silencioso
# que la Fase 0 se dedicó a erradicar.
#
# Solo están las que se pudieron confirmar contra el esquema real; una hoja sin
# equivalente comprobado NO se adivina aquí.
TABLAS_POR_HOJA = {
    "AGENDA_PERSONAL": "personal_agenda",
    "HABITOS_LOG": "habits_log",
    "LOG_SISTEMA": "system_log",
    "KPI_COTIZACIONES": "kpi_cotizaciones",
    "PPC_BORRADORES": "ppc_borradores",
    "BANCO_DATOS": "banco_datos",
    "CATALOGOS": "catalogos",
    "DB_WO_MATERIALES": "wo_materiales",
    "DB_WO_MANO_OBRA": "wo_mano_obra",
    "DB_WO_HERRAMIENTAS": "wo_herramientas",
    "DB_WO_EQUIPOS": "wo_equipos",
    "DB_WO_PROGRAMA": "wo_programa",
    "DB_SITIOS": "sites",
    "DB_PROYECTOS": "projects",
    "WORK_ORDERS": "work_orders",
}


def folios_del_ppc_maestro():
    """Folios que `plan_semanal` marca como parte del PPC maestro."""
    if "folios" not in _PLAN_SEMANAL_CACHE:
        folios = []
        try:
            for fila in sb_manager.select("plan_semanal", {"source_sheet": PPC_MASTER_SHEET}):
                folio = fila.get("task_folio")
                if folio:
                    folios.append(folio)
        except Exception as exc:  # la vista nunca debe romperse por esto
            print(f"No se pudieron leer los folios de plan_semanal: {exc}")
        _PLAN_SEMANAL_CACHE["folios"] = list(dict.fromkeys(folios))
    return _PLAN_SEMANAL_CACHE["folios"]


def _filas_del_ppc_maestro():
    """
    Las tareas del PPC maestro, resolviendo el índice de `plan_semanal`.

    Se consulta `tasks` por folio en lotes: son ~1.100 folios y meterlos todos
    en un `in.(...)` haría una URL que PostgREST rechaza.
    """
    folios = folios_del_ppc_maestro()
    if not folios:
        return []

    encontradas = []
    lote = 150
    for inicio in range(0, len(folios), lote):
        trozo = folios[inicio:inicio + lote]
        try:
            encontradas.extend(sb_manager.select_in("tasks", "folio", trozo))
        except Exception as exc:
            print(f"No se pudo leer el lote de tareas del PPC maestro: {exc}")

    # Un mismo folio puede vivir en varias hojas por difusión lateral; aquí se
    # quiere una fila por tarea, así que se deduplica por `id`.
    vistas = set()
    unicas = []
    for fila in encontradas:
        clave = fila.get("id") or fila.get("dedupe_key")
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(fila)
    return unicas


def _alta_en_directorio(values):
    """
    `append_row("DB_DIRECTORY", [nombre, depto, tipo])` -> alta en `people`.

    La hoja `DB_DIRECTORY` es la tabla `people`, con las columnas renombradas
    (`PEOPLE_HEADER_MAP`). Lo usa `apiResyncDirectory`.
    """
    fila = list(values or [])
    nombre = str(fila[0] if fila else "").strip()
    if not nombre:
        return None
    registro = {"nombre": nombre}
    if len(fila) > 1 and str(fila[1]).strip():
        registro["departamento"] = str(fila[1]).strip()
    if len(fila) > 2 and str(fila[2]).strip():
        registro["tipo_hoja"] = str(fila[2]).strip()
    return sb_manager.insert("people", registro)


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

        # PPCV3 se reconstruye resolviendo el índice de `plan_semanal` contra
        # `tasks`. Sin esto la consulta caía a la ruta legacy y preguntaba por
        # una tabla `public.PPCV3` que no existe: PGRST205 en consola y una
        # tabla vacía con `success: true` para todos menos Toñita.
        elif str(sheet_name).strip().upper() == PPC_MASTER_SHEET:
            values = _valores_de_tareas(_filas_del_ppc_maestro())
            if values:
                return values

        else:
            # Sales/quote hojas (e.g. ANTONIA_VENTAS) live in `quotes`,
            # everything else (staff trackers, PPCV3, ADMINISTRADOR mirror,
            # etc.) lives in `tasks`. Both keep the original hoja name in
            # `source_sheet`.
            rows = sb_manager.select("quotes", {"source_sheet": resolve_source_sheet("quotes", sheet_name)})
            values = _valores_de_cotizaciones(rows)
            if values:
                return values

            rows = []
            for particion in particiones_del_tracker(sheet_name):
                rows.extend(sb_manager.select("tasks", {"source_sheet": particion}))
            values = _valores_de_tareas(rows)
            if values:
                return values

        # Nombres de hoja que en el esquema relacional son una tabla con otro
        # nombre (ver TABLAS_POR_HOJA).
        tabla = TABLAS_POR_HOJA.get(str(sheet_name).strip().upper())
        if tabla:
            res = sb_manager.get_sheet_values(tabla)
            if res:
                return res

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
        except Exception:
            return None

    # `write_values` —reemplazar la matriz completa de una hoja— se retiró.
    #
    # Era una operación de Google Sheets sin traducción a una base relacional:
    # "reemplaza todas las filas" no se puede hacer contra una tabla sin borrar
    # datos que nadie pidió borrar. Además era el punto donde se perdían los
    # guardados: sin `credentials.json` caía al modo mock y escribía en un
    # diccionario en memoria que muere con la invocación.
    #
    # El tracker escribe ahora por `backend/services/persistencia.py`, fila a
    # fila y por clave, y los KPIs por `tracker_store.write_quote_metrics_to_sheet`,
    # que inserta una instantánea en `kpi_cotizaciones`.

    def append_row(self, sheet_name, values):
        # El nombre de hoja se traduce a su tabla real antes de insertar: sin
        # esto, `append_row("DB_DIRECTORY", ...)` preguntaba por una tabla
        # `public.DB_DIRECTORY` que no existe y el alta se perdía en silencio.
        destino = str(sheet_name).strip().upper()
        if destino == "DB_DIRECTORY":
            res = _alta_en_directorio(values)
            if res:
                return res
        else:
            tabla = TABLAS_POR_HOJA.get(destino, sheet_name)
            res = sb_manager.append_row(tabla, values)
            if res:
                return res

        if sb_manager.is_configured:
            print(f"[sheets] append_row({sheet_name}): no se pudo insertar en la base.")
            return None

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
    """
    Detector dinámico de encabezados. Delega en `tracker_rules.find_header_row`.

    Había dos implementaciones y **no eran equivalentes**: esta reconocía la
    agenda personal y los hábitos, y la de `tracker_rules` no. Como
    `rows_to_dicts` usa la de allá, `fetch_unified_agenda` devolvía la agenda
    vacía mientras `/api/data`, que usa esta, la leía sin problema.

    Con la delegación la regla vive en un solo sitio y la divergencia no puede
    repetirse (anti-patrón §23.4).
    """
    from api.services.tracker_rules import find_header_row as _find

    return _find(values)

    return -1
