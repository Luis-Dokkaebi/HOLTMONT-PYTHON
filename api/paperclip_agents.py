import os
import json
import math
import re
import secrets
import string
from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field

try:
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import StateGraph, START, END
except ImportError:
    ChatGroq = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

from api.modelos_llm import MODELO_GEMINI, MODELO_GROQ

# --- PYDANTIC SCHEMAS FOR STRUCTURED EXTRACTION ---
class LaborItem(BaseModel):
    category: str = Field(description="Rol o puesto de la persona (Ej. Operario, Ingeniero, Albañil)")
    personnel: str = Field(description="Cantidad de personas requeridas con este rol")
    unit: str = Field(description="Unidad de tiempo a contratar (debe ser: 'hora', 'dia', o 'semana')")
    weeks: str = Field(description="Duración o cantidad de la unidad de tiempo (Ej. 3, 5, 10)")
    salary: str = Field(description="Salario o costo unitario estimado por la unidad de tiempo")

class MaterialItem(BaseModel):
    description: str = Field(description="Descripción clara del material o insumo")
    unit: str = Field(description="Unidad de medida (Ej. pza, bulto, m2, m3, lote)")
    quantity: str = Field(description="Cantidad estimada a utilizar")
    cost: str = Field(description="Costo unitario estimado del material")

class ToolItem(BaseModel):
    description: str = Field(description="Descripción de la herramienta requerida")
    unit: str = Field(description="Unidad de medida (Ej. pza, lote)")
    quantity: str = Field(description="Cantidad estimada")
    cost: str = Field(description="Costo estimado")

class EquipmentItem(BaseModel):
    description: str = Field(description="Descripción del equipo especial, maquinaria o accesorio")
    unit: str = Field(description="Unidad de medida (Ej. hora, dia, unidad)")
    quantity: str = Field(description="Cantidad de equipos")
    days: str = Field(description="Días estimados de uso o renta")
    cost: str = Field(description="Costo unitario o de renta estimado")

class TravelItem(BaseModel):
    concepto: str = Field(description="Concepto del viático (Ej. Hotel, Casetas, Comidas)")
    cantidad: str = Field(description="Cantidad de noches, comidas o viajes")
    costo_unitario: str = Field(description="Costo unitario estimado")

class StructuredAgencyData(BaseModel):
    laborTable: List[LaborItem] = Field(description="Lista estructurada de mano de obra estimada")
    requiredMaterials: List[MaterialItem] = Field(description="Lista estructurada de materiales e insumos estimados")
    toolsRequired: List[ToolItem] = Field(description="Lista de herramientas menores requeridas")
    specialEquipment: List[EquipmentItem] = Field(description="Lista de maquinaria y equipo especial requerido")
    viaticosTable: List[TravelItem] = Field(description="Lista de viáticos requeridos si aplica")


# --- SCHEMAS ESTRUCTURADOS PARA AGENTES DE TEXTO ---
class LevantamientoData(BaseModel):
    """Reporte de levantamiento estructurado (Agente 1)."""
    site_conditions: List[str] = Field(default_factory=list, description="Condiciones del sitio observadas")
    scope: List[str] = Field(default_factory=list, description="Alcance del trabajo a realizar, punto por punto")
    restrictions: List[str] = Field(default_factory=list, description="Restricciones técnicas detectadas")
    missing_info: List[str] = Field(default_factory=list, description="Datos que el cliente debe aclarar (medidas, materiales, plazos ausentes)")


class ConceptItem(BaseModel):
    concept: str = Field(description="Concepto de obra principal")
    unit: str = Field(description="Unidad de medición (m2, m3, pza, lote)")
    quantity: str = Field(description="Cantidad estimada (> 0)")

class CalculoMaterial(BaseModel):
    description: str = Field(description="Material o insumo")
    unit: str = Field(description="Unidad (pza, bulto, m2, m3, lote)")
    quantity: str = Field(description="Cantidad estimada (> 0)")

class CalculoLabor(BaseModel):
    role: str = Field(description="Rol o puesto (Albañil, Ingeniero, Operario)")
    people: str = Field(description="Número de personas")
    duration: str = Field(description="Duración en la unidad indicada")
    unit: str = Field(description="Unidad de tiempo: hora, dia o semana")

class CalculoEquipment(BaseModel):
    description: str = Field(description="Maquinaria o equipo especial")
    quantity: str = Field(description="Cantidad de equipos")

class CalculoData(BaseModel):
    """Requerimientos técnicos estructurados (Agente 2)."""
    concepts: List[ConceptItem] = Field(default_factory=list, description="Catálogo de conceptos principales")
    materials: List[CalculoMaterial] = Field(default_factory=list, description="Materiales con cantidades")
    labor: List[CalculoLabor] = Field(default_factory=list, description="Mano de obra requerida")
    equipment: List[CalculoEquipment] = Field(default_factory=list, description="Maquinaria y equipo especial")


class PrecioItem(BaseModel):
    category: str = Field(description="Categoría: material, mano_obra, herramienta o equipo")
    description: str = Field(description="Descripción del concepto")
    unit: str = Field(description="Unidad de medida")
    quantity: str = Field(description="Cantidad (> 0)")
    unit_price: str = Field(description="Precio unitario estimado de mercado (> 0). NUNCA 0 ni vacío")

class PreciosData(BaseModel):
    """Precios unitarios estructurados (Agente 3). Totales se calculan en código."""
    currency: str = Field(default="MXN", description="Moneda de la estimación")
    items: List[PrecioItem] = Field(default_factory=list, description="Conceptos con precio unitario")


class PreciosCritique(BaseModel):
    """Veredicto del Agente Evaluador sobre el presupuesto (cálculo + precios)."""
    is_approved: bool = Field(description="True si el presupuesto está completo, coherente y con precios de mercado razonables")
    critique: str = Field(description="Qué corregir: conceptos del cálculo sin precio, precios fuera de rango, unidades incoherentes o ítems faltantes. Vacío si se aprueba")


# --- HELPERS COMPARTIDOS ---
def _to_float(value, default: float = 0.0) -> float:
    """Parse precio/cantidad textual a float de forma segura (ignora $, comas, unidades)."""
    if value is None:
        return default
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
        return float(cleaned) if cleaned not in ("", "-", ".", "-.", "--") else default
    except (ValueError, TypeError):
        return default


def _invoke_structured(llm, schema, prompt, inputs, attempts: int = 2):
    """Invoca structured output con reintentos. Lanza la última excepción si todo falla."""
    structured_llm = llm.with_structured_output(schema)
    chain = prompt | structured_llm
    last_err = None
    for _ in range(max(1, attempts)):
        try:
            return chain.invoke(inputs)
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise last_err if last_err else RuntimeError("structured invoke failed")


# Máximo de revisiones del presupuesto en el loop de reflexión (acota costo/tiempo).
MAX_PRECIOS_REVISIONS = 1


# --- STATE DEFINITION ---
class PaperclipState(TypedDict):
    user_request: str
    levantamiento_data: str
    architect_data: str
    calculo_data: str
    precios_data: str
    structured_data: str
    # De dónde salió el modelo 3D y qué avisar si es un supuesto. `architect_node`
    # ya los escribía sin declararlos: LangGraph 1.2 descarta en silencio lo
    # escrito a un canal que el esquema no nombra, así que el aviso «este plano
    # es una habitación de ejemplo, no la del proyecto» nunca salía del grafo.
    architect_origen: str
    architect_aviso: str
    # Lo estructurado se conserva además del texto: el integrador arma las
    # tablas con estos datos y no volviendo a pedirle a un LLM que relea su
    # propia prosa.
    calculo_struct: str
    precios_struct: str
    estimacion_origen: str
    # Loop de reflexión sobre el presupuesto:
    precios_critique: str
    precios_approved: bool
    precios_revision: int

# --- NODES ---
def _bullets(items, empty: str) -> str:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


