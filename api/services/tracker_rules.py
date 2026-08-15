"""
======================================================================
MOTOR DE REGLAS DEL TRACKER — PARIDAD CON CODIGO.js (Google Apps Script)
======================================================================
Este módulo es el gemelo en Python de la lógica de negocio que vive en
`CODIGO.js`. No depende de FastAPI, Supabase ni gspread: opera sobre
matrices de valores (list[list]) igual que `Range.getValues()`, de modo
que se puede probar unitariamente y reutilizar desde cualquier capa de
persistencia.

Reglas implementadas (ver AGENTS.md §§2-5):
  * "La Ley de Antonia": ruteo protegido de las hojas (VENTAS).
  * Prefijos de folio por titular (JO-, JC-, LC-, AV-, AP-, ...).
  * Gatekeeper anti-duplicación por `_tempId`.
  * Recuperación de filas por CONCEPTO + FECHA + RESPONSABLE.
  * Auto-archivado a TAREAS REALIZADAS (avance/estatus/cumplimiento).
  * Papa Caliente (PROCESO_LOG / MAP COT) y Reverse Sync saneado.
  * Payload de notificación Make.com -> Outlook con fechas ISO 8601.
  * Métricas de cotizaciones (reglas) para el agente de KPIs.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime, date
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------------
# CONFIGURACIÓN (espejo de las constantes de CODIGO.js)
# ----------------------------------------------------------------------

SALES_MASTER_SHEET = "ANTONIA_VENTAS"
ANTONIA_PERSONAL_SHEET = "ANTONIA PINEDA LOPEZ"
SALES_SUFFIX_RE = re.compile(r"\s*\(VENTAS\)", re.IGNORECASE)

FOLIO_PREFIX_MAP = {
    "JAIME OLIVO": "JO",
    "JESUS CANTU": "JC",
    "LUIS CARLOS": "LC",
    "ADMINISTRADOR": "LC",
    "ANTONIA VENTAS": "AV",
    "ANTONIA PINEDA LOPEZ": "AP",
    "RAMIRO RODRIGUEZ": "RR",
    "SEBASTIAN PADILLA": "SP",
    "TERESA GARZA": "TG",
}
FOLIO_PREFIX_FALLBACK = "PPC-"
FOLIO_STOPWORDS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "EL"}

PROCESS_STEPS = ["L", "CD", "EP", "CI", "EV", "CEC", "RCC"]
FULL_PROCESS_NAMES = {
    "L": "Levantamiento",
    "CD": "Calculo y Diseño",
    "EP": "Elaboracion Presupuesto",
    "CI": "Cotizacion Interna",
    "EV": "Estrategia Ventas",
    "CEC": "Cotizacion Enviada al cliente",
    "RCC": "Revision de Cotizacion Cliente",
}

TERMINAL_STATUSES = {"HECHO", "DONE", "REALIZADO", "COMPLETADO", "TERMINADO", "CERRADO", "FINALIZADO"}
WIN_STATUSES = ["GANADA", "GANADO", "APROBADA", "APROBADO", "VENDIDA", "VENDIDO", "CERRADA GANADA"]
LOSS_STATUSES = ["PERDIDA", "PERDIDO", "CANCELADA", "CANCELADO", "DECLINADA", "RECHAZADA"]

SLA_LIMITS = {"A": 3, "AA": 14, "AAA": 30}
SLA_BUFFERS = {"A": 1, "AA": 2, "AAA": 5}

CORPORATE_DOMAIN = "holtmont.com"
USER_EMAILS = {
    "LUIS_CARLOS": "luis.carlos@holtmont.com",
    "JESUS_CANTU": "jesus.cantu@holtmont.com",
    "ANTONIA_VENTAS": "antonia.pineda@holtmont.com",
    "JAIME_OLIVO": "jaime.olivo@holtmont.com",
    "ANGEL_SALINAS": "angel.salinas@holtmont.com",
    "TERESA_GARZA": "teresa.garza@holtmont.com",
    "EDUARDO_TERAN": "eduardo.teran@holtmont.com",
    "EDUARDO_MANZANARES": "eduardo.manzanares@holtmont.com",
    "RAMIRO_RODRIGUEZ": "ramiro.rodriguez@holtmont.com",
    "SEBASTIAN_PADILLA": "sebastian.padilla@holtmont.com",
    "EDGAR_LOPEZ": "edgar.lopez@holtmont.com",
    "PREWORK_ORDER": "workorder@holtmont.com",
}

COLUMN_ALIASES: Dict[str, List[str]] = {
    "FOLIO": ["FOLIO", "ID"],
    # `ALTA` NO va aqui: es el area (ver "AREA" mas abajo). Con ella puesta,
    # una fila sin fecha devolvia el nombre del departamento como si fuera
    # la fecha, y ese valor alimenta el emparejamiento FOLIO->CONCEPTO+FECHA
    # y la notificacion a Outlook.
    "FECHA": ["FECHA", "FECHAS", "FECHA ALTA", "FECHA INICIO", "FECHA DE INICIO", "FECHA VISITA", "FECHA DE ALTA", "F_INICIO"],
    "CONCEPTO": ["CONCEPTO", "DESCRIPCION", "DESCRIPCIÓN DE LA ACTIVIDAD", "DESCRIPCIÓN", "ACTIVIDAD"],
    "RESPONSABLE": ["RESPONSABLE", "RESPONSABLES", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO"],
    "RELOJ": ["RELOJ", "HORAS", "DIAS", "DÍAS"],
    "ESTATUS": ["ESTATUS", "STATUS"],
    "CUMPLIMIENTO": ["CUMPLIMIENTO", "CUMPL.", "CUMP"],
    "AVANCE": ["AVANCE", "AVANCE %", "% AVANCE"],
    "AREA": ["AREA", "DEPARTAMENTO", "ESPECIALIDAD", "ALTA"],
    "FECHA_RESPUESTA": ["FECHA RESPUESTA", "FECHA FIN", "FECHA ESTIMADA DE FIN", "FECHA ESTIMADA", "FECHA DE ENTREGA", "FECHA_FIN", "DEADLINE"],
    "PRIORIDAD": ["PRIORIDAD", "PRIORIDADES"],
    "ARCHIVO": ["ARCHIVO", "ARCHIVOS", "CLIP", "LINK", "URL", "EVIDENCIA", "DOCUMENTO", "FOTO", "VIDEO"],
    "CLASIFICACION": ["CLASIFICACION", "CLASI"],
    "COMENTARIOS": ["COMENTARIOS", "COMENTARIO", "COMENTARIOS SEMANA EN CURSO", "OBSERVACIONES", "NOTAS", "DETALLES"],
    "FECHA_TERMINO": ["FECHA TERMINO", "FECHA REAL", "TERMINO", "REALIZADO"],
}

ARCHIVE_SEPARATOR = "TAREAS REALIZADAS"

# Claves que NO viajan del trabajador a la hoja maestra.
#
# CUMPLIMIENTO y las fechas de término son del seguimiento del trabajador y no
# significan lo mismo en la fila maestra, así que se filtran siempre.
REVERSE_SYNC_BLOCKED_KEYS = {
    "CUMPLIMIENTO", "FECHA_TERMINO", "FECHA TERMINO",
}

# Claves que además se filtran **cuando la fila es una microtarea de papa
# caliente**, es decir, cuando trae marca de fase en el CONCEPTO.
#
# Es la regla que fijó el dueño: "cuando una persona le de 100% a su micro
# actividad no pasará a tareas realizadas, sino que pasará a color verde ...
# pero hasta que todos tengan 100% saldrá verde". Una fase es una parte de la
# cotización; cerrarla no cierra la venta. Lo que sí viaja es PROCESO_LOG y
# MAP COT, que es donde se pinta el verde, y `build_map_cot` solo lo pinta
# cuando **todas** las entradas de esa fase están en DONE.
#
# Invierte la decisión anterior del proyecto, que sí archivaba la maestra con
# el 100% de un solo trabajador. Las dos pruebas que la fijaban se actualizaron
# a la regla nueva; ver `tests/test_asignacion_bilateral.py`.
#
# Para una asignación normal (sin fase) estas claves **sí** viajan: ahí el 100%
# de quien recibió la actividad debe archivarla en las dos tablas.
FASE_BLOCKED_KEYS = {
    "AVANCE", "AVANCE %", "% AVANCE", "ESTATUS", "STATUS", "ESTADO",
}


class FaseEnCurso(Exception):
    """
    Se intentó delegar una fase dejando otra anterior sin cerrar.

    Es un error de negocio, no un fallo técnico: `save_tracker_batch` lo
    convierte en `{success: false, message}` para que el frontend explique por
    qué no se pudo y quién falta, en vez de guardar una delegación que rompe el
    orden del proceso.
    """


# ----------------------------------------------------------------------
# UTILIDADES BÁSICAS
# ----------------------------------------------------------------------

def normalize_staff_name(value: Any) -> str:
    """Quita guiones bajos y el sufijo (VENTAS): 'ANGEL_SALINAS' -> 'ANGEL SALINAS'."""
    raw = "" if value is None else str(value)
    raw = SALES_SUFFIX_RE.sub(" ", raw).replace("_", " ")
    return re.sub(r"\s+", " ", raw).strip().upper()


def normalize_header(value: Any) -> str:
    raw = "" if value is None else str(value)
    return re.sub(r"\s+", " ", raw.replace("\n", " ")).strip().upper()


def pick_task_value(task: Dict[str, Any], keys: Sequence[str]) -> Any:
    """Lee del payload sin importar mayúsculas/minúsculas ni espacios."""
    if not task:
        return ""
    wanted = [normalize_header(k) for k in keys]
    normalized = {normalize_header(k): k for k in task.keys()}
    for w in wanted:
        original = normalized.get(w)
        if original is None:
            continue
        val = task[original]
        if val not in (None, ""):
            return val
    return ""


def generate_prefix(name: Any) -> str:
    """
    Prefijo de folio del titular de la hoja.
    Usuarios conocidos usan sus iniciales oficiales; el resto genera
    iniciales dinámicas. Nombre vacío o error -> 'PPC-'.
    """
    try:
        raw = normalize_staff_name(re.sub(r"[\-.]+", " ", "" if name is None else str(name)))
        if not raw:
            return FOLIO_PREFIX_FALLBACK
        if raw in FOLIO_PREFIX_MAP:
            return FOLIO_PREFIX_MAP[raw] + "-"
        words = [w for w in raw.split(" ") if w and w not in FOLIO_STOPWORDS]
        if not words:
            return FOLIO_PREFIX_FALLBACK
        candidate = words[0][:2] if len(words) == 1 else words[0][0] + words[1][0]
        # Un prefijo debe empezar con letra: nombres numéricos caen al fallback.
        if not re.match(r"^[A-ZÑ][A-ZÑ0-9]?$", candidate):
            return FOLIO_PREFIX_FALLBACK
        return candidate + "-"
    except Exception:
        return FOLIO_PREFIX_FALLBACK


def folio_sequence_key(sheet_name: Any) -> str:
    base = normalize_staff_name(sheet_name) or "GENERAL"
    if base == "ANTONIA VENTAS":
        return "ANTONIA_SEQ"
    return "SEQ_" + base.replace(" ", "_")


def resolve_user_email(name: Any) -> str:
    """Correo corporativo: USER_EMAILS primero, derivación nombre.apellido después."""
    clean = normalize_staff_name(name)
    if not clean:
        return ""
    key = clean.replace(" ", "_")
    if key in USER_EMAILS:
        return USER_EMAILS[key]
    words = [w for w in clean.split(" ") if w and w not in FOLIO_STOPWORDS]
    if not words:
        return ""
    slug = words[0] if len(words) == 1 else f"{words[0]}.{words[-1]}"
    table = str.maketrans("ÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛÑ", "AAAAEEEEIIIIOOOOUUUUN")
    slug = slug.translate(table).lower()
    slug = re.sub(r"[^a-z0-9.]", "", slug)
    return f"{slug}@{CORPORATE_DOMAIN}" if slug else ""


def resolve_tracker_target(person_name: Any, username: Any) -> Dict[str, Any]:
    """
    "La Ley de Antonia": decide la hoja destino real.
      * Solo ANTONIA_VENTAS escribe en el core de ventas; el resto se
        redirige al tracker personal de Toñita.
      * El sufijo (VENTAS) solo lo respetan Toñita y el titular de la hoja.
    """
    original = ("" if person_name is None else str(person_name)).strip()
    user = normalize_staff_name(username)
    is_antonia_user = user == "ANTONIA VENTAS"

    if original.upper().strip() == SALES_MASTER_SHEET.upper() and not is_antonia_user:
        return {"sheet": ANTONIA_PERSONAL_SHEET, "redirected": True, "reason": "CORE_VENTAS_PROTEGIDO"}

    base = SALES_SUFFIX_RE.sub("", original).strip()
    if base != original:
        is_owner = bool(user) and normalize_staff_name(base) == user
        if not is_antonia_user and not is_owner:
            return {"sheet": base, "redirected": True, "reason": "SUFIJO_VENTAS_PURGADO"}

    return {"sheet": original, "redirected": False, "reason": ""}


def is_sales_sheet(sheet_name: Any) -> bool:
    up = ("" if sheet_name is None else str(sheet_name)).upper()
    return up == SALES_MASTER_SHEET.upper() or "(VENTAS)" in up


# ----------------------------------------------------------------------
# PROGRESO Y ESTATUS
# ----------------------------------------------------------------------

def is_progress_complete(value: Any) -> bool:
    """
    ¿El AVANCE representa el 100 %?
    AGENTS.md §4: el número nativo 1 (celda con formato porcentaje) SÍ es
    100 %, pero el string "1"/"1.0" (que el usuario teclea como 1 %) NO.
    """
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (datetime, date)):
        return False
    if isinstance(value, (int, float)):
        return abs(float(value) - 1) < 0.001 or abs(float(value) - 100) < 0.01
    raw = str(value).strip()
    if not raw:
        return False
    clean = raw.replace("%", "").replace(",", ".").strip()
    try:
        num = float(clean)
    except ValueError:
        return False
    if clean in ("1", "1.0", "1.00"):
        return False
    return abs(num - 100) < 0.01 or (abs(num - 1) < 0.001 and "%" not in raw)


def is_progress_complete_pct(value: Any) -> bool:
    """
    ¿El AVANCE representa el 100 %, **leyéndolo desde la base relacional**?

    Es la gemela de `is_progress_complete()` para el otro dominio, y la
    diferencia entre ambas no es cosmética:

    * En la **hoja**, el número nativo `1` viene de una celda con formato
      porcentual y significa 100 % (AGENTS.md §4). Esa es la regla de arriba y
      no se toca: gobierna lo que llega del frontend y de Apps Script.
    * En la **base**, `avance` ya está normalizado a escala 0-100 por
      `normalize_avance()`, que convirtió aquel `1` en `100`. Ahí el número `1`
      solo puede significar 1 %.

    Aplicar la regla de la hoja sobre un valor ya normalizado archiva como
    terminada cualquier tarea al 1 %. Hoy la trampa está latente porque ninguna
    fila tiene un avance en el intervalo (0,1], pero `SupabaseSync` convierte
    tanto el string "1" como una celda porcentual de 1 % en el número `1`: la
    primera captura de un 1 % la activaría.
    """
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (datetime, date)):
        return False
    if isinstance(value, (int, float)):
        numero = float(value)
    else:
        crudo = str(value).strip()
        if not crudo:
            return False
        try:
            numero = float(crudo.replace("%", "").replace(",", ".").strip())
        except ValueError:
            return False
    return numero >= 100 - 0.01


def is_terminal_status(value: Any) -> bool:
    up = ("" if value is None else str(value)).upper().strip()
    if not up:
        return False
    if up in TERMINAL_STATUSES:
        return True
    return any(up.startswith(s) for s in WIN_STATUSES + LOSS_STATUSES)


def classify_quote_status(value: Any) -> str:
    up = ("" if value is None else str(value)).upper().strip()
    if not up:
        return "EN_PROCESO"
    if any(up.startswith(s) for s in WIN_STATUSES):
        return "GANADA"
    if any(up.startswith(s) for s in LOSS_STATUSES):
        return "PERDIDA"
    return "EN_PROCESO"


# ----------------------------------------------------------------------
# NORMALIZACIÓN DE ESTATUS
# ----------------------------------------------------------------------
# La columna venía de captura libre en la hoja: 45 valores distintos en
# `tasks` y 26 en `quotes` para lo que son ~10 estatus reales. Mezcla
# mayúsculas/minúsculas, acentos, género (ASIGNADO/ASIGNADA), erratas
# (ASIGANDO, PEDIENTE, BIERTO), marcadores de vacío ("-", "-\n-") y texto
# que no es un estatus (iniciales, nombres, comentarios enteros).
#
# Los alias van escritos uno a uno a propósito: una coincidencia difusa
# adivinaría, y aquí un error cambia si una tarea se archiva o no.

CANONICAL_STATUSES = {
    "ASIGNADO": [
        # Género y erratas reales encontradas en los datos.
        "ASIGNADA", "ASIGANDO", "ASIGANDA", "ASIGADO", "ASIGANDOA",
        "ASIGANADO", "ASIGANADA", "ASIGNDO", "ASIGNADOO", "ASIGNAD",
        "ASIGNSDO", "ASIGNBADO", "ASIGNADP",
    ],
    "PENDIENTE": ["PEDIENTE", "PENDIENT", "PENDINTE", "PEDIENTES", "PENDIENTES"],
    "PENDIENTE VISITA": [
        "PENDIENTE DE VISITA", "PDTE VISITA", "PENDIENTE VISTA",
    ],
    "PENDIENTE INFORMACION": [
        "PENDIENTE INFORMACION POR PLANTA", "PENDIENTE DE INFORMACION",
        "PENDIENTE INFO",
    ],
    "FALTA INFORMACION": ["FALTA INFO", "FALTA DE INFORMACION"],
    "EN REVISION": ["REVISION", "EN REVISON", "EN REVICION"],
    "EN PROCESO": ["PROCESO", "EN PROSESO"],
    "ENVIADA": ["ENVIADO", "ENVIDA"],
    "ABIERTO": ["ABIERTA", "BIERTO", "BIERTA"],
    "SUSPENDIDA": ["SUSPENDIDO", "SUSPENDIA"],
    "PERDIDA POR TIEMPO": [
        "PERDIDA X TIEMPO", "PERDIDA POR TIEMPO", "PERDIDA TIEMPO",
        "PERDIDO POR TIEMPO", "PERDIDO X TIEMPO",
    ],
    "CANCELADA": [
        "CANCELADO", "CANCELADA X PLANTA", "CANCELADA POR PLANTA",
        "CANCELADA X CLIENTE", "CANCELADA POR CLIENTE",
    ],
    # Terminales: se conservan tal cual para no alterar el auto-archivado.
    "HECHO": [], "TERMINADO": [], "FINALIZADO": [], "REALIZADO": [],
    "COMPLETADO": [], "DONE": [], "CERRADO": [],
    "GANADA": ["GANADO"], "PERDIDA": ["PERDIDO"],
}

# Marcadores de "sin estatus" que la gente teclea en la hoja.
STATUS_PLACEHOLDERS = {"", "-", "--", "---", "N/A", "NA", "NULL", "NINGUNO",
                       ".", "..", "...", "#N/A", "ESTATUS", "STATUS"}


def _status_key(value: Any) -> str:
    """Mayúsculas, sin acentos, sin puntuación de relleno y con espacios colapsados."""
    if value is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(value))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("\n", " ").replace("\r", " ")
    texto = re.sub(r"[.,;:_/\\-]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip().upper()


_STATUS_LOOKUP = {}
for _canon, _alias in CANONICAL_STATUSES.items():
    _STATUS_LOOKUP[_status_key(_canon)] = _canon
    for _a in _alias:
        _STATUS_LOOKUP[_status_key(_a)] = _canon


def normalize_status(value: Any) -> Optional[str]:
    """
    Estatus canónico, o `None` si el valor no representa uno.

    Devolver `None` en vez de inventar un estatus es deliberado: `RAM`,
    `Nickey Torres` o un comentario entero no son estatus, y mapearlos a
    `PENDIENTE` fabricaría información que nadie capturó.

    No altera nunca si una tarea se considera terminal: cada alias se mapea a
    un canónico de la misma familia (`Perdida x Tiempo` → `PERDIDA POR TIEMPO`,
    que sigue empezando por `PERDIDA`).
    """
    clave = _status_key(value)
    if not clave or clave in STATUS_PLACEHOLDERS:
        return None
    directo = _STATUS_LOOKUP.get(clave)
    if directo:
        return directo
    # Familias con sufijo libre: "PERDIDA X TIEMPO DEL CLIENTE",
    # "CANCELADA X PLANTA 3", etc.
    for prefijo in ("PERDIDA", "PERDIDO"):
        if clave.startswith(prefijo + " ") and "TIEMPO" in clave:
            return "PERDIDA POR TIEMPO"
    for prefijo, canon in (("CANCELAD", "CANCELADA"), ("SUSPENDID", "SUSPENDIDA")):
        if clave.startswith(prefijo):
            return canon
    return None


def is_status_like(value: Any) -> bool:
    """¿El texto es reconocible como estatus? Útil para separar la basura."""
    return normalize_status(value) is not None


def normalize_cell_value(value: Any) -> str:
    """Normaliza una celda para comparaciones (fechas -> dd/MM/yy)."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%y")
    raw = str(value).strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", raw)
    if m:
        yy = m.group(3)[-2:] if len(m.group(3)) == 4 else m.group(3)
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{yy}"
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if iso:
        return f"{iso.group(3)}/{iso.group(2)}/{iso.group(1)[-2:]}"
    return re.sub(r"\s+", " ", raw).strip().upper()


