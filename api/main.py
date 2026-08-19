from fastapi import FastAPI, HTTPException, Body, Query, Header
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import re
import secrets
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, File, Form

# El contrato de `geo_prospectos`. Se importa arriba y no junto a la ruta porque
# FastAPI necesita el modelo resuelto al decorar, y porque un import a media
# altura sumaría un E402 al conteo de `ruff`, que es una puerta (§4).
# Solo depende de `pydantic`, que ya es requisito para que la app arranque.
from backend.schemas.geo_prospecto import ProspectoWrite

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
from api.services.asignacion import tabla_de_cotizaciones
from api.services.work_order import process_and_save_work_order, get_next_sequence

# MCP Server
#
# Import protegido: `mcp.server.fastmcp` desapareció en la versión 2 del SDK, y
# con el import al desnudo un cambio de versión del paquete tumbaba toda la API
# en el arranque en vez de dejar sin montar sólo `/mcp`.
try:
    from api.mcp_server import mcp
except Exception as exc:  # pragma: no cover - depende del entorno
    mcp = None
    print(f"Servidor MCP no disponible: {exc}")

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
if mcp is not None:
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

class Plano2DRequest(BaseModel):
    descripcion: str


@app.post("/api/plano_2d")
def api_generar_plano_2d(req: Plano2DRequest):
    """
    Plano 2D y escena 3D de una descripción, desde una sola geometría.

    Sustituye la llamada que el frontend hacía a `image.pollinations.ai`: aquel
    servicio devolvía una ilustración con medidas inventadas y sin relación con
    el modelo del editor 3D. Aquí las dos vistas salen del mismo cálculo.

    No lanza 500 cuando no se puede: devuelve `success: false` con el motivo,
    porque "escribe las medidas como 8 x 5 m" es una instrucción accionable y un
    error genérico no lo es.
    """
    from api.services import plano as servicio_plano

    return servicio_plano.generar_plano(
        req.descripcion, llm=servicio_plano.llm_disponible())


# ======================================================================
# PROSPECCIÓN GEOESPACIAL — /api/geo
# ======================================================================
# El catálogo del DENUE (20,957 establecimientos de la cadena de valor de la
# construcción en CDMX) vive en un SQLite de solo lectura dentro del bundle y se
# consulta con el `sqlite3` de la biblioteca estándar. Leerlo desde el Parquet
# exigiría pandas + pyarrow + numpy: 251 MB desempaquetadas, que rebasan solas
# el límite de 250 MB de una función serverless. Por eso `api/requirements.txt`
# no crece con este módulo.
#
# Estas dos rutas son de lectura pura sobre dato público del INEGI. Lo que la
# empresa genere encima —prospecto contactado, asignado, cotizado— es otra cosa
# y va a Supabase por el motor que ya existe.

@app.get("/api/geo/catalogo")
def api_geo_catalogo():
    """
    Las alcaldías y los giros que existen en el catálogo, para poblar los combos.

    Salen del propio artefacto, no de una lista escrita a mano: el día que el
    INEGI publique un giro nuevo, el combo lo tiene al regenerar el SQLite.
    """
    from api.services import denue_repo, prospeccion

    return prospeccion.catalogo(denue_repo.repositorio_disponible())


@app.get("/api/geo/establecimientos")
def api_geo_establecimientos(
    alcaldia: Optional[str] = None,
    giros: Optional[List[str]] = Query(None),
    personal_min: Optional[int] = None,
    solo_con_contacto: bool = False,
    bbox: Optional[str] = None,
    limite: Optional[int] = None,
    desplazamiento: int = 0,
):
    """
    Los establecimientos que pasan los filtros, en las 10 columnas del mapa.

    `bbox` es `lat_min,lon_min,lat_max,lon_max` — el orden del INEGI y de
    Leaflet, no el de GeoJSON. Devuelve `total` (los que cumplen) y `mostrados`
    (los que caben en el límite) por separado: el notebook cortaba en 2,000
    marcadores sin avisar y nadie sabía si estaba viendo todo.

    No lanza 500 con parámetros basura: devuelve `success: false` con el motivo,
    mismo criterio que `/api/plano_2d`.
    """
    from api.services import denue_repo, prospeccion

    return prospeccion.establecimientos(
        denue_repo.repositorio_disponible(),
        alcaldia=alcaldia,
        giros=giros,
        personal_min=personal_min,
        solo_con_contacto=solo_con_contacto,
        bbox=bbox,
        limite=limite,
        desplazamiento=desplazamiento,
    )