def _levantamiento_to_text(data: LevantamientoData) -> str:
    """Serializa el levantamiento estructurado a markdown legible para nodos siguientes."""
    secciones = [
        "## Condiciones del Sitio",
        _bullets(data.site_conditions, "Sin condiciones especiales reportadas."),
        "\n## Alcance del Trabajo",
        _bullets(data.scope, "Alcance no especificado por el cliente."),
        "\n## Restricciones Técnicas",
        _bullets(data.restrictions, "Sin restricciones detectadas."),
        "\n## Información Faltante (requiere aclaración del cliente)",
        _bullets(data.missing_info, "Ninguna; información suficiente para cotizar."),
    ]
    return "\n".join(secciones)


def levantamiento_node(state: PaperclipState, llm) -> dict:
    """Agente 1: Levantamiento. Extrae el alcance y condiciones del sitio (estructurado)."""
    print("--- [Agente de Levantamiento] Analizando requerimientos ---")

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Eres un Ingeniero Topógrafo y Residente de Obra experto. Analiza la solicitud y extrae "
         "de forma estructurada y separada: condiciones del sitio, alcance del trabajo (punto por punto), "
         "restricciones técnicas e información faltante. En missing_info incluye SOLO datos que el cliente "
         "debe aclarar (medidas, materiales, plazos o cantidades ausentes); si todo está claro, deja la lista vacía."),
        ("human", "Solicitud del cliente: {user_request}")
    ])

    try:
        data: LevantamientoData = _invoke_structured(
            llm, LevantamientoData, prompt, {"user_request": state["user_request"]}
        )
        return {"levantamiento_data": _levantamiento_to_text(data)}
    except Exception as e:  # noqa: BLE001
        print(f"Levantamiento estructurado falló ({e}). Usando prosa libre.")
        prose = ChatPromptTemplate.from_messages([
            ("system", "Eres un Ingeniero Topógrafo experto. Genera un reporte de levantamiento claro: "
                       "condiciones del sitio, alcance, restricciones técnicas e información faltante."),
            ("human", "Solicitud del cliente: {user_request}")
        ])
        try:
            resp = (prose | llm).invoke({"user_request": state["user_request"]})
            return {"levantamiento_data": resp.content}
        except Exception:  # noqa: BLE001
            return {"levantamiento_data": "Levantamiento no disponible por error del modelo."}

# --- PASCAL EDITOR SCHEMA HELPERS ---
class WallSegment(BaseModel):
    start: List[float] = Field(description="Punto inicial del muro [x, y] en metros")
    end: List[float] = Field(description="Punto final del muro [x, y] en metros")
    thickness: float = Field(default=0.2, description="Grosor del muro en metros (0.2=exterior, 0.1=interior)")
    wall_type: str = Field(default="exterior", description="Tipo de muro: 'exterior' o 'interior'")
    level: int = Field(default=0, description="Nivel al que pertenece (0=PB, 1=P1, etc.)")

class DoorOpening(BaseModel):
    wall_index: int = Field(description="Índice global del muro donde va la puerta (0-based en la lista de muros)")
    position_along_wall: float = Field(description="Posición normalizada: 0.0=inicio del muro, 1.0=fin, 0.5=centro")
    width: float = Field(default=0.9, description="Ancho de la puerta en metros")
    height: float = Field(default=2.1, description="Alto de la puerta en metros")

class WindowOpening(BaseModel):
    wall_index: int = Field(description="Índice global del muro donde va la ventana (0-based en la lista de muros)")
    position_along_wall: float = Field(description="Posición normalizada: 0.0=inicio del muro, 1.0=fin, 0.5=centro")
    width: float = Field(default=1.2, description="Ancho de la ventana en metros")
    height: float = Field(default=1.0, description="Alto de la ventana en metros")
    sill_height: float = Field(default=0.9, description="Altura del alféizar desde el piso en metros")

class StaircaseConfig(BaseModel):
    position: List[float] = Field(description="Posición [x, y] del origen de la escalera en metros")
    width: float = Field(default=1.0, description="Ancho de la escalera en metros")
    steps: int = Field(default=10, description="Número de escalones")
    direction: str = Field(default="north", description="Dirección de subida: 'north', 'south', 'east', 'west'")
    from_level: int = Field(default=0, description="Nivel de origen (0=PB)")
    to_level: int = Field(default=1, description="Nivel de destino")

class RoofConfig(BaseModel):
    roof_type: str = Field(default="flat", description="Tipo: 'flat', 'gabled', 'hip', 'shed'")
    pitch: float = Field(default=30.0, description="Ángulo de inclinación en grados (para techos no planos)")
    overhang: float = Field(default=0.5, description="Vuelo del alero en metros")
    ridge_direction: str = Field(default="east-west", description="Dirección de la cumbrera: 'east-west' o 'north-south'")

class FurnitureItem(BaseModel):
    name: str = Field(description="Nombre del mueble u objeto: 'bed', 'sofa', 'toilet', 'sink', 'bathtub', 'table', 'chair', 'wardrobe', 'desk', 'refrigerator', 'shower', etc.")
    position: List[float] = Field(description="Posición [x, y] del centro del objeto en metros")
    rotation: float = Field(default=0.0, description="Rotación en grados (0, 90, 180, 270)")
    level: int = Field(default=0, description="Nivel donde se coloca el objeto (0=PB, 1=P1, etc.)")

class ArchitectExtraction(BaseModel):
    walls: List[WallSegment] = Field(
        description="Lista de TODOS los muros de TODOS los niveles. Cada muro tiene 'level' (0=PB, 1=P1...), "
        "'thickness' (0.2=exterior, 0.1=interior), 'wall_type' ('exterior'/'interior'). "
        "Forma polígonos cerrados por nivel. Sin medidas claras: habitación 4x4 m centrada en origen."
    )
    ceiling_height: float = Field(default=2.5, description="Altura del techo en metros (aplica a todos los niveles)")
    doors: List[DoorOpening] = Field(default_factory=list, description="Puertas. wall_index = índice global en la lista walls. Lista vacía si no aplica.")
    windows: List[WindowOpening] = Field(default_factory=list, description="Ventanas. wall_index = índice global en la lista walls. Lista vacía si no aplica.")
    staircases: List[StaircaseConfig] = Field(default_factory=list, description="Escaleras. Solo si num_levels > 1. Lista vacía si no aplica.")
    roof: RoofConfig = Field(default_factory=RoofConfig, description="Configuración del techo del nivel superior.")
    furniture: List[FurnitureItem] = Field(default_factory=list, description="Muebles y objetos en la escena. Lista vacía si no se mencionan.")
    num_levels: int = Field(default=1, description="Número total de niveles (1=solo PB, 2=PB+P1, etc.)")


def _gen_pascal_id(prefix: str) -> str:
    chars = string.ascii_lowercase + string.digits
    return f"{prefix}_{''.join(secrets.choice(chars) for _ in range(16))}"


# --- Contrato con el editor 3D (holtmont-3d-editor) --------------------------
#
# Cada nodo que sale de aquí lo valida `AnyNode` (Zod) en el puente del editor
# antes de llegar a `useScene.setScene()`. Los nombres y las formas de abajo no
# son estilo: son ese esquema. Lo que no encaja se descarta allá y la escena
# llega incompleta, así que cualquier cambio aquí se comprueba contra
# `tests/test_arquitectura_pascal_contrato.py` y contra el test de esquema del
# repositorio del editor (`bun test`).
#
# Sistema de coordenadas
# ----------------------
#   - Nivel: los muros viven en (x, y) metros; el editor mapea y → z.
#   - Muro: su malla se coloca en `start` y se gira hasta alinear el eje X local
#     con el muro. Por eso una puerta se posiciona con `[avance, altura, 0]`,
#     donde `avance` son metros desde `start`, no una fracción.
#   - Nivel n: el editor apila los niveles solo; no hay que sumar alturas aquí.

ALTURA_MURO_POR_DEFECTO_M = 2.5

