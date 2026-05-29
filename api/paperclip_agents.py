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


# --- STATE DEFINITION ---
class PaperclipState(TypedDict):
    user_request: str
    levantamiento_data: str
    architect_data: str
    calculo_data: str
    precios_data: str
    structured_data: str

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
    """Construye un JSON válido para useScene.setState() de Pascal Editor."""
    doors = doors or []
    windows = windows or []
    staircases = staircases or []
    furniture = furniture or []
    if roof is None:
        roof = RoofConfig()

    site_id = _gen_pascal_id("site")
    building_id = _gen_pascal_id("building")

    # --- Determine full level set ---
    wall_levels = {w.level for w in walls}
    all_level_indices = sorted(set(range(num_levels)) | wall_levels)
    top_level_idx = max(all_level_indices)
    level_id_map = {lvl: _gen_pascal_id("level") for lvl in all_level_indices}

    # --- Pre-generate wall IDs (global index) ---
    wall_id_list = [_gen_pascal_id("wall") for _ in walls]

    # --- Per-level bounding coordinates ---
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

    # --- Wall nodes ---
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
            "frontSide": "exterior" if w.wall_type == "exterior" else "interior",
            "backSide": "interior",
        }

    # --- Opening nodes (doors + windows) — populate wall children ---
    opening_nodes: dict = {}
    for j, door in enumerate(doors, start=1):
        pwid = wall_id_list[door.wall_index] if door.wall_index < len(wall_id_list) else wall_id_list[0]
        did = _gen_pascal_id("door")
        opening_nodes[did] = {
            "object": "node", "id": did, "type": "door",
            "name": f"Door {j}", "parentId": pwid,
            "visible": True, "metadata": {}, "children": [],
            "position": door.position_along_wall,
            "width": door.width, "height": door.height,
        }
        wall_nodes[pwid]["children"].append(did)

    for k, win in enumerate(windows, start=1):
        pwid = wall_id_list[win.wall_index] if win.wall_index < len(wall_id_list) else wall_id_list[0]
        wndid = _gen_pascal_id("window")
        opening_nodes[wndid] = {
            "object": "node", "id": wndid, "type": "window",
            "name": f"Window {k}", "parentId": pwid,
            "visible": True, "metadata": {}, "children": [],
            "position": win.position_along_wall,
            "width": win.width, "height": win.height, "sillHeight": win.sill_height,
        }
        wall_nodes[pwid]["children"].append(wndid)

    # --- Staircase nodes ---
    staircase_nodes: dict = {}
    for m, stair in enumerate(staircases, start=1):
        from_lvl = stair.from_level if stair.from_level in level_id_map else min(all_level_indices)
        sid = _gen_pascal_id("staircase")
        staircase_nodes[sid] = {
            "object": "node", "id": sid, "type": "staircase",
            "name": f"Staircase {m}", "parentId": level_id_map[from_lvl],
            "visible": True, "metadata": {}, "children": [],
            "position": list(stair.position) + [0],
            "width": stair.width, "steps": stair.steps,
            "direction": stair.direction,
            "fromLevel": stair.from_level, "toLevel": stair.to_level,
        }

    # --- Furniture nodes ---
    furniture_nodes: dict = {}
    for n, item in enumerate(furniture, start=1):
        item_lvl = item.level if item.level in level_id_map else min(all_level_indices)
        fid = _gen_pascal_id("object")
        furniture_nodes[fid] = {
            "object": "node", "id": fid, "type": "object",
            "name": item.name, "parentId": level_id_map[item_lvl],
            "visible": True, "metadata": {}, "children": [],
            "position": list(item.position) + [0],
            "rotation": [0, 0, item.rotation],
        }

    # --- Level nodes (slab + ceiling/roof + all children) ---
    level_nodes: dict = {}
    horiz_nodes: dict = {}
    for lvl in all_level_indices:
        lvl_id = level_id_map[lvl]
        polygon = _poly(lvl)
        is_top = (lvl == top_level_idx)

        lvl_wall_ids = [wall_id_list[i] for i, w in enumerate(walls) if w.level == lvl]
        stair_ids = [sid for sid, sn in staircase_nodes.items() if sn["fromLevel"] == lvl]
        furn_ids = [fid for fid, fn in furniture_nodes.items() if fn["parentId"] == lvl_id]

        slab_id = _gen_pascal_id("slab")
        horiz_nodes[slab_id] = {
            "object": "node", "id": slab_id, "type": "slab",
            "name": f"Slab L{lvl}", "parentId": lvl_id,
            "visible": True, "metadata": {},
            "polygon": polygon, "holes": [], "holeMetadata": [],
            "elevation": 0.05, "autoFromWalls": True,
        }

        if is_top and roof.roof_type != "flat":
            cover_id = _gen_pascal_id("roof")
            horiz_nodes[cover_id] = {
                "object": "node", "id": cover_id, "type": "roof",
                "name": "Main Roof", "parentId": lvl_id,
                "visible": True, "metadata": {},
                "polygon": polygon, "holes": [],
                "roofType": roof.roof_type, "pitch": roof.pitch,
                "overhang": roof.overhang, "ridgeDirection": roof.ridge_direction,
                "autoFromWalls": True,
            }
        else:
            cover_id = _gen_pascal_id("ceiling")
            horiz_nodes[cover_id] = {
                "object": "node", "id": cover_id, "type": "ceiling",
                "name": f"Ceiling L{lvl}", "parentId": lvl_id,
                "visible": True, "metadata": {}, "children": [],
                "polygon": polygon, "holes": [], "holeMetadata": [],
                "height": ceiling_height, "autoFromWalls": True,
            }

        level_nodes[lvl_id] = {
            "object": "node", "id": lvl_id, "type": "level",
            "parentId": None, "visible": True, "metadata": {},
            "children": lvl_wall_ids + [slab_id, cover_id] + stair_ids + furn_ids,
            "level": lvl,
        }

    # --- Site and building ---
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
        "parentId": None, "visible": True, "metadata": {},
        "children": list(level_id_map.values()),
        "position": [0, 0, 0], "rotation": [0, 0, 0],
    }

    nodes = {
        site_id: {
            "object": "node", "id": site_id, "type": "site",
            "parentId": None, "visible": True, "metadata": {},
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
        print(f"Error generando escena Pascal: {e}. Usando habitacion 4x4 por defecto.")
        return {"architect_data": json.dumps(_default_room_scene())}

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
        return {"calculo_data": _calculo_to_text(data)}
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

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Eres un Analista de Precios Unitarios experto. A partir de los requerimientos técnicos, lista CADA "
         "concepto (material, mano_obra, herramienta o equipo) con su unidad, cantidad y precio unitario "
         "estimado de mercado. NO calcules totales: solo asigna el precio UNITARIO de cada ítem; los totales "
         "se calculan automáticamente. Es CRÍTICO que el precio unitario sea mayor a 0 y nunca quede vacío; "
         "si no conoces el dato exacto inventa una estimación razonable de mercado."),
        ("human", "Requerimientos Técnicos (Cálculo y Diseño):\n{calculo_data}")
    ])

    try:
        data: PreciosData = _invoke_structured(
            llm, PreciosData, prompt, {"calculo_data": state["calculo_data"]}
        )
        computed = _compute_precios(data)
        return {"precios_data": _precios_to_text(computed)}
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