# --- El puente con el negocio (Fase 5) ---------------------------------
#
# Hasta aquí el módulo es un mapa: enseña 20,957 establecimientos y no deja
# rastro de nada. Lo que sigue es lo que lo convierte en parte de la
# plataforma — marcar un prospecto, exportar una selección y pedir cotización
# por el mismo canal de correo que ya usan los agentes.
#
# El dato del INEGI y el de la empresa NO se mezclan (plan §4, decisión D2): el
# catálogo sigue siendo un SQLite de solo lectura y lo mutable va a Supabase por
# el `DataEngine` que ya existe.

class GeoSeleccionRequest(BaseModel):
    """El polígono que dibujó el usuario, más los filtros vigentes del panel."""

    poligono: Dict[str, Any]
    personal_min: Optional[int] = None
    solo_con_contacto: bool = False
    # `json` para pintar, `csv`/`xlsx` para llevárselo a compras.
    formato: str = "json"


class GeoCotizacionRequest(BaseModel):
    """La solicitud de cotización ya redactada, lista para salir por correo."""

    establecimiento_id: str
    destinatario: str = ""
    asunto: str = "Solicitud de cotización"
    mensaje: str = ""
    nombre: str = ""


_MEDIOS_DE_EXPORTACION = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
}


@app.post("/api/geo/prospecto")
def api_geo_prospecto(req: ProspectoWrite):
    """
    Marca el estado comercial de un establecimiento del DENUE.

    Alta y cambio son la misma llamada: un establecimiento tiene un solo estado
    comercial, así que el repositorio hace upsert por `denue_id`. `estado` sale
    de { NUEVO, CONTACTADO, COTIZANDO, DESCARTADO } y un valor desconocido se
    rechaza en vez de degradar a `NUEVO` — degradarlo diría que a este negocio
    nunca lo contactó nadie, borrando trabajo que alguien ya hizo.

    Si no hay motor de datos configurado degrada con `success: false` y el
    motivo, igual que `/api/plano_2d`. La tabla la crea el dueño con
    `docs/DDL_PENDIENTE.sql` §8.
    """
    from backend.core.engine import construir_engine
    from backend.core.errors import BackendError, SinMotorConfigurado
    from backend.repositories.geo_prospectos import GeoProspectoRepository

    try:
        repositorio = GeoProspectoRepository(construir_engine())
        guardado = repositorio.guardar(req)
    except SinMotorConfigurado as exc:
        return {"success": False, "message": str(exc)}
    except BackendError as exc:
        return {"success": False, "message": str(exc)}
    return {"success": True, "prospecto": guardado.model_dump(mode="json")}