# `RoofSegmentNode.roofType` del editor. Lo que el agente escriba fuera de esta
# tabla cae en 'gable', que es el techo a dos aguas de toda la vida.
TIPOS_DE_TECHO = {
    "flat": "flat", "plano": "flat",
    "gable": "gable", "gabled": "gable", "dos aguas": "gable", "a dos aguas": "gable",
    "hip": "hip", "hipped": "hip", "cuatro aguas": "hip",
    "shed": "shed", "un agua": "shed",
    "gambrel": "gambrel", "mansard": "mansard", "dutch": "dutch",
}

# Radianes de giro sobre Y según el rumbo de subida de la escalera.
RUMBOS_ESCALERA = {
    "north": 0.0, "norte": 0.0,
    "east": -math.pi / 2, "este": -math.pi / 2,
    "south": math.pi, "sur": math.pi,
    "west": math.pi / 2, "oeste": math.pi / 2,
}

# Huella de un escalón: lo que avanza la escalera por peldaño.
HUELLA_ESCALON_M = 0.28


def _acotar(valor: float, minimo: float, maximo: float) -> float:
    """Deja `valor` dentro de [minimo, maximo] aunque el intervalo esté invertido."""
    if maximo < minimo:
        return minimo
    return max(minimo, min(maximo, valor))


def _longitud_muro(muro: WallSegment) -> float:
    dx = muro.end[0] - muro.start[0]
    dy = muro.end[1] - muro.start[1]
    return math.sqrt(dx * dx + dy * dy)


def _build_pascal_scene(
    walls: List[WallSegment],
    ceiling_height: float = 2.5,
    doors: Optional[List[DoorOpening]] = None,
    windows: Optional[List[WindowOpening]] = None,
    staircases: Optional[List[StaircaseConfig]] = None,
    roof: Optional[RoofConfig] = None,
    furniture: Optional[List[FurnitureItem]] = None,
    num_levels: int = 1,
) -> dict:
    """Construye la escena que consume `useScene.setScene()` del editor Pascal."""
    doors = doors or []
    windows = windows or []
    staircases = staircases or []
    furniture = furniture or []
    if roof is None:
        roof = RoofConfig()

    altura_muro = ceiling_height if ceiling_height and ceiling_height > 0 else ALTURA_MURO_POR_DEFECTO_M

    site_id = _gen_pascal_id("site")
    building_id = _gen_pascal_id("building")

    # --- Conjunto completo de niveles ---
    wall_levels = {w.level for w in walls}
    all_level_indices = sorted(set(range(num_levels)) | wall_levels)
    top_level_idx = max(all_level_indices)
    level_id_map = {lvl: _gen_pascal_id("level") for lvl in all_level_indices}

    # --- Ids de muro por índice global ---
    wall_id_list = [_gen_pascal_id("wall") for _ in walls]

    # --- Coordenadas envolventes por nivel ---
    xs_by_level: dict = {lvl: [] for lvl in all_level_indices}
    ys_by_level: dict = {lvl: [] for lvl in all_level_indices}
    for w in walls:
        xs_by_level[w.level].extend([w.start[0], w.end[0]])
        ys_by_level[w.level].extend([w.start[1], w.end[1]])
    all_xs = [x for xs in xs_by_level.values() for x in xs] or [-2, 2]
    all_ys = [y for ys in ys_by_level.values() for y in ys] or [-2, 2]
    g_min_x, g_max_x = min(all_xs), max(all_xs)
    g_min_y, g_max_y = min(all_ys), max(all_ys)

    def _poly(lvl: int) -> list:
        xs, ys = xs_by_level[lvl], ys_by_level[lvl]
        mn_x, mx_x = (min(xs), max(xs)) if xs else (g_min_x, g_max_x)
        mn_y, mx_y = (min(ys), max(ys)) if ys else (g_min_y, g_max_y)
        return [[mn_x, mx_y], [mn_x, mn_y], [mx_x, mn_y], [mx_x, mx_y]]

    # --- Muros ---
    wall_nodes: dict = {}
    for i, w in enumerate(walls):
        wid = wall_id_list[i]
        wall_nodes[wid] = {
            "object": "node",
            "id": wid,
            "type": "wall",
            "name": f"Wall {i + 1} L{w.level}",
            "parentId": level_id_map[w.level],
            "visible": True,
            "metadata": {},
            "children": [],
            "start": list(w.start),
            "end": list(w.end),
            "thickness": w.thickness,
            "height": altura_muro,
            "frontSide": "exterior" if w.wall_type == "exterior" else "interior",
            "backSide": "interior",
        }

    # --- Huecos (puertas y ventanas) ---
    #
    # `position` va en coordenadas locales del muro: X son metros desde `start`,
    # Y es el centro del hueco medido desde el piso. El agente razona en
    # fracciones del muro (0.5 = a la mitad), así que la conversión se hace
    # aquí, que es donde se conoce la longitud real.
    opening_nodes: dict = {}
    for j, door in enumerate(doors, start=1):
        idx = door.wall_index if door.wall_index < len(wall_id_list) else 0
        pwid = wall_id_list[idx]
        largo = _longitud_muro(walls[idx])
        ancho = min(door.width, largo) if largo > 0 else door.width
        avance = _acotar(door.position_along_wall * largo, ancho / 2, largo - ancho / 2)
        did = _gen_pascal_id("door")
        opening_nodes[did] = {
            "object": "node", "id": did, "type": "door",
            "name": f"Door {j}", "parentId": pwid,
            "visible": True, "metadata": {},
            "wallId": pwid, "side": "front",
            "position": [avance, door.height / 2, 0],
            "rotation": [0, 0, 0],
            "width": ancho, "height": door.height,
        }
        wall_nodes[pwid]["children"].append(did)

    for k, win in enumerate(windows, start=1):
        idx = win.wall_index if win.wall_index < len(wall_id_list) else 0
        pwid = wall_id_list[idx]
        largo = _longitud_muro(walls[idx])
        ancho = min(win.width, largo) if largo > 0 else win.width
        alto = min(win.height, altura_muro)
        avance = _acotar(win.position_along_wall * largo, ancho / 2, largo - ancho / 2)
        centro_y = _acotar(win.sill_height + alto / 2, alto / 2, altura_muro - alto / 2)
        wndid = _gen_pascal_id("window")
        opening_nodes[wndid] = {
            "object": "node", "id": wndid, "type": "window",
            "name": f"Window {k}", "parentId": pwid,
            "visible": True, "metadata": {},
            "wallId": pwid, "side": "front",
            "position": [avance, centro_y, 0],
            "rotation": [0, 0, 0],
            "width": ancho, "height": alto,
        }
        wall_nodes[pwid]["children"].append(wndid)

    # --- Escaleras ---
    #
    # El editor modela una escalera como un grupo (`stair`) con tramos
    # (`stair-segment`) dentro: el grupo sin tramos no dibuja nada. Cada
    # escalera del agente es un tramo recto.
    staircase_nodes: dict = {}
    for m, stair in enumerate(staircases, start=1):
        from_lvl = stair.from_level if stair.from_level in level_id_map else min(all_level_indices)
        to_lvl = stair.to_level if stair.to_level in level_id_map else from_lvl
        peldanos = max(1, stair.steps)
        subida = altura_muro * max(1, to_lvl - from_lvl)
        sid = _gen_pascal_id("stair")
        seg_id = _gen_pascal_id("sseg")
        staircase_nodes[sid] = {
            "object": "node", "id": sid, "type": "stair",
            "name": f"Staircase {m}", "parentId": level_id_map[from_lvl],
            "visible": True, "metadata": {},
            "children": [seg_id],
            "position": [stair.position[0], 0, stair.position[1]],
            "rotation": RUMBOS_ESCALERA.get(str(stair.direction).lower(), 0.0),
            "stairType": "straight",
            "fromLevelId": level_id_map[from_lvl],
            "toLevelId": level_id_map.get(to_lvl),
            # El hueco en la losa del nivel de destino es lo que permite subir:
            # sin él la escalera termina contra el piso de arriba.
            "slabOpeningMode": "destination" if to_lvl in level_id_map and to_lvl != from_lvl else "none",
            "width": stair.width,
            "totalRise": subida,
            "stepCount": peldanos,
        }
        staircase_nodes[seg_id] = {
            "object": "node", "id": seg_id, "type": "stair-segment",
            "name": f"Staircase {m} — tramo 1", "parentId": sid,
            "visible": True, "metadata": {},
            "position": [0, 0, 0], "rotation": 0,
            "segmentType": "stair",
            "width": stair.width,
            "length": peldanos * HUELLA_ESCALON_M,
            "height": subida,
            "stepCount": peldanos,
            "attachmentSide": "front",
        }

    # --- Muebles ---
    #
    # Un `item` sin `asset` no se puede dibujar, y el catálogo de modelos vive
    # en el editor. Aquí se manda el nombre en `metadata.holtmontAsset` y el
    # puente lo resuelve contra ese catálogo; lo que no exista se descarta allá
    # con aviso, en vez de llegar roto a la escena.
    furniture_nodes: dict = {}
    for item in furniture:
        item_lvl = item.level if item.level in level_id_map else min(all_level_indices)
        fid = _gen_pascal_id("item")
        furniture_nodes[fid] = {
            "object": "node", "id": fid, "type": "item",
            "name": item.name, "parentId": level_id_map[item_lvl],
            "visible": True,
            "metadata": {"holtmontAsset": item.name},
            "children": [],
            "position": [item.position[0], 0, item.position[1]],
            "rotation": [0, math.radians(item.rotation), 0],
            "scale": [1, 1, 1],
        }

    # --- Niveles (losa + techo/cubierta + hijos) ---
    tipo_techo = TIPOS_DE_TECHO.get(str(roof.roof_type).strip().lower(), "gable")
    level_nodes: dict = {}
    horiz_nodes: dict = {}
    for lvl in all_level_indices:
        lvl_id = level_id_map[lvl]
        polygon = _poly(lvl)
        is_top = (lvl == top_level_idx)

        lvl_wall_ids = [wall_id_list[i] for i, w in enumerate(walls) if w.level == lvl]
        stair_ids = [sid for sid, sn in staircase_nodes.items()
                     if sn["type"] == "stair" and sn["parentId"] == lvl_id]
        furn_ids = [fid for fid, fn in furniture_nodes.items() if fn["parentId"] == lvl_id]

        slab_id = _gen_pascal_id("slab")
        horiz_nodes[slab_id] = {
            "object": "node", "id": slab_id, "type": "slab",
            "name": f"Slab L{lvl}", "parentId": lvl_id,
            "visible": True, "metadata": {},
            "polygon": polygon, "holes": [], "holeMetadata": [],
            "elevation": 0.05, "autoFromWalls": True,
        }

        cubierta_ids = [slab_id]
        if is_top and tipo_techo != "flat":
            cubierta_ids.extend(_nodos_de_techo(
                lvl_id, polygon, altura_muro, tipo_techo, roof, horiz_nodes))
        else:
            cover_id = _gen_pascal_id("ceiling")
            horiz_nodes[cover_id] = {
                "object": "node", "id": cover_id, "type": "ceiling",
                "name": f"Ceiling L{lvl}", "parentId": lvl_id,
                "visible": True, "metadata": {}, "children": [],
                "polygon": polygon, "holes": [], "holeMetadata": [],
                "height": altura_muro, "autoFromWalls": True,
            }
            cubierta_ids.append(cover_id)

        level_nodes[lvl_id] = {
            "object": "node", "id": lvl_id, "type": "level",
            "name": f"Level {lvl}",
            "parentId": building_id, "visible": True, "metadata": {},
            "children": lvl_wall_ids + cubierta_ids + stair_ids + furn_ids,
            "level": lvl,
        }

    # --- Terreno y edificio ---
    pad = 10
    site_polygon = {
        "type": "polygon",
        "points": [
            [g_min_x - pad, g_min_y - pad],
            [g_max_x + pad, g_min_y - pad],
            [g_max_x + pad, g_max_y + pad],
            [g_min_x - pad, g_max_y + pad],
        ],
    }
    building_inline = {
        "object": "node", "id": building_id, "type": "building",
        "name": "Building",
        "parentId": site_id, "visible": True, "metadata": {},
        "children": list(level_id_map.values()),
        "position": [0, 0, 0], "rotation": [0, 0, 0],
    }

    nodes = {
        site_id: {
            "object": "node", "id": site_id, "type": "site",
            "name": "Site",
            "parentId": None, "visible": True, "metadata": {},
            # `SiteNode.children` son nodos completos, no ids: así lo declara el
            # esquema del editor y así construye su escena por defecto.
            "polygon": site_polygon, "children": [building_inline],
        },
        building_id: building_inline,
        **level_nodes,
        **horiz_nodes,
        **wall_nodes,
        **opening_nodes,
        **staircase_nodes,
        **furniture_nodes,
    }

    return {"nodes": nodes, "rootNodeIds": [site_id]}