def integrador_node(state: PaperclipState, llm) -> dict:
    """Agente 4: Integrador. Extrae los recursos en formato JSON estricto."""
    print("--- [Agente Integrador] Estructurando JSON ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres un Analista de Datos experto. Extrae la mano de obra, materiales, equipos y herramientas de los reportes anteriores en el formato JSON estricto solicitado. Extrae explícitamente los costos unitarios, salarios y cantidades basándote en el reporte de 'Precios'. ES CRÍTICO que extraigas explícitamente y llenes SIEMPRE los campos de costos y salarios (salary, cost, costo_unitario) basándote en el reporte de Precios. Si el reporte de Precios no tiene un costo exacto, invéntate una estimación razonable del mercado y úsala. NUNCA, bajo NINGUNA circunstancia dejes cantidades o costos en 0, nulos, vacíos o ausentes en el JSON resultante."),
        ("human", "Cálculo y Diseño:\n{calculo}\n\nPrecios:\n{precios}")
    ])
    
    # Use structured output
    structured_llm = llm.with_structured_output(StructuredAgencyData)
    chain = prompt | structured_llm
    
    try:
        import json
        result: StructuredAgencyData = chain.invoke({
            "calculo": state["calculo_data"],
            "precios": state["precios_data"]
        })
        json_dict = result.model_dump()
        json_dict["arquitectura_3d_json"] = state.get("architect_data", "")
        return {"structured_data": json.dumps(json_dict)}
    except Exception as e:
        import json
        print(f"Error en extracción estructurada: {e}")
        empty_data = StructuredAgencyData(laborTable=[], requiredMaterials=[], toolsRequired=[], specialEquipment=[], viaticosTable=[])
        empty_dict = empty_data.model_dump()
        # Preservar la escena 3D que el arquitecto ya generó: un fallo del
        # integrador (extracción de tablas) no debe descartar el diseño.
        empty_dict["arquitectura_3d_json"] = state.get("architect_data", "")
        return {"structured_data": json.dumps(empty_dict)}

# --- GRAPH BUILDER ---
def build_paperclip_graph(llm_text, llm_structured):
    builder = StateGraph(PaperclipState)
    
    # Text agents use llm_text (e.g. Gemini)
    builder.add_node("levantamiento", lambda state: levantamiento_node(state, llm_text))
    builder.add_node("calculo", lambda state: calculo_node(state, llm_text))
    builder.add_node("precios", lambda state: precios_node(state, llm_text))
    
    # Formatting/Structured agents use llm_structured (e.g. Groq)
    builder.add_node("architect", lambda state: architect_node(state, llm_structured))
    builder.add_node("integrador", lambda state: integrador_node(state, llm_structured))
    
    builder.add_edge(START, "levantamiento")
    builder.add_edge("levantamiento", "architect")
    builder.add_edge("architect", "calculo")
    builder.add_edge("calculo", "precios")
    builder.add_edge("precios", "integrador")
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
    llm_structured = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2, api_key=groq_api_key)
    
    # Use Gemini for heavy text processing to save tokens. Fallback to Groq if missing.
    if gemini_key and ChatGoogleGenerativeAI is not None:
        llm_text = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.3, google_api_key=gemini_key)
    else:
        print("Aviso: GEMINI_API_KEY no detectada. Usando Groq para todos los agentes.")
        llm_text = llm_structured

    graph = build_paperclip_graph(llm_text, llm_structured)
    
    initial_state = {
        "user_request": user_request,
        "levantamiento_data": "",
        "architect_data": "",
        "calculo_data": "",
        "precios_data": "",
        "structured_data": ""
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
            "structured_data": final_state.get("structured_data", "{}")
        }
    except Exception as e:
        return {"success": False, "error": f"Error ejecutando la agencia: {str(e)}"}