@app.post("/api/geo/seleccion")
def api_geo_seleccion(req: GeoSeleccionRequest):
    """
    Los establecimientos dentro del polígono dibujado, para verlos o exportarlos.

    `formato=csv` y `formato=xlsx` devuelven el archivo; cualquier otro valor
    devuelve JSON. La exportación se arma con la biblioteca estándar
    (`api/services/exportacion.py`): meter `openpyxl` al runtime es justo lo que
    todo este diseño evita.
    """
    from api.services import denue_repo, exportacion, prospeccion

    resultado = prospeccion.seleccion(
        denue_repo.repositorio_disponible(), req.poligono,
        personal_min=req.personal_min, solo_con_contacto=req.solo_con_contacto)

    medio = _MEDIOS_DE_EXPORTACION.get(str(req.formato).lower().strip())
    if medio is None or not resultado.get("success"):
        return resultado

    tipo, extension = medio
    generar = exportacion.a_csv if extension == "csv" else exportacion.a_xlsx
    return Response(
        content=generar(resultado["items"]), media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="prospectos.{extension}"'})


@app.post("/api/geo/solicitar_cotizacion")
def api_geo_solicitar_cotizacion(req: GeoCotizacionRequest):
    """
    Manda la solicitud de cotización por el canal SMTP que ya existe.

    ⚠️ Hoy **no manda nada**: falta el aviso de identificación y baja que exige
    la LFPDPPP para contacto comercial, y es una decisión del dueño (plan §11,
    punto 5). La respuesta trae `motivo: "aviso_legal_pendiente"` y el correo ya
    redactado, para copiarlo y mandarlo a mano mientras tanto.
    """
    from api.services import prospeccion_correo

    return prospeccion_correo.solicitar_cotizacion(
        req.nombre or req.establecimiento_id, req.destinatario, req.asunto, req.mensaje)


class LoginRequest(BaseModel):
    username: str
    password: str

class SavePPCRequest(BaseModel):
    payload: List[Dict[str, Any]]
    activeUser: str

def _ve_prospeccion(role: str, cuenta: str) -> bool:
    """
    Si esta cuenta ve el módulo de Prospección.

    Misma forma que `puede_gestionar_tickets`: una bandera aditiva del perfil,
    más los dos roles que la tienen por el rol mismo. Vive fuera de
    `api_get_system_config` por la misma razón que `_con_prospeccion` —esa
    función ya está en complejidad C (16), es deuda inventariada
    (RESTRICCIONES_EXTREMAS.md §4) y un `or` más la habría subido a 17—.
    """
    return bool(organigrama.perfil(cuenta).get("prospeccion")) or role in (
        "ADMIN", "ADMIN_CONTROL",
    )


def _con_prospeccion(modulos: List[Dict[str, Any]], geo_module: Dict[str, Any],
                     visible: bool) -> List[Dict[str, Any]]:
    """
    Agrega el módulo de Prospección a `modulos` si esta cuenta lo ve.

    Vive fuera de `api_get_system_config` por una razón de puerta, no de
    estética: esa función ya está en complejidad C (16), es deuda inventariada
    (RESTRICCIONES_EXTREMAS.md §4) y la regla dice que una función existente
    sale igual o mejor, nunca peor. Con la decisión aquí, las cuatro ramas de
    rol la llaman sin añadir una sola bifurcación al contador.
    """
    return [*modulos, geo_module] if visible else list(modulos)


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
    # `sales` marca a quien tiene tabla `<NOMBRE> (VENTAS)`, que es la única
    # gente a la que se le puede asignar una cotización. La vista lo usa para no
    # ofrecer como destino a alguien sin tabla: si no hay a dónde mandarlo, no
    # debe aparecer en la lista. La fuente es `asignacion.VENDEDORES_CON_TABLA`,
    # declarada en un solo sitio, para que el frontend no repita la lista.
    full_directory = [
        {**persona, "sales": bool(tabla_de_cotizaciones(persona.get("name")))}
        for persona in full_directory
    ]
    cuenta = organigrama.clave_usuario(username)

    # `soporte` es una bandera aditiva, igual que `seller`: no reemplaza el
    # rol de nadie, solo agrega la vista de tickets encima del que ya tenga.
    # ADMIN/ADMIN_CONTROL la ven sin necesitar la bandera explícita (decisión
    # del dueño, 2026-08-13): quien ya administra el directorio no debería
    # tener que pedir un permiso aparte para ver los bugs reportados.
    puede_gestionar_tickets = bool(organigrama.perfil(cuenta).get("soporte")) or role in (
        "ADMIN", "ADMIN_CONTROL",
    )

    ppc_module_master = { "id": "PPC_MASTER", "label": "PPC Maestro", "icon": "fa-tasks", "color": "#fd7e14", "type": "ppc_native" }
    # JESUS_CANTU ve el módulo PPC con otro nombre. Es una etiqueta, no un
    # permiso, y por eso se resuelve aquí y no en la rama de rol.
    if cuenta == "JESUS_CANTU":
        ppc_module_master = { **ppc_module_master, "label": "INTERDICIPLINARIA" }

    ppc_module_weekly = { "id": "WEEKLY_PLAN", "label": "Planeación Semanal", "icon": "fa-calendar-alt", "color": "#6f42c1", "type": "weekly_plan_view" }
    kpi_module = { "id": "KPI_DASHBOARD", "label": "KPI Performance", "icon": "fa-chart-line", "color": "#d63384", "type": "kpi_dashboard_view" }
    wo_module = { "id": "WORK_ORDER_FORM", "label": "Pre Work Order", "icon": "fa-clipboard-list", "color": "#fd7e14", "type": "work_order_form" }
    # Prospección geoespacial sobre el DENUE. `prospeccion` es una bandera
    # aditiva en el perfil, igual que `soporte`: no reemplaza el rol de nadie,
    # solo agrega el mapa encima del que ya tenga. ADMIN y ADMIN_CONTROL lo ven
    # sin necesitar la bandera; el resto del personal solo con ella.
    #
    # Son 20,957 nombres con teléfono y correo: no es un dato que deba ver todo
    # el personal por defecto, y una bandera por cuenta es más fácil de auditar
    # —y de revocar— que una regla derivada del departamento.
    geo_module = { "id": "PROSPECCION_GEO", "label": "Prospección", "icon": "fa-map-marked-alt",
                   "color": "#20c997", "type": "geo_prospect_view" }
    ve_prospeccion = _ve_prospeccion(role, cuenta)
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
            "canManageTickets": puede_gestionar_tickets,
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
            "canManageTickets": puede_gestionar_tickets,
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
            # Solo con la bandera `prospeccion` en el perfil. El STAFF_USER
            # genérico no la trae y no tiene por qué llevarse el directorio.
            "specialModules": _con_prospeccion(modulos, geo_module, ve_prospeccion),
            "accessProjects": False,
            "canSeeBancoJuntas": False,
            "canManageTickets": puede_gestionar_tickets,
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
            "canManageTickets": puede_gestionar_tickets,
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
            "canManageTickets": puede_gestionar_tickets,
        }

    if role == 'ADMIN_CONTROL':
        return {
            "departments": ALL_DEPTS,
            "allDepartments": ALL_DEPTS,
            "staff": full_directory,
            "directory": full_directory,
            "specialModules": _con_prospeccion([
                { "id": "PPC_DINAMICO", "label": "Tracker", "icon": "fa-layer-group", "color": "#e83e8c", "type": "ppc_dynamic_view" },
                *ppc_modules,
                { "id": "MIRROR_TONITA", "label": "Monitor Toñita", "icon": "fa-eye", "color": "#0dcaf0", "type": "mirror_staff", "target": "ANTONIA_VENTAS" },
                { "id": "ADMIN_TRACKER", "label": "Control", "icon": "fa-clipboard-list", "color": "#6f42c1", "type": "mirror_staff", "target": "ADMINISTRADOR" },
            ], geo_module, ve_prospeccion),
            "accessProjects": True,
            "canSeeBancoJuntas": True,
            "canManageTickets": puede_gestionar_tickets,
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
        default_modules = _con_prospeccion(default_modules, geo_module, ve_prospeccion)

    return {
        "departments": ALL_DEPTS,
        "allDepartments": ALL_DEPTS,
        "staff": full_directory,
        "directory": full_directory,
        "specialModules": default_modules,
        "accessProjects": True,
        "canSeeBancoJuntas": True,
        "canManageTickets": puede_gestionar_tickets,
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
    user_found = None

    # 1) `profiles` es la tabla de cuentas del esquema relacional. Va primero
    #    porque es la única fuente que existe: la hoja `USERS` nunca se migró
    #    (`sheets.py` lo dice explícito) y por eso, hasta ahora, nadie podía
    #    entrar salvo con DEV_LOGIN_USERS.
    perfil_valido = organigrama.validar_credenciales(username_key, creds.password)
    if perfil_valido:
        user_found = {
            "success": True,
            "role": perfil_valido["role"],
            "name": perfil_valido["label"],
            "username": username_key,
        }

    # 2) Hoja/tabla `USERS`: se conserva por si alguna instalación la tiene.
    values = None if user_found else gs_manager.get_sheet_values("USERS")
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

    # 3) Login de desarrollo por entorno.
    #
    # NOTA: aquí vivía un diccionario de usuarios con contraseñas reales y
    # funcionales escritas en el fuente. Se eliminó: unas credenciales
    # versionadas en el repo son un riesgo, no un modo de prueba.
    #
    # La condición incluye `is_mock`, que es True cuando no existe
    # `credentials.json` —el archivo de servicio de *Google Sheets*—. Es una
    # dependencia desafortunada: si alguien coloca ese archivo para exportar a
    # Sheets, este respaldo se apaga. Ya no es crítico porque `profiles` cubre el
    # caso real, pero conviene saberlo mientras siga aquí.
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

# --- Protección de /api/data -------------------------------------------
# Nombres cuyo contenido no sale por el endpoint genérico de lectura. La
# comparación normaliza mayúsculas, espacios y guiones para que `Profiles`,
# `PROFILES` y `pro files` caigan igual.
_TABLAS_SENSIBLES = {"PROFILES", "USERS", "USUARIOS", "AUTH", "CREDENCIALES", "CREDENTIALS"}


def _clave_tabla(nombre: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(nombre or "").upper())


def _es_tabla_sensible(nombre: Any) -> bool:
    clave = _clave_tabla(nombre)
    return any(clave == _clave_tabla(t) for t in _TABLAS_SENSIBLES)


def _sin_columnas_de_credencial(values):
    """
    Quita las columnas que parecen contraseña de una matriz de hoja.

    Es la segunda barrera: aunque una tabla no esté en la lista de nombres, si
    trae una columna de credenciales no se publica. Vale también para el caso en
    que alguien añada mañana una columna `password` a una tabla existente.
    """
    if not values or not values[0]:
        return values

    prohibidas = {c.upper() for c in organigrama.columnas_de_credencial()}
    indices = [i for i, h in enumerate(values[0])
               if str(h or "").strip().upper() in prohibidas]
    if not indices:
        return values

    descartar = set(indices)
    return [[c for i, c in enumerate(fila) if i not in descartar] for fila in values]


@app.get("/api/data")
def get_data(sheet: str = Query(..., description="Name of the sheet to fetch")):
    # Este endpoint acepta cualquier nombre de tabla y no exige sesión, así que
    # era una lectura universal de la base: `?sheet=USERS` devolvía la tabla de
    # usuarios completa. Al poblar `profiles` con las 41 cuentas, eso pasaría a
    # entregar las contraseñas a cualquiera que supiera la URL.
    #
    # Se cierra por dos vías, porque la lista de nombres sola es burlable —la
    # misma tabla puede alcanzarse por un alias o por otra capitalización— y el
    # filtro de columnas sola dejaría pasar tablas sensibles por otros motivos:
    if _es_tabla_sensible(sheet):
        raise HTTPException(status_code=403, detail="Esa tabla no se expone por este endpoint.")

    values = gs_manager.get_sheet_values(sheet)
    values = _sin_columnas_de_credencial(values)

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
    # La key viaja en la petición porque el servidor no tiene dónde guardarla:
    # cada invocación en Vercel es un proceso nuevo y `os.environ` no sobrevive
    # de una petición a la siguiente. Ver `tracker_store.save_gemini_key`.
    # Si no viene, se usa `GEMINI_API_KEY` del entorno del despliegue.
    geminiKey: Optional[str] = None


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
    return tracker_store.run_quote_metrics_agent(req.month, req.year, req.geminiKey)


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
    """
    runTrackerProductivityAgent: metricas reales, las 3 reglas de alerta,
    resumen de IA y correo.

    Antes esto era un conteo de activas/cerradas escrito en linea aqui, sin
    cumplimiento de fechas, restricciones, riesgos ni prioridades — y por tanto
    sin las tres reglas, que dependen de esas metricas. Ahora delega en
    `tracker_store`, que usa `tracker_rules.compute_productivity_metrics`.
    """
    return tracker_store.run_tracker_productivity_agent(req.month, req.year)


@app.get("/api/legacy/trackerProductivityMetrics")
def api_legacy_tracker_productivity_metrics(
    month: Optional[int] = Query(None), year: Optional[int] = Query(None)
):
    """apiFetchTrackerProductivityMetrics: solo las metricas, sin correo."""
    return tracker_store.fetch_tracker_productivity_metrics(month, year)


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
# PROYECTOS / CASCADA
# ======================================================================
# Las tablas `sites` y `projects` existían desde la migración pero no tenían
# endpoint: el frontend mostraba las vistas PROJECTS y PROJECT_TASKS_VIEW
# alimentadas con listas vacías.


class SiteRequest(BaseModel):
    name: str
    client: str = ""
    type: Optional[str] = None
    createdBy: Optional[str] = None


class SubProjectRequest(BaseModel):
    parentId: str
    name: str
    type: Optional[str] = None
    createdBy: Optional[str] = None


class ProjectTaskRequest(BaseModel):
    task: Dict[str, Any]
    projectName: str
    username: Optional[str] = ""


def _repo_proyectos():
    from backend.core.engine import construir_engine
    from backend.repositories.proyectos import RepositorioProyectos

    return RepositorioProyectos(construir_engine())


def _auditar_proyecto(username: Optional[str], accion: str, detalle: str) -> None:
    """
    `registrarLog` del original. No puede tumbar la operación que audita.
    """
    try:
        from backend.services import auditoria

        auditoria.registrar(username or "ANONIMO", accion, detalle)
    except Exception as exc:  # noqa: BLE001
        print(f"[proyectos] No se pudo auditar: {exc}")


@app.get("/api/legacy/cascadeTree")
def api_legacy_cascade_tree():
    """apiFetchCascadeTree: árbol sitios -> subproyectos."""
    from backend.repositories.proyectos import ErrorDeLectura

    try:
        return {"success": True, "data": _repo_proyectos().arbol()}
    except ErrorDeLectura as exc:
        # Error visible en vez de un árbol vacío: una vista vacía es
        # indistinguible de "no hay proyectos" y esconde el fallo.
        return {"success": False, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Error leyendo proyectos: {exc}"}


@app.post("/api/legacy/saveSite")
def api_legacy_save_site(req: SiteRequest):
    """apiSaveSite."""
    try:
        res = _repo_proyectos().crear_sitio(req.name, req.client, req.type, req.createdBy)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"No se pudo crear el sitio: {exc}"}
    if res.get("success"):
        _auditar_proyecto(req.createdBy, "NUEVO SITIO", f"Sitio: {req.name} ({res['id']})")
    return res


@app.post("/api/legacy/saveSubProject")
def api_legacy_save_subproject(req: SubProjectRequest):
    """apiSaveSubProject."""
    try:
        res = _repo_proyectos().crear_subproyecto(req.parentId, req.name, req.type, req.createdBy)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"No se pudo crear el subproyecto: {exc}"}
    if res.get("success"):
        _auditar_proyecto(req.createdBy, "NUEVO SUBPROYECTO",
                          f"Subproyecto: {req.name} ({res['id']})")
    return res


@app.get("/api/legacy/projectTasks")
def api_legacy_project_tasks(projectName: str = Query(..., description="Nombre del proyecto")):
    """apiFetchProjectTasks. Corrige el ReferenceError del original (ver el servicio)."""
    return tracker_store.fetch_project_tasks(projectName)


@app.post("/api/legacy/saveProjectTask")
def api_legacy_save_project_task(req: ProjectTaskRequest):
    """apiSaveProjectTask."""
    res = tracker_store.save_project_task(req.task, req.projectName, req.username or "")
    if res.get("success"):
        folio = req.task.get("ID") or req.task.get("FOLIO") or ""
        _auditar_proyecto(req.username, "ACTUALIZAR PROYECTO",
                          f"Proyecto: {req.projectName}, ID: {folio}")
    return res


# ======================================================================
# BORRADORES, AGENDA, BANCO Y DIRECTORIO
# ======================================================================


class DraftsRequest(BaseModel):
    drafts: List[Dict[str, Any]] = []


class PersonalEventRequest(BaseModel):
    payload: Dict[str, Any]
    username: Optional[str] = ""


class EmployeeRequest(BaseModel):
    name: str
    dept: str = ""
    type: Optional[str] = "ESTANDAR"


class LogoutRequest(BaseModel):
    username: Optional[str] = ""


@app.get("/api/legacy/drafts")
def api_legacy_drafts():
    """apiFetchDrafts."""
    return tracker_store.fetch_drafts()


@app.post("/api/legacy/syncDrafts")
def api_legacy_sync_drafts(req: DraftsRequest):
    """apiSyncDrafts: la cola se reemplaza entera, no se fusiona."""
    return tracker_store.sync_drafts(req.drafts)


@app.post("/api/legacy/clearDrafts")
def api_legacy_clear_drafts():
    """apiClearDrafts."""
    return tracker_store.clear_drafts()


@app.post("/api/legacy/personalEvent")
def api_legacy_personal_event(req: PersonalEventRequest):
    """apiSavePersonalEvent."""
    return tracker_store.save_personal_event(req.payload, req.username or "")


@app.post("/api/legacy/habitLog")
def api_legacy_habit_log(req: PersonalEventRequest):
    """apiSaveHabitLog. Avisa qué crear si `habits_log` no existe."""
    return tracker_store.save_habit_log(req.payload, req.username or "")


@app.get("/api/legacy/infoBankData")
def api_legacy_info_bank_data(
    year: str = Query(...),
    month: str = Query(...),
    company: str = Query("", description="Cliente"),
    folder: str = Query("", description="Se acepta por compatibilidad; no filtra"),
):
    """apiFetchInfoBankData."""
    return tracker_store.fetch_info_bank_data(year, month, company, folder)


@app.get("/api/legacy/ppcData")
def api_legacy_ppc_data():
    """apiFetchPPCData: las últimas 300 actividades del PPC maestro."""
    return tracker_store.fetch_ppc_data()


@app.get("/api/legacy/combinedCalendar")
def api_legacy_combined_calendar(sheet: str = Query(..., description="Hoja/persona")):
    """apiFetchCombinedCalendarData."""
    return tracker_store.fetch_combined_calendar(sheet)


@app.post("/api/legacy/logout")
def api_legacy_logout(req: LogoutRequest):
    """apiLogout: registra el cierre en system_log."""
    return tracker_store.logout(req.username or "")


@app.post("/api/legacy/addEmployee")
def api_legacy_add_employee(req: EmployeeRequest):
    """apiAddEmployee."""
    return tracker_store.add_employee(req.name, req.dept, req.type)


@app.post("/api/legacy/deleteEmployee")
def api_legacy_delete_employee(req: EmployeeRequest):
    """apiDeleteEmployee."""
    return tracker_store.delete_employee(req.name)


# ======================================================================
# ARCHIVOS (Supabase Storage) Y TAREAS PROGRAMADAS
# ======================================================================


class UploadRequest(BaseModel):
    data: str
    type: Optional[str] = None
    name: Optional[str] = None
    # Con cliente, el archivo cae en la estructura del banco: AÑO/MES/CLIENTE.
    client: Optional[str] = None
    date: Optional[str] = None


class ArchiveRequest(BaseModel):
    fileUrl: str
    client: str
    date: Optional[str] = None


@app.post("/api/legacy/upload")
def api_legacy_upload(req: UploadRequest):
    """uploadFileToDrive, sobre Supabase Storage."""
    from api.services import storage

    return storage.subir(req.data, req.type, req.name, req.client, req.date)


@app.post("/api/legacy/archiveQuote")
def api_legacy_archive_quote(req: ArchiveRequest):
    """
    archiveFile + processQuoteRow: reubica el archivo en AÑO/MES/CLIENTE.

    En Drive era mover el archivo entre carpetas; en Storage es un `move` de la
    clave del objeto.
    """
    from api.services import storage

    return storage.archivar_cotizacion(req.fileUrl, req.client, req.date)


def _cron_autorizado(secreto: Optional[str]) -> bool:
    """
    El cron se dispara desde fuera, asi que el endpoint necesita un secreto.

    Sin `CRON_SECRET` configurado se rechaza: un endpoint que lanza los tres
    agentes y manda correos no puede quedar abierto por omision.
    """
    esperado = os.environ.get("CRON_SECRET", "").strip()
    if not esperado:
        return False
    return secrets.compare_digest(str(secreto or ""), esperado)


@app.post("/api/cron/dailyMetrics")
def api_cron_daily_metrics(x_cron_secret: str = Header("", alias="X-Cron-Secret")):
    """
    autoUpdateQuoteMetrics: el disparador diario de las 07:00.

    En Apps Script era un trigger de tiempo (`setupDailyQuoteMetricsTrigger`).
    En serverless no hay proceso residente que lo sostenga, asi que lo invoca un
    cron externo — ver `.github/workflows/cron-metricas.yml`.
    """
    if not _cron_autorizado(x_cron_secret):
        raise HTTPException(status_code=401, detail="Secreto de cron invalido o no configurado.")
    return tracker_store.auto_update_quote_metrics()


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

try:
    from backend.routers.tickets import router as tickets_v2_router

    app.include_router(tickets_v2_router)
except Exception as exc:
    print(f"Capa de tickets /api/v2 no disponible: {exc}")


# Estáticos del front.
#
# Antes esto era `StaticFiles(directory=".")`: montaba el directorio de trabajo
# entero, así que dependía de desde dónde se arrancara el proceso (en Vercel el
# cwd no es la raíz del repo) y, peor, publicaba todo el árbol —`api/main.py`
# incluido— como archivo descargable. Ahora la raíz se resuelve desde
# `__file__` y sólo se sirven los archivos que el front pide de verdad.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PUBLIC_FILES = {
    "index.html": "text/html; charset=utf-8",
    "api_service.js": "application/javascript",
    "workorder_form.html": "text/html; charset=utf-8",
}


@app.get("/{filename}")
async def serve_public_file(filename: str):
    media_type = _PUBLIC_FILES.get(filename)
    if media_type is None:
        raise HTTPException(status_code=404, detail="File not found")
    path = os.path.join(_REPO_ROOT, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type=media_type)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