def parse_sheet_date(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    raw = str(value).strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", raw)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return datetime(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def to_iso_z(value: Any) -> str:
    """
    ISO 8601 con milisegundos y 'Z' — formato exigido por Make.com/Outlook
    (AGENTS.md §5). Equivale a `Date.prototype.toISOString()` de JavaScript.
    """
    dt = value if isinstance(value, datetime) else (parse_sheet_date(value) or datetime.utcnow())
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def traffic_light_color(clasificacion: Any, dias: int) -> Optional[str]:
    """
    Color del semáforo equivalente al formato condicional de la hoja:
    verde antes del buffer, amarillo dentro del buffer, rojo pasado el SLA.
    """
    clase = ("" if clasificacion is None else str(clasificacion)).upper().strip()
    if clase not in SLA_LIMITS:
        return None
    limite = SLA_LIMITS[clase]
    inicio_aviso = limite - SLA_BUFFERS[clase]
    if dias > limite:
        return "#FF0000"
    if dias >= inicio_aviso:
        return "#FFFF00"
    return "#00FF00"


# ----------------------------------------------------------------------
# CALENDARIO DEL DASHBOARD
# ----------------------------------------------------------------------
# El calendario semanal junta dos orígenes con **fechas distintas**, y esa es
# la decisión del dueño (2026-08-15): una actividad del tracker se coloca por
# su FECHA (`fecha_alta`) y una cotización por su F. INICIO (`f_inicio`). No es
# un detalle cosmético: `quotes` tiene además F. VISITA y F. ENTREGA, y colocar
# la cotización por la primera columna de fecha que apareciera la habría puesto
# en un día que no es en el que se trabaja.
#
# El tercer origen es la agenda personal, que guarda su FECHA como el tracker.

CALENDAR_ORIGIN_TRACKER = "TRACKER"
CALENDAR_ORIGIN_QUOTES = "COTIZACIONES"
CALENDAR_ORIGIN_PERSONAL = "PERSONAL"

CALENDAR_DATE_ALIASES: Dict[str, List[str]] = {
    CALENDAR_ORIGIN_TRACKER: ["FECHA", "FECHA ALTA", "FECHA_ALTA", "FECHA DE ALTA"],
    CALENDAR_ORIGIN_QUOTES: ["F. INICIO", "F INICIO", "F_INICIO", "FECHA INICIO",
                             "FECHA_INICIO", "FECHA DE INICIO"],
    CALENDAR_ORIGIN_PERSONAL: ["FECHA", "FECHA ALTA", "FECHA_ALTA"],
}


def calendar_date(row: Dict[str, Any], origen: str) -> str:
    """
    Día en el que esta fila se pinta en el calendario, como `YYYY-MM-DD`.

    Cadena vacía si la fila no trae la fecha de su origen: sin fecha no hay
    casilla donde ponerla, y adivinarla con otra columna sería inventar.

    Se devuelve en ISO y no en `dd/MM/yy` a propósito. La base guarda `date` y
    lo que llega a la vista es `str(date)` — ISO —, mientras que el original de
    Apps Script mandaba `dd/MM/yy`; el calendario comparaba contra el segundo
    formato y por eso **no mostraba nada**. Con una columna normalizada, la
    vista compara un solo formato venga de donde venga el dato.
    """
    aliases = CALENDAR_DATE_ALIASES.get(str(origen).upper().strip())
    if not aliases:
        return ""
    fecha = parse_sheet_date(pick_task_value(row, aliases))
    return fecha.strftime("%Y-%m-%d") if fecha else ""


# ----------------------------------------------------------------------
# PAPA CALIENTE (PROCESO_LOG / MAP COT)
# ----------------------------------------------------------------------

def parse_proceso_log(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        return [e for e in value if isinstance(e, dict)]
    try:
        parsed = json.loads(str(value))
        return [e for e in parsed if isinstance(e, dict)] if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def normalize_phase_id(value: Any) -> str:
    raw = ("" if value is None else str(value)).strip()
    if not raw:
        return ""
    up = raw.upper()
    if up in PROCESS_STEPS:
        return up
    for step, label in FULL_PROCESS_NAMES.items():
        if label.upper() == up:
            return step
    m = re.search(r"[🔴🟡]\s*([A-Z]{1,3})", raw)
    if m and m.group(1) in PROCESS_STEPS:
        return m.group(1)
    return ""


def phase_label(step_id: Any) -> str:
    normalized = normalize_phase_id(step_id)
    return FULL_PROCESS_NAMES.get(normalized, "" if step_id is None else str(step_id))


def extract_phase_from_concepto(concepto: Any) -> str:
    raw = "" if concepto is None else str(concepto)
    for marker in reversed(re.findall(r"\[([^\]]+)\]", raw)):
        step = normalize_phase_id(marker.strip())
        if step:
            return step
    return ""


def strip_phase_marker(concepto: Any) -> str:
    raw = "" if concepto is None else str(concepto)
    return re.sub(r"\s*\[[^\]]+\]\s*$", "", raw).strip()


def build_map_cot(log: Any, current_step: Any) -> str:
    """🟢 etapa terminada · 🔴 etapa en curso · ⚪ etapa pendiente."""
    entries = parse_proceso_log(log)
    current = normalize_phase_id(current_step)
    current_idx = PROCESS_STEPS.index(current) if current in PROCESS_STEPS else -1

    parts = []
    for idx, step in enumerate(PROCESS_STEPS):
        step_entries = [e for e in entries if e.get("step") == step or e.get("to") == step]
        if step_entries:
            all_done = all(str(e.get("status", "")).upper() == "DONE" for e in step_entries)
            parts.append(("🟢 " if all_done else "🔴 ") + step)
            continue
        if current_idx > -1 and idx < current_idx:
            parts.append("🟢 " + step)
        elif step == current:
            parts.append("🔴 " + step)
        else:
            parts.append("⚪ " + step)
    return " | ".join(parts)


def upsert_proceso_log_entry(log: Any, step_id: Any, assignee: Any, status: str) -> List[Dict[str, Any]]:
    entries = parse_proceso_log(log)
    step = normalize_phase_id(step_id)
    if not step:
        return entries
    who = ("" if assignee is None else str(assignee)).strip()
    now = datetime.now()

    found = False
    for entry in entries:
        entry_step = entry.get("step") or entry.get("to")
        if entry_step != step:
            continue
        if who and entry.get("assignee") and str(entry["assignee"]).upper().strip() != who.upper():
            continue
        entry["status"] = status
        entry["timestamp"] = int(now.timestamp() * 1000)
        entry["dateStr"] = now.strftime("%d/%m/%Y %H:%M:%S")
        if who and not entry.get("assignee"):
            entry["assignee"] = who
        found = True

    if not found:
        entries.append({
            "step": step,
            "status": status,
            "assignee": who,
            "timestamp": int(now.timestamp() * 1000),
            "dateStr": now.strftime("%d/%m/%Y %H:%M:%S"),
        })
    return entries


def apply_hot_potato(sheet_name: str, task: Dict[str, Any], master_row: Optional[Dict[str, Any]] = None,
                     username: str = "") -> Optional[Dict[str, Any]]:
    """
    Distribución lateral. Muta `task` con PROCESO_LOG y MAP COT y devuelve
    las filas delegadas listas para escribirse en la hoja de cada trabajador.
    Soporta `_assignToWorker`/`_assignStep` (frontend) y PROCESO+INVOLUCRADOS.
    """
    if not task:
        return None
    master = master_row or {}

    workers: List[str] = []
    assign = task.get("_assignToWorker")
    if assign:
        workers = list(assign) if isinstance(assign, (list, tuple)) else [assign]
    if not workers:
        involucrados = pick_task_value(task, ["INVOLUCRADOS", "RESPONSABLE", "ASIGNADO"])
        if involucrados:
            workers = str(involucrados).split(",")
    workers = [str(w).strip() for w in workers if str(w).strip()]
    workers = [w for w in workers if normalize_staff_name(w) != normalize_staff_name(sheet_name)]
    if not workers:
        return None

    step = normalize_phase_id(
        task.get("_assignStep") or pick_task_value(task, ["PROCESO", "ETAPA", "FASE", "MAP COT"])
    )
    if not step:
        return None

    folio = str(pick_task_value(task, ["FOLIO", "ID"]) or "").strip()
    if not folio:
        return None

    # El proceso es una secuencia: no se delega una fase dejando otra anterior
    # a medias. Import diferido para no crear un ciclo — `asignacion` importa
    # las reglas de este módulo.
    from api.services.asignacion import bloqueo_de_fase

    log_previo = pick_task_value(task, ["PROCESO_LOG"]) or master.get("PROCESO_LOG")
    motivo = bloqueo_de_fase(log_previo, step)
    if motivo:
        raise FaseEnCurso(motivo)

    concepto_base = strip_phase_marker(
        pick_task_value(task, ["CONCEPTO", "DESCRIPCION"]) or master.get("CONCEPTO") or master.get("DESCRIPCION") or ""
    )
    cliente = pick_task_value(task, ["CLIENTE"]) or master.get("CLIENTE", "")
    clasificacion = pick_task_value(task, ["CLASIFICACION", "CLASI"]) or master.get("CLASIFICACION", "")
    fecha = pick_task_value(task, ["FECHA", "FECHA ALTA"]) or master.get("FECHA") or datetime.now()

    log = parse_proceso_log(pick_task_value(task, ["PROCESO_LOG"]) or master.get("PROCESO_LOG"))
    for worker in workers:
        log = upsert_proceso_log_entry(log, step, worker, "IN_PROGRESS")

    task["PROCESO_LOG"] = json.dumps(log, ensure_ascii=False)
    task["MAP COT"] = build_map_cot(log, step)

    delegated = [{
        "FOLIO": folio,
        "CLIENTE": cliente,
        "CONCEPTO": f"{concepto_base} [{phase_label(step)}]",
        "FECHA": fecha,
        "ESTATUS": "ASIGNADO",
        "AVANCE": "",
        "CLASIFICACION": clasificacion,
        "RESPONSABLE": worker,
        "VENDEDOR": worker,
        "COMENTARIOS": f"Fase delegada desde {sheet_name} por {username or 'SISTEMA'}",
    } for worker in workers]

    return {"step": step, "workers": workers, "rows": delegated}


def build_reverse_sync_payload(source_sheet: str, task: Dict[str, Any],
                               worker_row: Optional[Dict[str, Any]] = None,
                               master_row: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Payload que devuelve el avance del trabajador a su hoja maestra.

    Qué viaja depende de si la fila es una **microtarea de papa caliente** o una
    **actividad asignada normal**, y esa es la distinción que gobierna todo:

      * **Microtarea** (trae marca de fase en el CONCEPTO): AVANCE y ESTATUS
        **no** viajan. Cerrar una fase no cierra la cotización. Lo que viaja es
        PROCESO_LOG y MAP COT, y `build_map_cot` pinta la fase de verde solo
        cuando todas sus entradas están en DONE — es decir, cuando terminaron
        todos los asignados, no el primero. Ver `FASE_BLOCKED_KEYS`.
      * **Actividad normal** (sin fase): AVANCE y ESTATUS sí viajan, para que el
        100% de quien la recibió la archive también en la tabla de quien la
        asignó. Es la sincronización bilateral.

    En los dos casos:
      * CUMPLIMIENTO y las fechas de término no viajan.
      * No pisa el CONCEPTO maestro con el concepto marcado de la fase: el
        trabajador ve "COTIZAR NAVE [Calculo y Diseño]" y la maestra conserva
        "COTIZAR NAVE".
    """
    folio = str(pick_task_value(task, ["FOLIO", "ID"]) or "").strip()
    if not folio:
        return None
    worker = worker_row or {}
    master = master_row or {}

    phase = extract_phase_from_concepto(worker.get("CONCEPTO") or pick_task_value(task, ["CONCEPTO"]))
    bloqueadas = set(REVERSE_SYNC_BLOCKED_KEYS)
    if phase:
        bloqueadas |= FASE_BLOCKED_KEYS

    clean: Dict[str, Any] = {}
    for key, value in task.items():
        if str(key).startswith("_"):
            continue
        up = normalize_header(key)
        if up in bloqueadas:
            continue
        if up == "CONCEPTO" and re.search(r"\[[^\]]+\]", str(value)):
            continue
        clean[key] = value
    clean["FOLIO"] = folio

    avance = worker.get("AVANCE", pick_task_value(task, ["AVANCE"]))
    estatus = worker.get("ESTATUS", pick_task_value(task, ["ESTATUS"]))
    completed = is_progress_complete(avance) or is_terminal_status(estatus)

    if phase:
        log = upsert_proceso_log_entry(
            master.get("PROCESO_LOG"), phase, normalize_staff_name(source_sheet),
            "DONE" if completed else "IN_PROGRESS",
        )
        clean["PROCESO_LOG"] = json.dumps(log, ensure_ascii=False)
        clean["MAP COT"] = build_map_cot(log, phase)

    return clean


# ----------------------------------------------------------------------
# NOTIFICACIONES (MAKE.COM -> OUTLOOK)
# ----------------------------------------------------------------------

def build_notification_payload(sheet_name: str, task: Dict[str, Any], assignee: Optional[str] = None) -> Dict[str, Any]:
    """Payload del webhook. `fechaInicio` SIEMPRE en ISO 8601 con ms y 'Z'."""
    who = assignee or str(
        pick_task_value(task, ["RESPONSABLE", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO"]) or sheet_name
    ).split(",")[0].strip()

    fecha = parse_sheet_date(pick_task_value(task, ["FECHA", "FECHA ALTA", "FECHA INICIO"])) or datetime.now()
    fecha_fin = parse_sheet_date(pick_task_value(task, ["FECHA_RESPUESTA", "FECHA RESPUESTA", "FECHA FIN"]))

    return {
        "evento": "TAREA_ASIGNADA",
        "hoja": sheet_name,
        "origen": "tabla de ventas" if is_sales_sheet(sheet_name) else "tracker general",
        "esVenta": is_sales_sheet(sheet_name),
        "folio": str(pick_task_value(task, ["FOLIO", "ID"]) or ""),
        "concepto": str(pick_task_value(task, ["CONCEPTO", "DESCRIPCION"]) or ""),
        "responsable": who,
        "email": resolve_user_email(who),
        "cliente": str(pick_task_value(task, ["CLIENTE"]) or ""),
        "clasificacion": str(pick_task_value(task, ["CLASIFICACION", "CLASI"]) or ""),
        "estatus": str(pick_task_value(task, ["ESTATUS", "STATUS"]) or "ASIGNADO"),
        "fechaInicio": to_iso_z(fecha),
        "fechaFin": to_iso_z(fecha_fin) if fecha_fin else "",
        "enviadoEn": to_iso_z(datetime.utcnow()),
    }


def should_notify_sheet(sheet_name: Any) -> bool:
    up = ("" if sheet_name is None else str(sheet_name)).upper().strip()
    if not up:
        return False
    if up.startswith("DB_") or up.startswith("LOG_"):
        return False
    return up not in {"ADMINISTRADOR", "PPCV3", "PPCV4", "PPC_BORRADOR"}


# ----------------------------------------------------------------------
# PLANEACIÓN SEMANAL (equivalente de apiFetchWeeklyPlanData)
# ----------------------------------------------------------------------

def week_number(value: Any) -> Any:
    """
    Número de semana ISO 8601, igual que `getWeekNumber()` de `CODIGO.js`.

    Aquella función desplaza la fecha al jueves de su semana y cuenta desde el
    1 de enero, que es exactamente la definición ISO; `isocalendar()` la
    implementa. Devuelve "-" cuando no hay fecha, como el original.
    """
    fecha = parse_sheet_date(value)
    return fecha.isocalendar()[1] if fecha else "-"


def map_weekly_plan_header(header: Any) -> str:
    """
    Traduce un encabezado de la hoja al nombre que espera la vista.

    Copia literal de la cadena de `if` de `apiFetchWeeklyPlanData`, incluido el
    orden: `ALTA`/`FECHA` se evalúa después de `DESCRIPCI`/`CONCEPTO`, y las
    dos columnas de comentarios se comparan por igualdad exacta, no por
    inclusión, para que "COMENTARIOS SEMANA PREVIA" no acabe en la de la
    semana en curso.
    """
    up = normalize_header(header)
    if "ESPECIALIDAD" in up or "AREA" in up or "DEPARTAMENTO" in up:
        return "ESPECIALIDAD"
    if "DESCRIPCI" in up or "CONCEPTO" in up:
        return "CONCEPTO"
    if "INVOLUCRADOS" in up or "RESPONSABLE" in up or "VENDEDOR" in up or "ENCARGADO" in up:
        return "RESPONSABLE"
    if "ALTA" in up or "FECHA" in up:
        return "FECHA"
    if "RELOJ" in up or "HORAS" in up:
        return "RELOJ"
    if "ARCHIV" in up or "CLIP" in up or "LINK" in up or "EVIDENCIA" in up:
        return "ARCHIVO"
    if "CUMPLIMIENTO" in up:
        return "CUMPLIMIENTO"
    if up in ("COMENTARIOS", "COMENTARIOS SEMANA EN CURSO") or "OBSERVACIONES" in up:
        return "COMENTARIOS SEMANA EN CURSO"
    if up in ("COMENTARIOS PREVIOS", "COMENTARIOS SEMANA PREVIA", "PREVIOS"):
        return "COMENTARIOS SEMANA PREVIA"
    return up


def build_weekly_plan(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    (headers, data) de la vista "Planeación Semanal".

    Reproduce `apiFetchWeeklyPlanData`: renombra los encabezados, antepone la
    columna SEMANA que la vista pinta como `S{{ row.SEMANA }}`, descarta las
    filas sin CONCEPTO ni FOLIO/ID, y devuelve el resultado invertido (lo más
    reciente primero).
    """
    filas = list(rows or [])
    if not filas:
        return {"headers": [], "data": []}

    originales: List[str] = []
    for fila in filas:
        for clave in fila.keys():
            if not str(clave).startswith("_") and clave not in originales:
                originales.append(clave)

    mapeados = [map_weekly_plan_header(h) for h in originales]
    # Si dos columnas mapean al mismo nombre gana la primera, como en GAS,
    # donde el objeto se construye asignando en orden.
    salida: List[Dict[str, Any]] = []
    for fila in filas:
        objeto: Dict[str, Any] = {}
        for original, destino in zip(originales, mapeados):
            objeto.setdefault(destino, fila.get(original))
        if not (objeto.get("CONCEPTO") or objeto.get("FOLIO") or objeto.get("ID")):
            continue
        objeto["SEMANA"] = week_number(objeto.get("FECHA"))
        if "_rowIndex" in fila:
            objeto["_rowIndex"] = fila["_rowIndex"]
        salida.append(objeto)

    vistos = set()
    encabezados = ["SEMANA"]
    for destino in mapeados:
        if destino not in vistos:
            vistos.add(destino)
            encabezados.append(destino)

    salida.reverse()
    return {"headers": encabezados, "data": salida}


# ----------------------------------------------------------------------
# GATEKEEPER ANTI-DUPLICACIÓN (equivalente a CacheService)
# ----------------------------------------------------------------------

class Gatekeeper:
    """
    Candado por `_tempId` con TTL, espejo de `CacheService` en GAS.
    En despliegues multi-worker debe respaldarse con Redis o la propia
    base (una tabla `idempotency_keys`); la interfaz no cambia.
    """

    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[str, float]] = {}

    @staticmethod
    def key_for(sheet_name: str, temp_id: str) -> str:
        return f"GK_{str(sheet_name).upper().strip()}_{temp_id}"

    def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if not entry:
            return None
        value, expires = entry
        if expires < time.time():
            self._store.pop(key, None)
            return None
        return value

    def put(self, key: str, value: str) -> None:
        self._store[key] = (str(value), time.time() + self.ttl)


DEFAULT_GATEKEEPER = Gatekeeper()


# ----------------------------------------------------------------------
# MOTOR DE ESCRITURA SOBRE LA MATRIZ DE LA HOJA
# ----------------------------------------------------------------------

def find_header_row(values: Sequence[Sequence[Any]]) -> int:
    """Detector dinámico de encabezados (AGENTS.md §4): la fila 1 no es fiable."""
    for i in range(min(100, len(values))):
        row_str = "|".join(normalize_header(c) for c in values[i])
        if "ID_SITIO" in row_str or "ID_PROYECTO" in row_str:
            return i
        if "FOLIO" in row_str and "CONCEPTO" in row_str and any(
                x in row_str for x in ("ALTA", "AVANCE", "STATUS", "FECHA")):
            return i
        if "ID" in row_str and "RESPONSABLE" in row_str:
            return i
        if ("FOLIO" in row_str or "ID" in row_str) and any(
                x in row_str for x in ("DESCRIPCI", "RESPONSABLE", "CONCEPTO")):
            return i
        if "CLIENTE" in row_str and any(x in row_str for x in ("VENDEDOR", "AREA", "CLASIFICACION")):
            return i
        # Agenda personal y hábitos. Sus encabezados no tienen FOLIO, CONCEPTO,
        # RESPONSABLE ni CLIENTE, así que ninguna de las reglas anteriores los
        # reconocía.
        #
        # Estas dos reglas **existían en `sheets.find_header_row`** y no aquí:
        # había dos implementaciones del detector y solo una sabía leer la
        # agenda (anti-patrón §23.4). La consecuencia era que `/api/data`, que
        # usa la de `sheets`, sí la leía, mientras `rows_to_dicts` —y con él
        # `fetch_unified_agenda`— devolvía (0, 0, 0) filas: la vista "Mi Agenda
        # Personal" salía vacía con 27 eventos en la base, y los hábitos igual.
        # El fallo era silencioso porque una hoja sin encabezados válidos y una
        # hoja sin datos se ven iguales desde el frontend.
        #
        # Se copian aquí y `sheets.find_header_row` pasa a delegar, para que no
        # puedan volver a divergir. La condición es algo más laxa que la
        # original (no exige la columna de usuario): un export de agenda sin ella
        # también debe poder leerse.
        if "TITULO" in row_str and any(x in row_str for x in ("FECHA", "HORA_INICIO", "TIPO")):
            return i
        if "HABITO" in row_str:
            return i
    return -1


def _build_col_resolver(headers: List[str]) -> Callable[[str], int]:
    col_map = {h: i for i, h in enumerate(headers)}

    def get_col_idx(key: str) -> int:
        k = normalize_header(key)
        if k in col_map:
            return col_map[k]
        for aliases in COLUMN_ALIASES.values():
            if k in aliases:
                for alias in aliases:
                    if alias in col_map:
                        return col_map[alias]
        return -1

    return get_col_idx


class BatchResult:
    """Resultado de `apply_batch_update`."""

    def __init__(self, values, data, moved, appended, notifications, message=""):
        self.values = values
        self.data = data
        self.moved = moved
        self.appended = appended
        self.notifications = notifications
        self.success = message == ""
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "moved": self.moved,
            "appended": self.appended,
            "notifications": self.notifications,
        }


def apply_batch_update(values: List[List[Any]], tasks: List[Dict[str, Any]], sheet_name: str,
                       gatekeeper: Optional[Gatekeeper] = None,
                       sequence_provider: Optional[Callable[[str], str]] = None,
                       skip_notify: bool = False) -> BatchResult:
    """
    Aplica un lote de tareas sobre la matriz de una hoja replicando
    `internalBatchUpdateTasks` de CODIGO.js: búsqueda por folio, gatekeeper
    por `_tempId`, fallback por CONCEPTO+FECHA+RESPONSABLE, asignación de
    folio con prefijo y auto-archivado a TAREAS REALIZADAS.
    """
    if not tasks:
        return BatchResult(values, [], False, 0, [])

    grid = [list(r) for r in (values or [])]
    header_row_index = find_header_row(grid)
    if header_row_index == -1:
        return BatchResult(grid, [], False, 0, [], message="Sin cabeceras válidas")

    headers = [normalize_header(h) for h in grid[header_row_index]]
    total_columns = max(max((len(r) for r in grid), default=0), len(headers))
    for row in grid:
        while len(row) < total_columns:
            row.append("")

    get_col_idx = _build_col_resolver(headers)
    folio_idx = get_col_idx("FOLIO")
    concepto_idx = get_col_idx("CONCEPTO")
    fecha_idx = get_col_idx("FECHA")
    responsable_idx = get_col_idx("RESPONSABLE")
    estatus_idx = get_col_idx("ESTATUS")
    avance_idx = get_col_idx("AVANCE")
    cumplimiento_idx = get_col_idx("CUMPLIMIENTO")
    fecha_termino_idx = get_col_idx("FECHA_TERMINO")

    gk = gatekeeper if gatekeeper is not None else DEFAULT_GATEKEEPER
    seq = sequence_provider or _default_sequence_provider

    def find_by_folio(folio: Any) -> int:
        if folio_idx == -1 or not folio:
            return -1
        target = str(folio).upper().strip()
        for i in range(header_row_index + 1, len(grid)):
            if str(grid[i][folio_idx]).upper().strip() == target:
                return i
        return -1

    def find_by_fingerprint(task: Dict[str, Any]) -> int:
        if concepto_idx == -1 or fecha_idx == -1:
            return -1
        t_concepto = normalize_cell_value(pick_task_value(task, COLUMN_ALIASES["CONCEPTO"]))
        t_fecha = normalize_cell_value(pick_task_value(task, COLUMN_ALIASES["FECHA"]))
        if not t_concepto or not t_fecha:
            return -1
        t_resp = normalize_cell_value(pick_task_value(task, COLUMN_ALIASES["RESPONSABLE"]))
        for i in range(header_row_index + 1, len(grid)):
            row = grid[i]
            if normalize_cell_value(row[concepto_idx]) != t_concepto:
                continue
            if normalize_cell_value(row[fecha_idx]) != t_fecha:
                continue
            if t_resp and responsable_idx > -1:
                row_resp = normalize_cell_value(row[responsable_idx])
                if row_resp and row_resp != t_resp:
                    continue
            return i
        return -1

    rows_to_append: List[List[Any]] = []
    notifications: List[Dict[str, Any]] = []
    processed: List[Dict[str, Any]] = []

    for original_task in tasks:
        task = dict(original_task)
        processed.append(task)

        folio_value = pick_task_value(task, ["FOLIO", "ID"])
        row_index = find_by_folio(folio_value)

        temp_id = str(task.get("_tempId") or "").strip()
        gk_key = Gatekeeper.key_for(sheet_name, temp_id) if temp_id else ""
        already_processed = False
        if gk_key:
            cached = gk.get(gk_key)
            if cached:
                already_processed = True
                if row_index == -1:
                    row_index = find_by_folio(cached)

        if row_index == -1:
            row_index = find_by_fingerprint(task)

        if row_index > -1:
            for key, value in task.items():
                if str(key).startswith("_"):
                    continue
                c_idx = get_col_idx(key)
                if c_idx > -1:
                    grid[row_index][c_idx] = value
            if folio_idx > -1:
                if not str(grid[row_index][folio_idx] or "").strip():
                    grid[row_index][folio_idx] = generate_prefix(sheet_name) + seq(folio_sequence_key(sheet_name))
                task["FOLIO"] = grid[row_index][folio_idx]
            task["_rowIndex"] = row_index + 1
            if gk_key:
                gk.put(gk_key, str(task.get("FOLIO", "")))
            continue

        if already_processed:
            # Petición duplicada del mismo evento de UI: se descarta.
            continue

        new_row: List[Any] = ["" for _ in range(total_columns)]
        for key, value in task.items():
            if str(key).startswith("_"):
                continue
            c_idx = get_col_idx(key)
            if c_idx > -1:
                new_row[c_idx] = value
        if folio_idx > -1 and not new_row[folio_idx]:
            new_row[folio_idx] = folio_value if folio_value else (
                generate_prefix(sheet_name) + seq(folio_sequence_key(sheet_name))
            )
        if folio_idx > -1:
            task["FOLIO"] = new_row[folio_idx]
        if estatus_idx > -1 and not new_row[estatus_idx]:
            new_row[estatus_idx] = "ASIGNADO"
        if gk_key:
            gk.put(gk_key, str(task.get("FOLIO", "")))
        if not skip_notify and should_notify_sheet(sheet_name):
            notifications.append(build_notification_payload(sheet_name, task))
        rows_to_append.append(new_row)

    # --- AUTO-ARCHIVADO ---
    separator_index = -1
    for i, row in enumerate(grid):
        if ARCHIVE_SEPARATOR in "|".join(str(c).upper() for c in row):
            separator_index = i
            break

    head = grid[:header_row_index + 1]
    if separator_index == -1:
        active_rows = grid[header_row_index + 1:]
        separator_rows: List[List[Any]] = []
        history_rows: List[List[Any]] = []
    else:
        active_rows = grid[header_row_index + 1:separator_index]
        separator_rows = [grid[separator_index]]
        history_rows = grid[separator_index + 1:]

    def is_row_complete(row: List[Any]) -> bool:
        if avance_idx > -1 and is_progress_complete(row[avance_idx]):
            return True
        if estatus_idx > -1 and is_terminal_status(row[estatus_idx]):
            return True
        if cumplimiento_idx > -1 and str(row[cumplimiento_idx] or "").upper().strip() == "SI":
            return True
        return False

    new_active: List[List[Any]] = []
    moved_rows: List[List[Any]] = []
    for row in active_rows:
        if is_row_complete(row):
            if fecha_termino_idx > -1 and not row[fecha_termino_idx]:
                row[fecha_termino_idx] = datetime.now().strftime("%d/%m/%y")
            moved_rows.append(row)
        else:
            new_active.append(row)

    if not separator_rows and (moved_rows or rows_to_append):
        sep = ["" for _ in range(total_columns)]
        sep[2 if total_columns > 2 else 0] = ARCHIVE_SEPARATOR
        separator_rows = [sep]

    grid = head + rows_to_append + new_active + separator_rows + moved_rows + history_rows

    return BatchResult(grid, processed, bool(moved_rows), len(rows_to_append), notifications)


_SEQUENCES: Dict[str, int] = {}


def _default_sequence_provider(key: str) -> str:
    """Consecutivo en memoria. En producción se respalda en la base de datos."""
    _SEQUENCES[key] = _SEQUENCES.get(key, 1000) + 1
    return str(_SEQUENCES[key])


def rows_to_dicts(values: Sequence[Sequence[Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Convierte la matriz en (activas, historial, encabezados)."""
    header_row_index = find_header_row(values)
    if header_row_index == -1:
        return [], [], []
    headers = [str(h).strip() for h in values[header_row_index]]
    active: List[Dict[str, Any]] = []
    history: List[Dict[str, Any]] = []
    reading_history = False

    for i in range(header_row_index + 1, len(values)):
        row = values[i]
        joined = "|".join(str(c).upper() for c in row)
        if ARCHIVE_SEPARATOR in joined:
            reading_history = True
            continue
        if not any(str(c).strip() for c in row):
            continue
        obj = {h: (row[j] if j < len(row) else "") for j, h in enumerate(headers) if h}
        obj["_rowIndex"] = i + 1
        (history if reading_history else active).append(obj)

    return active, history, [h for h in headers if h]


# ----------------------------------------------------------------------
# MÉTRICAS DE COTIZACIONES
# ----------------------------------------------------------------------

def compute_quote_metrics(rows: Iterable[Dict[str, Any]], month: Optional[int] = None,
                          year: Optional[int] = None) -> Dict[str, Any]:
    """
    KPIs de cotizaciones. `rows` debe incluir el historial (TAREAS
    REALIZADAS): ahí viven las cotizaciones cerradas que alimentan la
    tasa de cierre y los buckets de ganadas/perdidas.
    """
    now = datetime.now()
    metrics: Dict[str, Any] = {
        "totalCount": 0,
        "month": month or now.month,
        "year": year or now.year,
        "winLoss": {"ganada": 0, "perdida": 0, "enProceso": 0, "total": 0},
        "closeRate": 0,
        "slaSummary": {
            clase: {"slaLimit": limite, "count": 0, "ok": 0, "fail": 0, "avgDays": 0, "pctOk": 0}
            for clase, limite in SLA_LIMITS.items()
        },
        "byCotizadorArr": [],
        "byDepartmentArr": [],
        "aaaByClientArr": [],
        "alerts": [],
    }

    by_cotizador: Dict[str, Dict[str, Any]] = {}
    by_department: Dict[str, Dict[str, Any]] = {}
    aaa_by_client: Dict[str, Dict[str, Any]] = {}
    sla_days: Dict[str, List[int]] = {c: [] for c in SLA_LIMITS}

    for row in rows:
        fecha = parse_sheet_date(pick_task_value(row, ["FECHA", "FECHA INICIO", "FECHA ALTA", "ALTA"]))
        if month and year:
            if not fecha or fecha.month != month or fecha.year != year:
                continue

        metrics["totalCount"] += 1
        estatus = str(pick_task_value(row, ["ESTATUS", "STATUS"]) or "")
        bucket = classify_quote_status(estatus)
        if bucket == "GANADA":
            metrics["winLoss"]["ganada"] += 1
        elif bucket == "PERDIDA":
            metrics["winLoss"]["perdida"] += 1
        else:
            metrics["winLoss"]["enProceso"] += 1
        metrics["winLoss"]["total"] += 1

        vendedor = str(pick_task_value(row, ["VENDEDOR", "RESPONSABLE", "COTIZADOR"]) or "SIN ASIGNAR").upper().strip()
        entry = by_cotizador.setdefault(vendedor, {"nombre": vendedor, "total": 0, "ganada": 0, "perdida": 0, "enProceso": 0})
        entry["total"] += 1
        entry["ganada" if bucket == "GANADA" else ("perdida" if bucket == "PERDIDA" else "enProceso")] += 1

        depto = str(pick_task_value(row, ["AREA", "DEPARTAMENTO", "ESPECIALIDAD"]) or "GENERAL").upper().strip()
        dep = by_department.setdefault(depto, {"nombre": depto, "total": 0, "ganada": 0, "perdida": 0})
        dep["total"] += 1
        if bucket == "GANADA":
            dep["ganada"] += 1
        elif bucket == "PERDIDA":
            dep["perdida"] += 1

        clase = str(pick_task_value(row, ["CLASIFICACION", "CLASI"]) or "").upper().strip()
        if clase in metrics["slaSummary"] and fecha:
            cierre = parse_sheet_date(pick_task_value(row, ["FECHA_TERMINO", "FECHA TERMINO", "FECHA REAL"]))
            dias = ((cierre or now) - fecha).days
            limite = metrics["slaSummary"][clase]["slaLimit"]
            metrics["slaSummary"][clase]["count"] += 1
            sla_days[clase].append(dias)
            if dias <= limite:
                metrics["slaSummary"][clase]["ok"] += 1
            else:
                metrics["slaSummary"][clase]["fail"] += 1
                metrics["alerts"].append({
                    "folio": str(pick_task_value(row, ["FOLIO", "ID"]) or ""),
                    "cliente": str(pick_task_value(row, ["CLIENTE"]) or ""),
                    "vendedor": vendedor,
                    "clasificacion": clase,
                    "dias": dias,
                    "slaLimit": limite,
                    "estatus": estatus,
                })
            if clase == "AAA":
                cli = str(pick_task_value(row, ["CLIENTE"]) or "SIN CLIENTE").upper().strip()
                cli_entry = aaa_by_client.setdefault(cli, {"cliente": cli, "total": 0, "fueraSla": 0})
                cli_entry["total"] += 1
                if dias > limite:
                    cli_entry["fueraSla"] += 1

    for clase, resumen in metrics["slaSummary"].items():
        dias_list = sla_days[clase]
        resumen["avgDays"] = round(sum(dias_list) / len(dias_list), 1) if dias_list else 0
        resumen["pctOk"] = round((resumen["ok"] / resumen["count"]) * 100, 1) if resumen["count"] else 0

    cerradas = metrics["winLoss"]["ganada"] + metrics["winLoss"]["perdida"]
    metrics["closeRate"] = round((metrics["winLoss"]["ganada"] / cerradas) * 100, 1) if cerradas else 0

    metrics["byCotizadorArr"] = sorted(by_cotizador.values(), key=lambda v: v["total"], reverse=True)
    metrics["byDepartmentArr"] = sorted(by_department.values(), key=lambda v: v["total"], reverse=True)
    metrics["aaaByClientArr"] = sorted(aaa_by_client.values(), key=lambda v: v["total"], reverse=True)
    return metrics


def build_quote_metrics_prompt(metrics: Dict[str, Any]) -> str:
    """Prompt del analista para Gemini (~180 palabras, cierra con recomendación operativa)."""
    sla = metrics["slaSummary"]
    fallas = "\n".join(
        f"- Folio {a['folio']} ({a['clasificacion']}) de {a['vendedor']}: {a['dias']} días vs SLA {a['slaLimit']}. Estatus: {a['estatus']}"
        for a in metrics.get("alerts", [])[:15]
    ) or "- Ninguno en el periodo."

    return "\n".join([
        f"Eres el analista de operaciones de Holtmont. Analiza los KPIs de cotizaciones del periodo "
        f"{metrics['month']}/{metrics['year']} y responde en español en aproximadamente 180 palabras.",
        "",
        "DATOS:",
        f"- Cotizaciones totales: {metrics['totalCount']}",
        f"- Ganadas: {metrics['winLoss']['ganada']} | Perdidas: {metrics['winLoss']['perdida']} | En proceso: {metrics['winLoss']['enProceso']}",
        f"- Tasa de cierre: {metrics['closeRate']}%",
        f"- SLA A ({sla['A']['slaLimit']} días): {sla['A']['ok']} cumplidas / {sla['A']['fail']} fuera de tiempo (promedio {sla['A']['avgDays']} días)",
        f"- SLA AA ({sla['AA']['slaLimit']} días): {sla['AA']['ok']} cumplidas / {sla['AA']['fail']} fuera de tiempo (promedio {sla['AA']['avgDays']} días)",
        f"- SLA AAA ({sla['AAA']['slaLimit']} días): {sla['AAA']['ok']} cumplidas / {sla['AAA']['fail']} fuera de tiempo (promedio {sla['AAA']['avgDays']} días)",
        "",
        "SLAs INCUMPLIDOS:",
        fallas,
        "",
        "Entrega el texto en un solo bloque, sin listas ni markdown, y cierra siempre con una "
        "recomendación operativa concreta y accionable para el equipo de ventas.",
    ])


# ----------------------------------------------------------------------
# MÉTRICAS DE PRODUCTIVIDAD DE TRACKERS
# ----------------------------------------------------------------------
# Port de `apiFetchTrackerProductivityMetrics`. La versión que había en
# `api/main.py` era una cuenta de activas/cerradas por persona escrita en línea
# en el endpoint; le faltaban el cumplimiento de fechas, las restricciones, los
# riesgos, las prioridades y el desglose por departamento, que son las métricas
# de las que dependen las tres reglas de alerta.

PRIORIDADES = ("ALTA", "MEDIA", "BAJA")
RIESGO_IRRELEVANTE = {"", "BAJO", "NINGUNO", "NO"}


def _duracion_de_tarea(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Días entre el alta y la entrega, y si llegó tarde.

    Tarde = se entregó después de la fecha comprometida. Sin fecha comprometida
    no se puede juzgar, así que cuenta como a tiempo — igual que el original, que
    solo marca `isLate` cuando hay con qué comparar.
    """
    alta = parse_sheet_date(pick_task_value(row, ["FECHA", "FECHA ALTA", "ALTA", "F. INICIO"]))
    compromiso = parse_sheet_date(pick_task_value(
        row, ["FECHA_RESPUESTA", "FECHA RESPUESTA", "FEC. EST. FIN",
              "FECHA ESTIMADA DE FIN", "F. ENTREGA", "FECHA ENTREGA"]))
    entrega = parse_sheet_date(pick_task_value(
        row, ["FECHA_CIERRE", "FECHA CIERRE", "F. ENTREGA", "FECHA ENTREGA"])) or compromiso

    dias = 0.0
    if alta and entrega:
        dias = max((entrega - alta).days, 0)

    tarde = bool(compromiso and entrega and entrega.date() > compromiso.date())
    return {"dias": dias, "tarde": tarde}


def compute_productivity_metrics(por_persona: Dict[str, List[Dict[str, Any]]],
                                 departamento_de: Optional[Callable[[str], str]] = None,
                                 month: Optional[int] = None,
                                 year: Optional[int] = None) -> Dict[str, Any]:
    """
    Métricas de productividad del periodo.

    `por_persona` es {nombre: [tareas cerradas del periodo]}. Se recibe ya
    filtrado para que esta función sea pura y probable sin base de datos.
    """
    total = 0
    a_tiempo = 0
    tarde = 0
    dias_totales = 0.0
    con_duracion = 0
    con_restricciones = 0
    con_riesgos = 0
    prioridades = {"ALTA": 0, "MEDIA": 0, "BAJA": 0, "SIN_PRIORIDAD": 0}
    por_depto: Dict[str, Dict[str, int]] = {}
    por_colab: Dict[str, Dict[str, Any]] = {}

    for persona, tareas in (por_persona or {}).items():
        depto = (departamento_de(persona) if departamento_de else "") or "SIN DEPARTAMENTO"
        for row in tareas:
            total += 1
            duracion = _duracion_de_tarea(row)
            if duracion["tarde"]:
                tarde += 1
            else:
                a_tiempo += 1
            if duracion["dias"] > 0:
                dias_totales += duracion["dias"]
                con_duracion += 1

            if str(pick_task_value(row, ["RESTRICCIONES"]) or "").strip():
                con_restricciones += 1

            riesgo = str(pick_task_value(row, ["RIESGOS", "RIESGO"]) or "").strip().upper()
            if riesgo not in RIESGO_IRRELEVANTE:
                con_riesgos += 1

            prio = str(pick_task_value(row, ["PRIORIDAD"]) or "").strip().upper()
            prioridades[prio if prio in PRIORIDADES else "SIN_PRIORIDAD"] += 1

            d = por_depto.setdefault(depto, {"count": 0, "late": 0, "onTime": 0})
            d["count"] += 1
            d["late" if duracion["tarde"] else "onTime"] += 1

            c = por_colab.setdefault(persona, {
                "name": persona, "dept": depto, "count": 0, "late": 0, "onTime": 0,
                "_dias": 0.0, "_conDuracion": 0,
            })
            c["count"] += 1
            c["late" if duracion["tarde"] else "onTime"] += 1
            if duracion["dias"] > 0:
                c["_dias"] += duracion["dias"]
                c["_conDuracion"] += 1

    def pct(parte: int, entero: int) -> int:
        return round((parte / entero) * 100) if entero else 0

    colaboradores = sorted(por_colab.values(), key=lambda c: c["count"], reverse=True)
    for c in colaboradores:
        c["avgDays"] = round(c.pop("_dias") / c["_conDuracion"], 1) if c["_conDuracion"] else 0
        c.pop("_conDuracion")
        c["onTimePct"] = pct(c["onTime"], c["count"])

    return {
        "totalTasks": total,
        "onTimeTasks": a_tiempo,
        "lateTasks": tarde,
        "onTimePct": pct(a_tiempo, total),
        "avgDurationDays": round(dias_totales / con_duracion, 1) if con_duracion else 0,
        "tasksWithRestrictions": con_restricciones,
        "restrictionsPct": pct(con_restricciones, total),
        "tasksWithRisks": con_riesgos,
        "risksPct": pct(con_riesgos, total),
        "priorityStats": prioridades,
        "byCollabArr": colaboradores,
        "byDeptArr": sorted(
            [{"dept": k, "count": v["count"]} for k, v in por_depto.items()],
            key=lambda d: d["count"], reverse=True),
        "month": month,
        "year": year,
    }


def productivity_alerts(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Las tres reglas de alerta de `runTrackerProductivityAgent`, con sus umbrales
    exactos: <80% a tiempo, >20% con restricciones, y el colaborador de mayor
    volumen por debajo del 50% con al menos 5 tareas.
    """
    alertas: List[Dict[str, Any]] = []

    if metrics.get("totalTasks", 0) > 0 and metrics.get("onTimePct", 0) < 80:
        alertas.append({
            "type": "ENTREGAS_ATRASADAS", "severity": "ALTA", "icon": "🔴",
            "mensaje": f"Porcentaje de entregas a tiempo crítico: {metrics['onTimePct']}%",
        })

    if metrics.get("restrictionsPct", 0) > 20:
        alertas.append({
            "type": "ALTAS_RESTRICCIONES", "severity": "MEDIA", "icon": "🟡",
            "mensaje": ("Alta proporción de tareas con restricciones: "
                        f"{metrics['restrictionsPct']}%"),
        })

    top = (metrics.get("byCollabArr") or [None])[0]
    if top and top.get("onTimePct", 0) < 50 and top.get("count", 0) >= 5:
        alertas.append({
            "type": "PRODUCTIVIDAD_COLAB", "severity": "ALTA", "icon": "🔴",
            "mensaje": (f"Colaborador {top['name']} tiene {top['onTimePct']}% a tiempo "
                        f"de {top['count']} tareas."),
        })

    return alertas


def build_productivity_prompt(metrics: Dict[str, Any], month_name: str) -> str:
    """Mismo prompt que el original, para que el reporte lea igual."""
    import json as _json

    resumen = _json.dumps({
        "volumen_total": metrics.get("totalTasks"),
        "a_tiempo_pct": metrics.get("onTimePct"),
        "atrasadas": metrics.get("lateTasks"),
        "promedio_dias_resolucion": metrics.get("avgDurationDays"),
        "porcentaje_restricciones": metrics.get("restrictionsPct"),
        "porcentaje_riesgos": metrics.get("risksPct"),
        "prioridades": metrics.get("priorityStats"),
        "top_colaboradores": [
            {"nombre": c["name"], "volumen": c["count"],
             "a_tiempo_pct": c["onTimePct"], "promedio_dias": c["avgDays"]}
            for c in (metrics.get("byCollabArr") or [])[:3]
        ],
    }, indent=2, ensure_ascii=False)

    return (
        "Eres un Analista de Productividad y Operaciones Senior. Analiza las "
        f"siguientes métricas del equipo correspondientes al mes de {month_name}. "
        "Tu objetivo es redactar un reporte ejecutivo muy conciso (máximo 180 "
        "palabras) en español. Debes destacar el porcentaje de tareas entregadas "
        "a tiempo, identificar si hay un cuello de botella con las prioridades "
        "altas o restricciones, y mencionar al colaborador o departamento más "
        "productivo. Termina siempre con UNA recomendación operativa concreta "
        f"para mejorar los tiempos de entrega.\n\nMétricas:\n{resumen}"
    )
