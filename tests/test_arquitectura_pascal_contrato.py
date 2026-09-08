"""
El contrato entre la escena que genera Python y el editor 3D.

Por qué existe este archivo
---------------------------
`useScene.setScene()` del editor **no valida**: guarda el objeto tal cual se lo
den. Un nodo con un campo de la forma equivocada no falla al importar; falla
después, dentro del bucle de render de react-three-fiber, que muere sin
mensaje. Lo que se ve entonces es el lienzo en negro de la captura del bug:
la interfaz entera bien, el plano 3D vacío.

Eso es exactamente lo que pasaba: `_build_pascal_scene` escribía una puerta con
`position: 0.5` (una fracción del muro) donde el editor espera
`position: [x, y, z]` en metros, y `DoorSystem` reventaba en
`segments.reduce(...)` sobre `undefined`.

`tests/test_architect_pascal.py` pasaba con esa escena rota porque comprobaba
la forma que Python escribía, no la que el editor lee. Este archivo comprueba la
segunda: cada aserción de abajo es un campo del esquema Zod de
`holtmont-3d-editor/packages/core/src/schema/nodes/`. Si el editor cambia su
esquema, esto se pone en rojo — que es justo el aviso que faltaba.

La misma escena se valida además contra el Zod de verdad en el repositorio del
editor (`bun test apps/editor/lib/holtmont-import.test.ts`); aquí se comprueba
del lado que la genera, para que el fallo salga antes de cruzar el iframe.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.paperclip_agents import (  # noqa: E402
    ArchitectExtraction,
    DoorOpening,
    FurnitureItem,
    RoofConfig,
    StaircaseConfig,
    WallSegment,
    WindowOpening,
    _build_pascal_scene,
    _default_room_scene,
)
from api.services.plano import generar_plano  # noqa: E402

# --- Vocabulario del editor -------------------------------------------------
# `AnyNode` es una unión discriminada por `type`: un `type` que no esté en esta
# lista no lo dibuja nadie. 'staircase' y 'object' —los que escribía la versión
# anterior— no están, y por eso no se veían.
TIPOS_DEL_EDITOR = {
    "site", "building", "level", "wall", "fence", "item", "zone", "slab",
    "ceiling", "roof", "roof-segment", "stair", "stair-segment", "scan",
    "guide", "window", "door",
}

# `LevelNode.children` solo admite estos tipos. Un `roof-segment` colgado del
# nivel (en vez de del grupo `roof`) tumba la validación del nivel entero.
TIPOS_HIJOS_DE_NIVEL = {
    "wall", "fence", "zone", "slab", "ceiling", "roof", "stair", "scan", "guide",
    "item",
}
TIPOS_HIJOS_DE_MURO = {"item", "door", "window"}


def _es_terna(valor) -> bool:
    return (isinstance(valor, (list, tuple)) and len(valor) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valor))


def _es_par(valor) -> bool:
    return (isinstance(valor, (list, tuple)) and len(valor) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valor))


def _es_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def verificar_escena(escena: dict) -> dict:
    """Comprueba la escena entera contra el esquema del editor.

    Devuelve los nodos por tipo para que cada prueba siga desde ahí sin repetir
    el recorrido.
    """
    assert set(escena.keys()) == {"nodes", "rootNodeIds"}, escena.keys()
    nodos = escena["nodes"]
    raices = escena["rootNodeIds"]
    assert isinstance(nodos, dict) and nodos, "la escena no trae nodos"
    assert isinstance(raices, list) and raices, "la escena no trae rootNodeIds"

    for raiz in raices:
        assert raiz in nodos, f"rootNodeIds apunta a {raiz}, que no existe"

    por_tipo: dict = {}
    for nid, nodo in nodos.items():
        assert nodo.get("id") == nid, f"{nid}: la clave del diccionario y el id no coinciden"
        assert nodo.get("object") == "node", f"{nid}: falta object='node'"
        tipo = nodo.get("type")
        assert tipo in TIPOS_DEL_EDITOR, f"{nid}: type '{tipo}' no existe en el editor"
        # `objectId(prefijo)` del editor es una plantilla `prefijo_...`: un id
        # con otra forma no pasa la validación de Zod.
        assert "_" in str(nid), f"{nid}: el id no lleva el prefijo que exige el editor"
        assert isinstance(nodo.get("metadata"), dict), f"{nid}: metadata debe ser objeto"
        assert isinstance(nodo.get("visible"), bool), f"{nid}: visible debe ser booleano"
        por_tipo.setdefault(tipo, []).append(nodo)

        padre = nodo.get("parentId")
        assert padre is None or padre in nodos, f"{nid}: parentId {padre} no existe"

        _verificar_nodo(nid, nodo, nodos)

    return por_tipo


def _verificar_nodo(nid: str, nodo: dict, nodos: dict) -> None:
    tipo = nodo["type"]

    if tipo == "site":
        poligono = nodo.get("polygon")
        assert isinstance(poligono, dict) and poligono.get("type") == "polygon", \
            f"{nid}: SiteNode.polygon es {{type:'polygon', points:[...]}}"
        assert all(_es_par(p) for p in poligono.get("points", [])), f"{nid}: points mal formados"
        # SiteNode.children son nodos completos, no ids.
        for hijo in nodo.get("children", []):
            assert isinstance(hijo, dict) and hijo.get("type") in ("building", "item"), \
                f"{nid}: los hijos del sitio son nodos building/item completos"

    elif tipo == "building":
        assert _es_terna(nodo.get("position")), f"{nid}: BuildingNode.position es [x,y,z]"
        assert _es_terna(nodo.get("rotation")), f"{nid}: BuildingNode.rotation es [x,y,z]"
        for hijo in nodo.get("children", []):
            assert nodos[hijo]["type"] == "level", f"{nid}: solo niveles cuelgan del edificio"

    elif tipo == "level":
        assert isinstance(nodo.get("level"), int), f"{nid}: LevelNode.level es un entero"
        for hijo in nodo.get("children", []):
            assert hijo in nodos, f"{nid}: hijo {hijo} inexistente"
            assert nodos[hijo]["type"] in TIPOS_HIJOS_DE_NIVEL, \
                f"{nid}: '{nodos[hijo]['type']}' no puede colgar de un nivel"

    elif tipo == "wall":
        assert _es_par(nodo.get("start")) and _es_par(nodo.get("end")), \
            f"{nid}: WallNode.start/end son [x, y]"
        assert _es_numero(nodo.get("thickness")), f"{nid}: falta thickness"
        assert _es_numero(nodo.get("height")), f"{nid}: falta height"
        assert nodo.get("frontSide") in ("interior", "exterior", "unknown")
        assert nodo.get("backSide") in ("interior", "exterior", "unknown")
        for hijo in nodo.get("children", []):
            assert nodos[hijo]["type"] in TIPOS_HIJOS_DE_MURO, \
                f"{nid}: '{nodos[hijo]['type']}' no puede colgar de un muro"

    elif tipo in ("door", "window"):
        assert _es_terna(nodo.get("position")), \
            f"{nid}: {tipo}.position son metros [x, y, z] en el sistema del muro, no una fracción"
        assert _es_terna(nodo.get("rotation")), f"{nid}: {tipo}.rotation es [x,y,z]"
        assert _es_numero(nodo.get("width")) and _es_numero(nodo.get("height"))
        assert nodo.get("side") in ("front", "back"), f"{nid}: falta side"
        padre = nodos.get(nodo.get("parentId"))
        assert padre is not None and padre["type"] == "wall", f"{nid}: {tipo} sin muro padre"
        assert nodo.get("wallId") == padre["id"], f"{nid}: wallId debe apuntar al muro padre"
        assert nodo["id"] in padre["children"], f"{nid}: el muro no lo lista en children"
        # El hueco tiene que caber en el muro: el editor recorta contra sus
        # límites y un vano fuera del muro no abre nada.
        largo = math.dist(padre["start"], padre["end"])
        avance = nodo["position"][0]
        assert -1e-6 <= avance - nodo["width"] / 2, f"{nid}: el vano se sale por el arranque del muro"
        assert avance + nodo["width"] / 2 <= largo + 1e-6, f"{nid}: el vano se sale por el final del muro"
        alto_muro = padre["height"]
        centro = nodo["position"][1]
        assert centro - nodo["height"] / 2 >= -1e-6, f"{nid}: el vano baja del piso"
        assert centro + nodo["height"] / 2 <= alto_muro + 1e-6, f"{nid}: el vano pasa del techo"

    elif tipo in ("slab", "ceiling"):
        assert all(_es_par(p) for p in nodo.get("polygon", [])) and len(nodo.get("polygon", [])) >= 3, \
            f"{nid}: {tipo}.polygon es una lista de [x, y] con al menos 3 puntos"
        assert isinstance(nodo.get("holes"), list)
        if tipo == "ceiling":
            assert _es_numero(nodo.get("height")), f"{nid}: falta height"
        else:
            assert _es_numero(nodo.get("elevation")), f"{nid}: falta elevation"

    elif tipo == "roof":
        assert _es_terna(nodo.get("position")), f"{nid}: RoofNode.position es [x,y,z]"
        assert _es_numero(nodo.get("rotation")), f"{nid}: RoofNode.rotation es un número (giro en Y)"
        hijos = nodo.get("children", [])
        assert hijos, f"{nid}: un techo sin tramos no dibuja nada"
        for hijo in hijos:
            assert nodos[hijo]["type"] == "roof-segment", f"{nid}: los hijos del techo son roof-segment"

    elif tipo == "roof-segment":
        assert nodo.get("roofType") in (
            "hip", "gable", "shed", "gambrel", "dutch", "mansard", "flat"), \
            f"{nid}: roofType '{nodo.get('roofType')}' no existe en el editor"
        assert _es_terna(nodo.get("position")) and _es_numero(nodo.get("rotation"))
        for campo in ("width", "depth", "wallHeight", "roofHeight"):
            assert _es_numero(nodo.get(campo)), f"{nid}: falta {campo}"
        assert nodos[nodo["parentId"]]["type"] == "roof", f"{nid}: el tramo cuelga del grupo roof"

    elif tipo == "stair":
        assert _es_terna(nodo.get("position")), f"{nid}: StairNode.position es [x,y,z]"
        assert _es_numero(nodo.get("rotation")), f"{nid}: StairNode.rotation es un número"
        assert nodo.get("stairType") in ("straight", "curved", "spiral")
        assert _es_numero(nodo.get("totalRise")) and nodo["totalRise"] > 0
        assert isinstance(nodo.get("stepCount"), int) and nodo["stepCount"] >= 1
        assert nodo.get("slabOpeningMode") in ("none", "destination")
        for campo in ("fromLevelId", "toLevelId"):
            valor = nodo.get(campo)
            assert valor is None or nodos[valor]["type"] == "level", \
                f"{nid}: {campo} debe ser el id de un nivel"
        hijos = nodo.get("children", [])
        assert hijos, f"{nid}: una escalera sin tramos no dibuja nada"
        for hijo in hijos:
            assert nodos[hijo]["type"] == "stair-segment"

    elif tipo == "stair-segment":
        assert _es_terna(nodo.get("position")) and _es_numero(nodo.get("rotation"))
        assert nodo.get("segmentType") in ("stair", "landing")
        for campo in ("width", "length", "height"):
            assert _es_numero(nodo.get(campo)), f"{nid}: falta {campo}"
        assert nodo.get("attachmentSide") in ("front", "left", "right")

    elif tipo == "item":
        assert _es_terna(nodo.get("position")), f"{nid}: ItemNode.position es [x,y,z]"
        assert _es_terna(nodo.get("rotation")) and _es_terna(nodo.get("scale"))
        # El catálogo de modelos vive en el editor: aquí solo viaja el nombre.
        assert nodo["metadata"].get("holtmontAsset"), \
            f"{nid}: sin metadata.holtmontAsset el puente no puede resolver el modelo"


def _cuarto(ancho: float, largo: float, nivel: int = 0):
    mx, my = ancho / 2, largo / 2
    esquinas = [(-mx, -my), (mx, -my), (mx, my), (-mx, my)]
    return [WallSegment(start=list(esquinas[i]), end=list(esquinas[(i + 1) % 4]), level=nivel)
            for i in range(4)]


# --- Los dos casos que pidió el usuario -------------------------------------

def test_cuarto_de_5x4_con_una_puerta_es_valido_para_el_editor():
    """«un cuarto de 5x4 con una puerta»: el camino sin LLM, de punta a punta."""
    resultado = generar_plano("Construir un cuarto de 5 x 4 m con una puerta")
    assert resultado["success"], resultado.get("message")

    por_tipo = verificar_escena(resultado["escena_3d"])
    assert len(por_tipo["wall"]) == 4
    assert len(por_tipo["door"]) == 1
    assert len(por_tipo["level"]) == 1
    assert len(por_tipo["slab"]) == 1

    puerta = por_tipo["door"][0]
    muro = {n["id"]: n for n in por_tipo["wall"]}[puerta["parentId"]]
    largo = math.dist(muro["start"], muro["end"])
    # A la mitad del muro: es donde la coloca el repartidor de vanos, y es la
    # comprobación de que la fracción se convirtió en metros y no se copió tal cual.
    assert puerta["position"][0] == pytest.approx(largo / 2, abs=0.01)
    assert puerta["position"][1] == pytest.approx(puerta["height"] / 2)


def test_casa_de_dos_pisos_con_ventanas_al_frente_y_atras():
    """«casa de 2 pisos con ventanas al frente y trasera»: dos niveles, escalera y techo."""
    muros = _cuarto(8, 6, nivel=0) + _cuarto(8, 6, nivel=1)
    extraccion = ArchitectExtraction(
        walls=muros,
        ceiling_height=2.7,
        num_levels=2,
        # Frente y trasera de cada nivel: muros 0 y 2 de la planta baja,
        # 4 y 6 del primer piso.
        windows=[
            WindowOpening(wall_index=0, position_along_wall=0.5),
            WindowOpening(wall_index=2, position_along_wall=0.5),
            WindowOpening(wall_index=4, position_along_wall=0.5),
            WindowOpening(wall_index=6, position_along_wall=0.5),
        ],
        doors=[DoorOpening(wall_index=0, position_along_wall=0.25)],
        staircases=[StaircaseConfig(position=[0, 0], from_level=0, to_level=1)],
        roof=RoofConfig(roof_type="gabled", pitch=30.0),
    )
    escena = _build_pascal_scene(
        extraccion.walls, extraccion.ceiling_height, extraccion.doors,
        extraccion.windows, extraccion.staircases, extraccion.roof,
        extraccion.furniture, extraccion.num_levels)

    por_tipo = verificar_escena(escena)
    assert len(por_tipo["level"]) == 2
    assert len(por_tipo["wall"]) == 8
    assert len(por_tipo["window"]) == 4
    assert len(por_tipo["door"]) == 1
    assert len(por_tipo["stair"]) == 1 and len(por_tipo["stair-segment"]) == 1
    assert len(por_tipo["roof"]) == 1 and len(por_tipo["roof-segment"]) == 1
    # El techo va arriba del todo; abajo hay techo plano (ceiling) de entreplanta.
    assert len(por_tipo["ceiling"]) == 1

    niveles = {n["level"]: n for n in por_tipo["level"]}
    assert set(niveles) == {0, 1}
    escalera = por_tipo["stair"][0]
    assert escalera["fromLevelId"] == niveles[0]["id"]
    assert escalera["toLevelId"] == niveles[1]["id"]
    assert escalera["slabOpeningMode"] == "destination"
    assert escalera["totalRise"] == pytest.approx(2.7)

    # Las ventanas del piso de arriba cuelgan de muros del nivel 1.
    por_id = escena["nodes"]
    niveles_con_ventana = {por_id[por_id[v["parentId"]]["parentId"]]["level"]
                           for v in por_tipo["window"]}
    assert niveles_con_ventana == {0, 1}


# --- Invariantes que valen para cualquier instrucción -----------------------

@pytest.mark.parametrize("descripcion", [
    "Cuarto de 5 x 4 m con una puerta",
    "Bodega de 12 x 8 metros con dos puertas y cuatro ventanas",
    "Oficina de 3,5 x 2,5 m, altura 3 m, sin puertas ni ventanas",
    "Nave de 25 por 15 m con puerta",
    "Cuarto de máquinas de 2 x 2 m con puerta y ventana",
])
def test_toda_descripcion_con_medidas_produce_una_escena_valida(descripcion):
    resultado = generar_plano(descripcion)
    assert resultado["success"], resultado.get("message")
    verificar_escena(resultado["escena_3d"])


def test_la_habitacion_por_defecto_tambien_cumple_el_contrato():
    verificar_escena(_default_room_scene())


def test_techo_plano_usa_ceiling_y_no_deja_grupo_roof_vacio():
    escena = _build_pascal_scene(_cuarto(5, 4), roof=RoofConfig(roof_type="flat"))
    por_tipo = verificar_escena(escena)
    assert "roof" not in por_tipo
    assert len(por_tipo["ceiling"]) == 1


@pytest.mark.parametrize("tipo_pedido,esperado", [
    ("gabled", "gable"), ("hip", "hip"), ("shed", "shed"),
    ("dos aguas", "gable"), ("inventado", "gable"),
])
def test_el_tipo_de_techo_se_traduce_al_vocabulario_del_editor(tipo_pedido, esperado):
    escena = _build_pascal_scene(_cuarto(6, 4), roof=RoofConfig(roof_type=tipo_pedido))
    por_tipo = verificar_escena(escena)
    assert por_tipo["roof-segment"][0]["roofType"] == esperado


def test_el_mueble_viaja_con_el_nombre_para_que_el_puente_resuelva_el_modelo():
    escena = _build_pascal_scene(
        _cuarto(5, 4),
        furniture=[FurnitureItem(name="cama", position=[1, 1], rotation=90)])
    por_tipo = verificar_escena(escena)
    assert len(por_tipo["item"]) == 1
    mueble = por_tipo["item"][0]
    assert mueble["metadata"]["holtmontAsset"] == "cama"
    assert mueble["rotation"][1] == pytest.approx(math.pi / 2)


def test_una_puerta_mas_ancha_que_el_muro_se_acomoda_dentro_del_muro():
    """El editor recorta contra los límites del muro: un vano mayor no abre nada."""
    muros = [WallSegment(start=[0, 0], end=[1.5, 0]),
             WallSegment(start=[1.5, 0], end=[1.5, 3]),
             WallSegment(start=[1.5, 3], end=[0, 3]),
             WallSegment(start=[0, 3], end=[0, 0])]
    escena = _build_pascal_scene(
        muros, doors=[DoorOpening(wall_index=0, position_along_wall=1.0, width=3.0)])
    por_tipo = verificar_escena(escena)
    puerta = por_tipo["door"][0]
    assert puerta["width"] <= 1.5


def test_una_ventana_mas_alta_que_el_muro_se_acomoda_bajo_el_techo():
    escena = _build_pascal_scene(
        _cuarto(5, 4), ceiling_height=2.4,
        windows=[WindowOpening(wall_index=0, position_along_wall=0.5,
                               height=3.0, sill_height=2.0)])
    por_tipo = verificar_escena(escena)
    ventana = por_tipo["window"][0]
    assert ventana["height"] <= 2.4
    assert ventana["position"][1] + ventana["height"] / 2 <= 2.4 + 1e-6


def test_un_indice_de_muro_fuera_de_rango_no_deja_la_puerta_huerfana():
    escena = _build_pascal_scene(
        _cuarto(5, 4), doors=[DoorOpening(wall_index=99, position_along_wall=0.5)])
    verificar_escena(escena)