def _nodos_de_techo(
    lvl_id: str,
    polygon: List[List[float]],
    altura_muro: float,
    tipo_techo: str,
    roof: RoofConfig,
    destino: dict,
) -> List[str]:
    """Añade el grupo `roof` y su tramo a `destino`; devuelve los ids del nivel.

    El editor dibuja el techo a partir de los `roof-segment` que cuelgan del
    grupo: un `roof` sin tramos aparece en el árbol y no se ve en la escena.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    ancho_x = max(xs) - min(xs)
    ancho_y = max(ys) - min(ys)
    centro_x = (max(xs) + min(xs)) / 2
    centro_y = (max(ys) + min(ys)) / 2

    # La cumbrera de un tramo corre a lo largo de su X local. Para orientarla
    # norte-sur se gira el grupo 90° y se intercambian las medidas.
    norte_sur = "north" in str(roof.ridge_direction).lower() or "norte" in str(roof.ridge_direction).lower()
    giro = math.pi / 2 if norte_sur else 0.0
    ancho = ancho_y if norte_sur else ancho_x
    fondo = ancho_x if norte_sur else ancho_y

    pendiente = _acotar(roof.pitch, 1.0, 75.0)
    corrida = fondo if tipo_techo == "shed" else fondo / 2
    alto_techo = _acotar(math.tan(math.radians(pendiente)) * corrida, 0.2, 12.0)

    # Faldón vertical bajo la cubierta: apoya el techo sobre el muro sin
    # comerse la altura libre del nivel.
    faldon = 0.2

    roof_id = _gen_pascal_id("roof")
    seg_id = _gen_pascal_id("rseg")
    destino[roof_id] = {
        "object": "node", "id": roof_id, "type": "roof",
        "name": "Main Roof", "parentId": lvl_id,
        "visible": True, "metadata": {},
        "children": [seg_id],
        "position": [centro_x, altura_muro - faldon, centro_y],
        "rotation": giro,
    }
    destino[seg_id] = {
        "object": "node", "id": seg_id, "type": "roof-segment",
        "name": "Roof Segment 1", "parentId": roof_id,
        "visible": True, "metadata": {},
        "position": [0, 0, 0], "rotation": 0,
        "roofType": tipo_techo,
        "width": max(0.5, ancho), "depth": max(0.5, fondo),
        "wallHeight": faldon, "roofHeight": alto_techo,
        "overhang": max(0.0, roof.overhang),
    }
    return [roof_id]


def _default_room_scene() -> dict:
    """4x4 m fallback room when LLM fails."""
    walls = [
        WallSegment(start=[-2, -2], end=[2, -2]),
        WallSegment(start=[2, -2], end=[2, 2]),
        WallSegment(start=[2, 2], end=[-2, 2]),
        WallSegment(start=[-2, 2], end=[-2, -2]),
    ]
    return _build_pascal_scene(walls)


def _validate_and_fix_extraction(extraction: ArchitectExtraction) -> ArchitectExtraction:
    """Corrige problemas geométricos comunes antes de generar la escena Pascal."""
    n_walls = len(extraction.walls)

    def _wall_len(w: WallSegment) -> float:
        dx, dy = w.end[0] - w.start[0], w.end[1] - w.start[1]
        return math.sqrt(dx * dx + dy * dy)

    def _fix_door(d: DoorOpening) -> DoorOpening:
        idx = max(0, min(d.wall_index, n_walls - 1))
        pos = max(0.05, min(0.95, d.position_along_wall))
        wlen = _wall_len(extraction.walls[idx]) if n_walls > 0 else 1.0
        max_w = wlen * 0.8 if wlen > 0 else d.width
        return DoorOpening(wall_index=idx, position_along_wall=pos,
                           width=min(d.width, max_w), height=d.height)

    def _fix_window(w: WindowOpening) -> WindowOpening:
        idx = max(0, min(w.wall_index, n_walls - 1))
        pos = max(0.05, min(0.95, w.position_along_wall))
        wall = extraction.walls[idx] if n_walls > 0 else None
        wlen = _wall_len(wall) if wall else 1.0
        max_w = wlen * 0.8 if wlen > 0 else w.width
        return WindowOpening(wall_index=idx, position_along_wall=pos,
                             width=min(w.width, max_w), height=w.height,
                             sill_height=w.sill_height)

    def _fix_stair(s: StaircaseConfig, num_lvls: int) -> StaircaseConfig:
        max_lvl = max(0, num_lvls - 1)
        from_lvl = max(0, min(s.from_level, max(0, num_lvls - 2)))
        to_lvl = max(from_lvl + 1, min(s.to_level, max_lvl))
        return StaircaseConfig(position=s.position, width=s.width, steps=s.steps,
                               direction=s.direction, from_level=from_lvl, to_level=to_lvl)

    num_levels = max(1, extraction.num_levels)
    return ArchitectExtraction(
        walls=extraction.walls,
        ceiling_height=extraction.ceiling_height,
        doors=[_fix_door(d) for d in extraction.doors],
        windows=[_fix_window(w) for w in extraction.windows],
        staircases=[_fix_stair(s, num_levels) for s in extraction.staircases],
        roof=extraction.roof,
        furniture=extraction.furniture,
        num_levels=num_levels,
    )


def architect_node(state: PaperclipState, llm) -> dict:
    """Agente Arquitecto: Extrae muros del levantamiento y construye JSON Pascal Editor."""
    print("--- [Agente Arquitecto 3D] Generando modelo volumétrico ---")

    PASCAL_CATALOG = (
        "CATÁLOGO DE NODOS DISPONIBLES EN PASCAL EDITOR:\n"
        "- wall: muro (start/end [x,y], thickness, wall_type exterior/interior, level). Hijos: door/window.\n"
        "- door: puerta hija de wall (position 0-1 a lo largo del muro, width, height).\n"
        "- window: ventana hija de wall (position 0-1, width, height, sillHeight).\n"
        "- slab: losa de piso (por nivel, generada automáticamente).\n"
        "- ceiling: techo plano (height, por nivel). Usar cuando roof_type='flat'.\n"
        "- roof: techo inclinado (roofType: gabled/hip/shed, pitch en grados, overhang, ridgeDirection). "
        "Solo en nivel superior, reemplaza ceiling.\n"
        "- staircase: escalera (position [x,y], width, steps, direction: north/south/east/west, "
        "fromLevel, toLevel). Hija del nivel de origen.\n"
        "- object: mueble u objeto (name, position [x,y], rotation en grados, level).\n"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         f"{PASCAL_CATALOG}\n"
         "Eres un Arquitecto experto. Usa el catálogo para extraer TODOS los elementos del levantamiento:\n"
         "MUROS: start/end en metros, nivel (level), grosor (thickness: 0.2=exterior, 0.1=interior), "
         "tipo (wall_type). Polígono cerrado por nivel. Sin medidas: 4x4 m centrado en origen. "
         "Mínimo 4 muros siempre.\n"
         "PUERTAS: wall_index global (índice en la lista walls), position_along_wall (0.0-1.0), "
         "width=0.9 m, height=2.1 m por defecto.\n"
         "VENTANAS: wall_index global, position_along_wall (0.0-1.0), width=1.2 m, "
         "height=1.0 m, sill_height=0.9 m por defecto.\n"
         "ESCALERAS: solo si num_levels>1. position [x,y], width=1.0 m, steps, "
         "direction (north/south/east/west), from_level, to_level.\n"
         "TECHO: roof_type ('flat' si no se especifica, 'gabled', 'hip', 'shed'), "
         "pitch en grados, overhang en metros.\n"
         "MOBILIARIO: incluye muebles mencionados (cama, sofá, baño, cocina, etc.) con name en inglés, "
         "position [x,y], rotation, level.\n"
         "NUM_LEVELS: número total de pisos.\n"
         "Campos sin información: listas vacías o valores por defecto."),
        ("human", "Reporte de Levantamiento:\n{levantamiento_data}")
    ])

    try:
        structured_llm = llm.with_structured_output(ArchitectExtraction)
        chain = prompt | structured_llm
        extraction: ArchitectExtraction = chain.invoke({"levantamiento_data": state["levantamiento_data"]})
        extraction = _validate_and_fix_extraction(extraction)
        scene = _build_pascal_scene(
            extraction.walls, extraction.ceiling_height,
            extraction.doors, extraction.windows,
            extraction.staircases, extraction.roof,
            extraction.furniture, extraction.num_levels,
        )
        return {"architect_data": json.dumps(scene)}
    except Exception as e:
        # Antes se devolvía una habitación 4x4 sin puertas y el frontend la
        # anunciaba como "3D actualizado": quien pedía "8 x 5 m con una puerta"
        # recibía otra cosa sin enterarse. Ahora se intenta leer las medidas del
        # propio texto —que resuelve el caso corriente sin LLM— y solo si eso
        # tampoco da nada se recurre a la 4x4, dejando dicho que es un supuesto.
        print(f"Error generando escena Pascal: {e}. Intentando leer las medidas del texto.")
        from api.services import plano as servicio_plano

        extraccion = servicio_plano.extraccion_desde_texto(state.get("levantamiento_data"))
        if extraccion is not None:
            scene = _build_pascal_scene(
                extraccion.walls, extraccion.ceiling_height, extraccion.doors,
                extraccion.windows, extraccion.staircases, extraccion.roof,
                extraccion.furniture, extraccion.num_levels)
            return {"architect_data": json.dumps(scene), "architect_origen": "medidas"}
        return {"architect_data": json.dumps(_default_room_scene()),
                "architect_origen": "supuesto",
                "architect_aviso": (
                    "No se pudo interpretar el levantamiento y no se encontraron "
                    "medidas en el texto: el modelo 3D es una habitación de 4x4 m "
                    "de ejemplo, no la del proyecto.")}

def _normalize_calculo(data: CalculoData) -> CalculoData:
    """Garantiza cantidades > 0 (regla: nunca 0/null) y normaliza unidades de tiempo."""
    def _qty(q: str) -> str:
        return q if _to_float(q) > 0 else "1"

    valid_units = {"hora", "dia", "día", "semana"}
    def _unit(u: str) -> str:
        u = (u or "").strip().lower()
        return u if u in valid_units else "dia"

    return CalculoData(
        concepts=[ConceptItem(concept=c.concept, unit=c.unit, quantity=_qty(c.quantity)) for c in data.concepts],
        materials=[CalculoMaterial(description=m.description, unit=m.unit, quantity=_qty(m.quantity)) for m in data.materials],
        labor=[CalculoLabor(role=l.role, people=_qty(l.people), duration=_qty(l.duration), unit=_unit(l.unit)) for l in data.labor],
        equipment=[CalculoEquipment(description=eq.description, quantity=_qty(eq.quantity)) for eq in data.equipment],
    )


def _calculo_to_text(data: CalculoData) -> str:
    lines = ["## Catálogo de Conceptos"]
    lines += [f"- {c.concept} — {c.quantity} {c.unit}" for c in data.concepts] or ["- Sin conceptos."]
    lines.append("\n## Materiales e Insumos")
    lines += [f"- {m.description}: {m.quantity} {m.unit}" for m in data.materials] or ["- Sin materiales."]
    lines.append("\n## Mano de Obra")
    lines += [f"- {l.role}: {l.people} persona(s) x {l.duration} {l.unit}" for l in data.labor] or ["- Sin mano de obra."]
    lines.append("\n## Maquinaria y Equipo Especial")
    lines += [f"- {eq.description}: {eq.quantity}" for eq in data.equipment] or ["- Sin equipo especial."]
    return "\n".join(lines)


def calculo_node(state: PaperclipState, llm) -> dict:
    """Agente 2: Cálculo y Diseño. Genera requerimientos técnicos estructurados."""
    print("--- [Agente de Cálculo y Diseño] Diseñando solución técnica ---")

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Eres un Ingeniero Calculista y Arquitecto experto. A partir del reporte de levantamiento genera "
         "los requerimientos técnicos en listas separadas: 1) catálogo de conceptos principales con unidad "
         "(m2, m3, pza, lote) y cantidad, 2) materiales con unidad y cantidad, 3) mano de obra (rol, número "
         "de personas, duración y unidad de tiempo hora/dia/semana), 4) maquinaria y equipo especial. "
         "Toda cantidad debe ser mayor a 0; estima un valor de mercado razonable si falta el dato."),
        ("human", "Reporte de Levantamiento:\n{levantamiento_data}")
    ])

    try:
        data: CalculoData = _invoke_structured(
            llm, CalculoData, prompt, {"levantamiento_data": state["levantamiento_data"]}
        )
        data = _normalize_calculo(data)
        # El texto es para los agentes; la estructura es para las tablas.
        return {"calculo_data": _calculo_to_text(data),
                "calculo_struct": data.model_dump_json()}
    except Exception as e:  # noqa: BLE001
        print(f"Cálculo estructurado falló ({e}). Usando prosa libre.")
        prose = ChatPromptTemplate.from_messages([
            ("system", "Eres un Ingeniero Calculista experto. Detalla: 1) catálogo de conceptos, "
                       "2) materiales con cantidades, 3) mano de obra, 4) maquinaria y equipo especial."),
            ("human", "Reporte de Levantamiento:\n{levantamiento_data}")
        ])
        try:
            resp = (prose | llm).invoke({"levantamiento_data": state["levantamiento_data"]})
            return {"calculo_data": resp.content}
        except Exception:  # noqa: BLE001
            return {"calculo_data": "Cálculo no disponible por error del modelo."}

_CATEGORIAS_PRECIO = {
    "material": "Materiales",
    "mano_obra": "Mano de Obra",
    "herramienta": "Herramientas",
    "equipo": "Equipo y Maquinaria",
}


def _compute_precios(data: PreciosData) -> dict:
    """Calcula totales por línea y gran total EN CÓDIGO (no por el LLM) para evitar errores aritméticos.

    Validación: cantidad y precio unitario se fuerzan a > 0 (regla: nunca 0/null).
    """
    grupos: dict = {}
    grand_total = 0.0
    for it in data.items:
        q = _to_float(it.quantity, 1.0)
        if q <= 0:
            q = 1.0
        p = _to_float(it.unit_price, 0.0)
        if p <= 0:
            # Precio no puede ser 0: marca para revisión pero mantiene la línea visible.
            p = 1.0
        line_total = round(q * p, 2)
        grand_total += line_total
        cat = (it.category or "material").strip().lower()
        cat = cat if cat in _CATEGORIAS_PRECIO else "material"
        grupos.setdefault(cat, []).append({
            "description": it.description,
            "unit": it.unit,
            "quantity": q,
            "unit_price": p,
            "line_total": line_total,
        })
    return {"currency": data.currency or "MXN", "grupos": grupos, "grand_total": round(grand_total, 2)}


def _precios_to_text(computed: dict) -> str:
    cur = computed["currency"]
    lines = ["## Presupuesto con Precios Unitarios (totales calculados en código)"]
    for cat_key, label in _CATEGORIAS_PRECIO.items():
        items = computed["grupos"].get(cat_key)
        if not items:
            continue
        subtotal = round(sum(i["line_total"] for i in items), 2)
        lines.append(f"\n### {label} — subtotal {cur} {subtotal:,.2f}")
        for i in items:
            lines.append(
                f"- {i['description']}: {i['quantity']:g} {i['unit']} x "
                f"{cur} {i['unit_price']:,.2f} = {cur} {i['line_total']:,.2f}"
            )
    lines.append(f"\n## TOTAL ESTIMADO DEL PROYECTO: {cur} {computed['grand_total']:,.2f}")
    return "\n".join(lines)


def precios_node(state: PaperclipState, llm) -> dict:
    """Agente 3: Precios Unitarios. Asigna precio unitario por ítem; totales se calculan en código."""
    print("--- [Agente de Precios Unitarios] Estimando presupuesto ---")

    critique = state.get("precios_critique", "")
    critique_block = (
        f"\nUn revisor senior rechazó la versión anterior con esta crítica; corrígela: {critique}"
        if critique else ""
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Eres un Analista de Precios Unitarios experto. A partir de los requerimientos técnicos, lista CADA "
         "concepto (material, mano_obra, herramienta o equipo) con su unidad, cantidad y precio unitario "
         "estimado de mercado. NO calcules totales: solo asigna el precio UNITARIO de cada ítem; los totales "
         "se calculan automáticamente. Es CRÍTICO que el precio unitario sea mayor a 0 y nunca quede vacío; "
         "si no conoces el dato exacto inventa una estimación razonable de mercado."
         f"{critique_block}"),
        ("human", "Requerimientos Técnicos (Cálculo y Diseño):\n{calculo_data}")
    ])

    try:
        data: PreciosData = _invoke_structured(
            llm, PreciosData, prompt, {"calculo_data": state["calculo_data"]}
        )
        computed = _compute_precios(data)
        return {"precios_data": _precios_to_text(computed),
                "precios_struct": json.dumps(computed)}
    except Exception as e:  # noqa: BLE001
        print(f"Precios estructurado falló ({e}). Usando prosa libre.")
        prose = ChatPromptTemplate.from_messages([
            ("system", "Eres un Analista de Precios Unitarios experto. Genera un desglose con precio unitario "
                       "explícito por ítem (materiales, mano de obra, equipo) y un total estimado. "
                       "Nunca dejes precios en 0."),
            ("human", "Requerimientos Técnicos (Cálculo y Diseño):\n{calculo_data}")
        ])
        try:
            resp = (prose | llm).invoke({"calculo_data": state["calculo_data"]})
            return {"precios_data": resp.content}
        except Exception:  # noqa: BLE001
            return {"precios_data": "Precios no disponibles por error del modelo."}

# --- LA ESTIMACIÓN, ARMADA EN CÓDIGO ---------------------------------------
#
# Las tablas del formulario se llenaban con UNA sola llamada al LLM: el
# Integrador releía la prosa de los agentes anteriores y volvía a extraer de
# ella los materiales, la mano de obra, las herramientas y el equipo con el
# esquema más grande de todo el archivo (`StructuredAgencyData`: cinco listas
# anidadas). Si esa llamada fallaba —o devolvía las cinco listas vacías, que es
# como un modelo se rinde— el usuario veía las tablas intactas.
#
# El dato ya existía estructurado antes de esa llamada: `calculo_node` produce
# `CalculoData` y `precios_node` produce `PreciosData` con categoría, unidad,
# cantidad y precio unitario de cada concepto. Se serializaban a markdown y se
# tiraba la estructura. Estas funciones arman la estimación con esos datos, sin
# LLM: si la agencia calculó un presupuesto, las tablas se llenan.

def _clave(texto: str) -> str:
    """Descripción normalizada para cruzar cálculo y precios."""
    return re.sub(r"\s+", " ", str(texto or "").strip().lower())


def _num(valor: float) -> str:
    """Número a texto sin ceros de relleno: el formulario guarda cadenas."""
    return f"{valor:g}"


def _items_de(computed: Optional[dict], categoria: str) -> List[dict]:
    if not computed:
        return []
    return list((computed.get("grupos") or {}).get(categoria) or [])


def _materiales_de(calculo: Optional[CalculoData], computed: Optional[dict]) -> List[MaterialItem]:
    materiales = [
        MaterialItem(description=str(it["description"]), unit=str(it["unit"] or "pza"),
                     quantity=_num(it["quantity"]), cost=_num(it["unit_price"]))
        for it in _items_de(computed, "material")
    ]
    presupuestados = {_clave(m.description) for m in materiales}
    materiales += [
        MaterialItem(description=m.description, unit=m.unit or "pza",
                     quantity=_num(_to_float(m.quantity, 1.0)), cost="0")
        for m in (calculo.materials if calculo else [])
        if _clave(m.description) not in presupuestados
    ]
    return materiales


def _herramientas_de(computed: Optional[dict]) -> List[ToolItem]:
    # El cálculo no lista herramienta menor: si no está en el presupuesto, no
    # hay de dónde sacarla.
    return [
        ToolItem(description=str(it["description"]), unit=str(it["unit"] or "pza"),
                 quantity=_num(it["quantity"]), cost=_num(it["unit_price"]))
        for it in _items_de(computed, "herramienta")
    ]


def _equipos_de(calculo: Optional[CalculoData], computed: Optional[dict]) -> List[EquipmentItem]:
    # `days=1`: el total de la tabla es cantidad x días x costo y la cantidad
    # del presupuesto ya trae el tiempo dentro. Repitiendo los días aquí, el
    # equipo se cobraría dos veces.
    equipos = [
        EquipmentItem(description=str(it["description"]), unit=str(it["unit"] or "unidad"),
                      quantity=_num(it["quantity"]), days="1", cost=_num(it["unit_price"]))
        for it in _items_de(computed, "equipo")
    ]
    presupuestados = {_clave(e.description) for e in equipos}
    equipos += [
        EquipmentItem(description=eq.description, unit="unidad",
                      quantity=_num(_to_float(eq.quantity, 1.0)), days="1", cost="0")
        for eq in (calculo.equipment if calculo else [])
        if _clave(eq.description) not in presupuestados
    ]
    return equipos


def _precio_del_puesto(rol: str, por_rol: dict, usados: set) -> Optional[dict]:
    """El renglón del presupuesto que paga ese puesto, o None.

    El presupuesto y el cálculo no siempre nombran igual al mismo puesto
    ("Albañil" vs "Albañil oficial"): se acepta que uno contenga al otro antes
    de rendirse y dejar el salario en 0.
    """
    exacto = por_rol.get(rol)
    if exacto is not None:
        return exacto
    return next((it for clave, it in por_rol.items()
                 if clave not in usados and (clave in rol or rol in clave)), None)


def _mano_de_obra_de(calculo: Optional[CalculoData], computed: Optional[dict]) -> List[LaborItem]:
    """Cruza el precio del presupuesto con la gente y el tiempo del cálculo.

    La tabla del formulario multiplica salario x personal x tiempo, así que el
    precio unitario va como salario y el personal NO se mete en el tiempo.
    """
    presupuesto = _items_de(computed, "mano_obra")
    por_rol = {_clave(it["description"]): it for it in presupuesto}
    usados: set = set()

    filas: List[LaborItem] = []
    for puesto in (calculo.labor if calculo else []):
        precio = _precio_del_puesto(_clave(puesto.role), por_rol, usados)
        if precio is not None:
            usados.add(_clave(precio["description"]))
        filas.append(LaborItem(
            category=puesto.role, personnel=_num(_to_float(puesto.people, 1.0)),
            unit=puesto.unit or "semana", weeks=_num(_to_float(puesto.duration, 1.0)),
            salary=_num(precio["unit_price"]) if precio else "0"))

    # Puesto que solo aparece en el presupuesto: la cantidad presupuestada es
    # el tiempo contratado y el personal se asume en 1 para no inflar el total.
    filas += [
        LaborItem(category=str(it["description"]), personnel="1",
                  unit=str(it["unit"] or "semana"), weeks=_num(it["quantity"]),
                  salary=_num(it["unit_price"]))
        for it in presupuesto if _clave(it["description"]) not in usados
    ]
    return filas


def estimacion_desde_estructura(
    calculo: Optional[CalculoData], computed: Optional[dict]
) -> StructuredAgencyData:
    """Arma las cuatro tablas del formulario con lo que ya calcularon los agentes.

    `computed` es la salida de `_compute_precios`: cantidad y precio unitario ya
    validados (> 0) y agrupados por categoría. `calculo` aporta lo que el
    presupuesto no distingue: cuánta gente y por cuánto tiempo.

    Un concepto del cálculo sin precio entra igual con costo 0: la fila visible
    y en blanco es un pendiente que se ve; la fila ausente es el fallo mudo que
    originó esto.
    """
    return StructuredAgencyData(
        laborTable=_mano_de_obra_de(calculo, computed),
        requiredMaterials=_materiales_de(calculo, computed),
        toolsRequired=_herramientas_de(computed),
        specialEquipment=_equipos_de(calculo, computed),
        viaticosTable=[])


def estimacion_vacia(estimacion: StructuredAgencyData) -> bool:
    """True si no hay una sola fila que insertar en el formulario."""
    return not (estimacion.laborTable or estimacion.requiredMaterials
                or estimacion.toolsRequired or estimacion.specialEquipment)


def _estimacion_del_estado(state: PaperclipState) -> Optional[StructuredAgencyData]:
    """La estimación armada con lo estructurado del estado, o None si no alcanza."""
    calculo = None
    crudo_calculo = state.get("calculo_struct") or ""
    if crudo_calculo:
        try:
            calculo = CalculoData.model_validate_json(crudo_calculo)
        except Exception:  # noqa: BLE001
            calculo = None

    computed = None
    crudo_precios = state.get("precios_struct") or ""
    if crudo_precios:
        try:
            computed = json.loads(crudo_precios)
        except (ValueError, TypeError):
            computed = None

    if calculo is None and computed is None:
        return None
    estimacion = estimacion_desde_estructura(calculo, computed)
    return None if estimacion_vacia(estimacion) else estimacion


def evaluador_node(state: PaperclipState, llm) -> dict:
    """Agente Evaluador: revisa el presupuesto (cálculo + precios) antes de integrar.

    Loop de reflexión: si rechaza, devuelve una crítica que el nodo de precios
    usa para regenerar. Acotado por MAX_PRECIOS_REVISIONS para limitar costo.
    """
    revision = state.get("precios_revision", 0)
    print(f"--- [Agente Evaluador] Revisando presupuesto (revisión {revision}) ---")

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Eres un Revisor Senior de Costos de Construcción. Evalúa el presupuesto comparándolo con los "
         "requerimientos técnicos. Verifica: 1) que CADA concepto del cálculo tenga precio, 2) que los "
         "precios unitarios sean de mercado razonables (ni absurdamente altos ni cercanos a 0), 3) unidades "
         "coherentes, 4) que no falten partidas (materiales, mano de obra, equipo). Sé crítico pero aprueba "
         "(is_approved=True) si el presupuesto es sólido. Si rechazas, explica en critique qué corregir."),
        ("human", "Requerimientos Técnicos:\n{calculo_data}\n\nPresupuesto Propuesto:\n{precios_data}")
    ])

    try:
        result: PreciosCritique = _invoke_structured(
            llm, PreciosCritique, prompt,
            {"calculo_data": state["calculo_data"], "precios_data": state["precios_data"]},
        )
        print(f"  -> Aprobado: {result.is_approved} | {result.critique[:120]}")
        return {
            "precios_approved": result.is_approved,
            "precios_critique": result.critique,
            "precios_revision": revision + 1,
        }
    except Exception as e:  # noqa: BLE001
        # Si el evaluador falla, no bloquear el pipeline: aprobar y continuar.
        print(f"Evaluador falló ({e}). Aprobando presupuesto por defecto.")
        return {"precios_approved": True, "precios_critique": "", "precios_revision": revision + 1}


def route_after_evaluacion(state: PaperclipState) -> str:
    """Aprobado o agotadas las revisiones -> integrador. Si no, regenerar precios."""
    if state.get("precios_approved") or state.get("precios_revision", 0) > MAX_PRECIOS_REVISIONS:
        return "integrador"
    return "precios"


def integrador_node(state: PaperclipState, llm) -> dict:
    """Agente 4: Integrador. Deja la estimación en la forma que leen las tablas.

    Orden deliberado:

    1. **Con el presupuesto estructurado** (`estimacion_desde_estructura`), si
       `precios_node` lo produjo. Es determinista: cantidades y precios ya
       están validados, y las tablas se llenan sin otra llamada al modelo.
    2. **Con el LLM**, cuando el presupuesto se quedó en prosa —`precios_node`
       cayó a su respaldo— y sus precios solo existen en el texto. Ahora con
       reintento (`_invoke_structured`), como el resto de los nodos.
    3. **Con los conceptos del cálculo y costo 0**, si el modelo tampoco pudo.
       Una tabla con los conceptos y los precios en blanco es un pendiente que
       se ve; la tabla vacía es el fallo mudo de siempre.
    4. **Vacía**, y dicho en voz alta: `estimacion_origen` viaja hasta el
       formulario para que "no había nada que estimar" no se confunda con "la
       extracción falló".
    """
    print("--- [Agente Integrador] Estructurando JSON ---")

    def _salida(estimacion: StructuredAgencyData, origen: str) -> dict:
        json_dict = estimacion.model_dump()
        # La escena 3D viaja con la estimación: un fallo de las tablas no debe
        # descartar el diseño que el arquitecto ya generó.
        json_dict["arquitectura_3d_json"] = state.get("architect_data", "")
        return {"structured_data": json.dumps(json_dict), "estimacion_origen": origen}

    del_estado = _estimacion_del_estado(state)
    if del_estado is not None and state.get("precios_struct"):
        # Con presupuesto estructurado no hace falta el modelo: cantidades y
        # precios ya están, validados y agrupados por categoría.
        print(f"  -> {len(del_estado.requiredMaterials)} materiales, "
              f"{len(del_estado.toolsRequired)} herramientas, "
              f"{len(del_estado.laborTable)} de mano de obra, "
              f"{len(del_estado.specialEquipment)} equipos (desde el presupuesto)")
        return _salida(del_estado, "estructura")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Analista de Datos experto. Extrae la mano de obra, materiales, equipos y herramientas de los reportes anteriores en el formato JSON estricto solicitado. Extrae explícitamente los costos unitarios, salarios y cantidades basándote en el reporte de 'Precios'. ES CRÍTICO que extraigas explícitamente y llenes SIEMPRE los campos de costos y salarios (salary, cost, costo_unitario) basándote en el reporte de Precios. Si el reporte de Precios no tiene un costo exacto, invéntate una estimación razonable del mercado y úsala. NUNCA, bajo NINGUNA circunstancia dejes cantidades o costos en 0, nulos, vacíos o ausentes en el JSON resultante."),
        ("human", "Cálculo y Diseño:\n{calculo}\n\nPrecios:\n{precios}")
    ])

    try:
        result: StructuredAgencyData = _invoke_structured(
            llm, StructuredAgencyData, prompt,
            {"calculo": state.get("calculo_data", ""), "precios": state.get("precios_data", "")},
        )
        if not estimacion_vacia(result):
            return _salida(result, "llm")
        print("El integrador devolvió las cuatro tablas vacías.")
    except Exception as e:  # noqa: BLE001
        print(f"Error en extracción estructurada: {e}")

    if del_estado is not None:
        # El presupuesto se quedó en prosa (precios cayó a su respaldo) y el
        # modelo tampoco pudo: entran los conceptos del cálculo con costo 0.
        # Una tabla con los conceptos y los precios en blanco es un pendiente
        # que se ve; la tabla vacía es el fallo mudo de siempre.
        print("  -> estimación sin precios: los conceptos del cálculo, a capturar costo")
        return _salida(del_estado, "estructura_sin_precios")

    vacia = StructuredAgencyData(laborTable=[], requiredMaterials=[], toolsRequired=[],
                                 specialEquipment=[], viaticosTable=[])
    return _salida(vacia, "vacia")

# --- GRAPH BUILDER ---
def build_paperclip_graph(llm_text, llm_structured):
    builder = StateGraph(PaperclipState)
    
    # Text agents use llm_text (e.g. Gemini)
    builder.add_node("levantamiento", lambda state: levantamiento_node(state, llm_text))
    builder.add_node("calculo", lambda state: calculo_node(state, llm_text))
    builder.add_node("precios", lambda state: precios_node(state, llm_text))
    
    # Formatting/Structured agents use llm_structured (e.g. Groq)
    builder.add_node("architect", lambda state: architect_node(state, llm_structured))
    builder.add_node("evaluador", lambda state: evaluador_node(state, llm_structured))
    builder.add_node("integrador", lambda state: integrador_node(state, llm_structured))

    builder.add_edge(START, "levantamiento")
    builder.add_edge("levantamiento", "architect")
    builder.add_edge("architect", "calculo")
    builder.add_edge("calculo", "precios")
    # Loop de reflexión: precios -> evaluador -> (precios | integrador)
    builder.add_edge("precios", "evaluador")
    builder.add_conditional_edges(
        "evaluador",
        route_after_evaluacion,
        {"precios": "precios", "integrador": "integrador"},
    )
    builder.add_edge("integrador", END)

    return builder.compile()

# --- MAIN EXECUTION LOGIC ---
def run_paperclip_agency(user_request: str, api_key: str = None) -> dict:
    groq_api_key = api_key or os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_api_key:
        return {"success": False, "error": "Falta GROQ_API_KEY en el entorno"}
    
    if ChatGroq is None:
        return {"success": False, "error": "Falta la librería langchain_groq o langchain_google_genai"}

    # Groq is strictly used for JSON formatting / Tool calling (Structured Outputs)
    llm_structured = ChatGroq(model=MODELO_GROQ, temperature=0.2, api_key=groq_api_key)
    
    # Use Gemini for heavy text processing to save tokens. Fallback to Groq if missing.
    if gemini_key and ChatGoogleGenerativeAI is not None:
        llm_text = ChatGoogleGenerativeAI(
            model=MODELO_GEMINI, temperature=0.3, google_api_key=gemini_key)
    else:
        print("Aviso: GEMINI_API_KEY no detectada. Usando Groq para todos los agentes.")
        llm_text = llm_structured

    graph = build_paperclip_graph(llm_text, llm_structured)
    
    initial_state = {
        "user_request": user_request,
        "levantamiento_data": "",
        "architect_data": "",
        "architect_origen": "",
        "architect_aviso": "",
        "calculo_data": "",
        "calculo_struct": "",
        "precios_data": "",
        "precios_struct": "",
        "structured_data": "",
        "estimacion_origen": "",
        "precios_critique": "",
        "precios_approved": False,
        "precios_revision": 0,
    }
    
    try:
        final_state = graph.invoke(initial_state)
        return {
            "success": True,
            "levantamiento": final_state.get("levantamiento_data", ""),
            "calculo": final_state.get("calculo_data", ""),
            "precios": final_state.get("precios_data", ""),
            # Exponer la escena 3D directamente desde el estado del arquitecto,
            # desacoplada del integrador: así llega al frontend aunque la
            # extracción estructurada de tablas falle.
            "arquitectura_3d_json": final_state.get("architect_data", ""),
            "structured_data": final_state.get("structured_data", "{}"),
            # De dónde salieron las tablas: "estructura" (del presupuesto que
            # calculó la propia agencia), "llm" (extraídas de la prosa) o
            # "vacia" (no se pudo). El formulario lo dice en su aviso: sin este
            # dato, "no había nada que estimar" y "la extracción falló" se ven
            # exactamente igual desde la pantalla.
            "estimacion_origen": final_state.get("estimacion_origen", ""),
            "architect_aviso": final_state.get("architect_aviso", ""),
        }
    except Exception as e:
        return {"success": False, "error": f"Error ejecutando la agencia: {str(e)}"}
