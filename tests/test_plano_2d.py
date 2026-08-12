"""
El Plano 2D sale de la geometría, no de un generador de imágenes.

Qué estaba mal
--------------
El botón "Plano 2D (IA)" no dibujaba un plano: llamaba desde el navegador a
`image.pollinations.ai`, un servicio de difusión texto→imagen, y mostraba lo que
devolviera. Con "habitación de 8 x 5 m con una puerta" eso produce una
ilustración plausible con medidas inventadas: no respeta la escala, no lleva
cotas, cambia en cada intento (la semilla es aleatoria) y no guarda ninguna
relación con el modelo que abre el Editor 3D. Dos botones de la misma pantalla,
alimentados por la misma descripción, contaban cosas distintas.

Y el modelo 3D tenía su propio agujero: `architect_node` cae a una habitación
4x4 m sin puertas cuando el LLM falla o no hay clave configurada, y el frontend
lo anunciaba como "3D actualizado". Pedir 8x5 con puerta y recibir 4x4 sin
puerta, sin aviso, es el peor resultado posible: parece que funcionó.

Qué se hace ahora
-----------------
Una sola geometría alimenta las dos vistas. Cuando la descripción trae medidas
—que es el caso corriente— se leen sin LLM, de forma determinista, y el plano se
dibuja en SVG a escala y con cotas. El LLM sigue estando para lo que el parser
no sabe leer, pero ya no es la única puerta, y cuando no se pudo usar se dice.

El caso que abre este archivo es el que pidió el dueño:
    "habitación de 8 x 5 m con una puerta"
"""

from __future__ import annotations

import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import plano  # noqa: E402

CASO_DEL_DUENO = "habitación de 8 x 5 m con una puerta"


# ----------------------------------------------------------------------
# 1. Leer las medidas de la descripción
# ----------------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("habitación de 8 x 5 m con una puerta", (8.0, 5.0)),
    ("habitacion de 8x5", (8.0, 5.0)),
    ("cuarto de 8 por 5 metros", (8.0, 5.0)),
    ("oficina 10.5 x 4 m", (10.5, 4.0)),
    ("bodega de 10,5 x 4 mts", (10.5, 4.0)),
    ("nave de 8 m x 5 m", (8.0, 5.0)),
    ("AREA DE 8 X 5 M", (8.0, 5.0)),
    ("habitación de 8 × 5 m", (8.0, 5.0)),
])
def test_las_medidas_se_leen_del_texto(texto, esperado):
    assert plano.medidas_de_texto(texto) == esperado


@pytest.mark.parametrize("sin_medidas", [
    "remodelar la oficina de dirección",
    "cambiar luminarias del pasillo",
    "",
    None,
])
def test_sin_medidas_no_se_inventa_una_habitacion(sin_medidas):
    """
    Devuelve `None` y el trabajo pasa al LLM, que es quien puede interpretar un
    levantamiento en prosa. Inventar 4x4 aquí sería repetir el fallo que este
    archivo viene a quitar.
    """
    assert plano.medidas_de_texto(sin_medidas) is None


def test_una_medida_absurda_no_se_acepta():
    """
    Un número suelto enorme suele ser un folio o un código, no una medida. El
    tope es generoso (200 m) pero existe: sin él, "cotización 5000 x 3" dibuja
    un plano de cinco kilómetros.
    """
    assert plano.medidas_de_texto("cotizacion 5000 x 3") is None
    assert plano.medidas_de_texto("habitacion de 0 x 5 m") is None


# ----------------------------------------------------------------------
# 2. Contar puertas y ventanas
# ----------------------------------------------------------------------

@pytest.mark.parametrize("texto,puertas,ventanas", [
    ("habitación de 8 x 5 m con una puerta", 1, 0),
    ("habitación de 8 x 5 m con 2 puertas y 3 ventanas", 2, 3),
    ("cuarto 4 x 4 con dos ventanas", 0, 2),
    ("oficina 6 x 4 m con puerta", 1, 0),
    ("bodega 6 x 4 m sin ventanas", 0, 0),
    ("nave 6 x 4", 0, 0),
])
def test_se_cuentan_los_huecos_pedidos(texto, puertas, ventanas):
    assert plano.cuenta_de(texto, "puerta") == puertas
    assert plano.cuenta_de(texto, "ventana") == ventanas


# ----------------------------------------------------------------------
# 3. La geometría del caso del dueño
# ----------------------------------------------------------------------

def test_el_caso_del_dueno_produce_una_habitacion_de_8_por_5():
    ext = plano.extraccion_desde_texto(CASO_DEL_DUENO)

    assert ext is not None, "No se pudo leer «8 x 5 m» de la descripción"
    assert len(ext.walls) == 4, "Una habitación rectangular son cuatro muros"

    largos = sorted(round(plano.largo_de_muro(m), 2) for m in ext.walls)
    assert largos == [5.0, 5.0, 8.0, 8.0], (
        f"Los muros no miden 8 y 5 metros: {largos}")


def test_el_caso_del_dueno_pone_exactamente_una_puerta():
    ext = plano.extraccion_desde_texto(CASO_DEL_DUENO)

    assert len(ext.doors) == 1
    assert len(ext.windows) == 0
    puerta = ext.doors[0]
    assert 0 <= puerta.wall_index < 4
    assert puerta.width == pytest.approx(0.9), "Una puerta de paso son 90 cm"
    assert puerta.height == pytest.approx(2.1)


def test_el_poligono_cierra():
    """
    Cuatro muros que no cierran no son una habitación: el 3D deja un hueco y el
    2D dibuja una L. El final del último muro tiene que ser el inicio del
    primero.
    """
    ext = plano.extraccion_desde_texto(CASO_DEL_DUENO)

    for anterior, siguiente in zip(ext.walls, ext.walls[1:] + ext.walls[:1]):
        assert anterior.end == siguiente.start, (
            f"El polígono no cierra: {anterior.end} != {siguiente.start}")


def test_los_huecos_se_reparten_entre_muros_distintos():
    """Dos puertas en el mismo muro y en la misma posición serían una sola."""
    ext = plano.extraccion_desde_texto("bodega de 10 x 6 m con 3 puertas")

    muros = [d.wall_index for d in ext.doors]
    assert len(set(muros)) == 3, f"Las tres puertas cayeron en {set(muros)}"


def test_ninguna_puerta_es_mas_ancha_que_su_muro():
    """
    El caso que rompe el dibujo: una puerta de 0.9 m en un muro de 0.5 m deja el
    hueco fuera del trazo y el 3D abre un boquete que se come la esquina.
    """
    ext = plano.extraccion_desde_texto("closet de 0.6 x 0.5 m con una puerta")

    for d in ext.doors:
        muro = ext.walls[d.wall_index]
        assert d.width <= plano.largo_de_muro(muro), (
            "La puerta no cabe en su muro")


def test_la_altura_se_lee_cuando_se_menciona():
    ext = plano.extraccion_desde_texto("nave de 20 x 10 m con altura de 6 m")
    assert ext.ceiling_height == pytest.approx(6.0)


def test_sin_altura_se_usa_la_de_siempre():
    ext = plano.extraccion_desde_texto(CASO_DEL_DUENO)
    assert ext.ceiling_height == pytest.approx(2.5)


# ----------------------------------------------------------------------
# 4. El dibujo
# ----------------------------------------------------------------------

@pytest.fixture
def svg_del_caso() -> str:
    return plano.svg_de_extraccion(plano.extraccion_desde_texto(CASO_DEL_DUENO))


def test_el_plano_es_un_svg(svg_del_caso):
    assert svg_del_caso.lstrip().startswith("<svg")
    assert svg_del_caso.rstrip().endswith("</svg>")
    assert "viewBox=" in svg_del_caso


def test_el_plano_dibuja_los_cuatro_muros(svg_del_caso):
    assert svg_del_caso.count('class="muro"') == 4


def test_el_plano_dibuja_la_puerta(svg_del_caso):
    assert 'class="puerta"' in svg_del_caso


def test_el_plano_lleva_las_cotas_reales(svg_del_caso):
    """
    Lo que separa un plano de una ilustración: los números. Si dice 8 x 5, el
    dibujo tiene que decir 8.00 m y 5.00 m.
    """
    assert "8.00 m" in svg_del_caso
    assert "5.00 m" in svg_del_caso


def test_el_plano_respeta_la_proporcion(svg_del_caso):
    """
    Una habitación de 8x5 se dibuja más ancha que alta. Si el SVG saliera
    cuadrado, el plano estaría mintiendo sobre la forma del espacio.
    """
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_del_caso)
    assert m, "El SVG no declara viewBox"
    ancho, alto = float(m.group(1)), float(m.group(2))
    assert ancho > alto, f"8x5 salió con viewBox {ancho}x{alto}"


def test_el_dibujo_es_el_mismo_dos_veces():
    """
    Determinista, al contrario que el generador de imágenes que había antes: la
    misma descripción da exactamente el mismo plano. Es lo que permite adjuntarlo
    a una orden y que dentro de un mes siga siendo el mismo documento.
    """
    uno = plano.svg_de_extraccion(plano.extraccion_desde_texto(CASO_DEL_DUENO))
    dos = plano.svg_de_extraccion(plano.extraccion_desde_texto(CASO_DEL_DUENO))
    assert uno == dos


def test_el_svg_no_trae_ni_scripts_ni_recursos_externos(svg_del_caso):
    """
    El SVG se inyecta en el DOM de la aplicación: no puede traer `<script>`, ni
    manejadores `on*`, ni pedir nada a un tercero.
    """
    bajo = svg_del_caso.lower()
    assert "<script" not in bajo
    assert not re.search(r"\son\w+\s*=", bajo), "El SVG trae un manejador de eventos"
    # El único `http` admisible es el namespace de SVG, que es un identificador,
    # no una descarga. Cualquier otra referencia sí saldría a la red.
    sin_namespace = bajo.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http://" not in sin_namespace and "https://" not in sin_namespace
    for externo in ("<image", "xlink:href", "src=", "url("):
        assert externo not in bajo, f"El SVG referencia algo externo: {externo}"


def test_la_descripcion_se_escapa_en_el_titulo():
    """
    El texto del usuario acaba dentro del SVG. Sin escapar, un `<` suelto rompe
    el documento — y peor, lo que va entre corchetes angulares se interpreta.
    """
    ext = plano.extraccion_desde_texto("sala de 5 x 4 m")
    svg = plano.svg_de_extraccion(ext, titulo='<img src=x onerror="alert(1)">')

    assert "<img" not in svg
    assert "&lt;img" in svg


# ----------------------------------------------------------------------
# 5. Las dos vistas cuentan lo mismo
# ----------------------------------------------------------------------

def test_el_plano_y_el_modelo_3d_salen_de_la_misma_geometria():
    """
    La regla de fondo de todo este arreglo: el 2D y el 3D no pueden discrepar,
    porque son la misma habitación vista de dos maneras.
    """
    from api.paperclip_agents import _build_pascal_scene

    ext = plano.extraccion_desde_texto(CASO_DEL_DUENO)
    escena = _build_pascal_scene(
        ext.walls, ext.ceiling_height, ext.doors, ext.windows,
        ext.staircases, ext.roof, ext.furniture, ext.num_levels)

    muros = [n for n in escena["nodes"].values() if n["type"] == "wall"]
    puertas = [n for n in escena["nodes"].values() if n["type"] == "door"]
    assert len(muros) == 4
    assert len(puertas) == 1

    largos = sorted(round(plano.largo_de_muro_xy(m["start"], m["end"]), 2) for m in muros)
    assert largos == [5.0, 5.0, 8.0, 8.0], (
        f"El 3D no mide lo mismo que el 2D: {largos}")


def test_la_puerta_del_3d_cuelga_del_muro_que_dice_el_2d():
    from api.paperclip_agents import _build_pascal_scene

    ext = plano.extraccion_desde_texto(CASO_DEL_DUENO)
    escena = _build_pascal_scene(
        ext.walls, ext.ceiling_height, ext.doors, ext.windows,
        ext.staircases, ext.roof, ext.furniture, ext.num_levels)

    nodos = escena["nodes"]
    puerta = next(n for n in nodos.values() if n["type"] == "door")
    muro_padre = nodos[puerta["parentId"]]

    assert muro_padre["type"] == "wall"
    esperado = ext.walls[ext.doors[0].wall_index]
    assert list(muro_padre["start"]) == list(esperado.start)
    assert list(muro_padre["end"]) == list(esperado.end)


# ----------------------------------------------------------------------
# 6. El plano completo, que es lo que consume el endpoint
# ----------------------------------------------------------------------

def test_generar_plano_dice_que_lo_resolvio_sin_llm():
    resultado = plano.generar_plano(CASO_DEL_DUENO)

    assert resultado["success"] is True
    assert resultado["origen"] == "medidas", (
        "Una descripción con medidas explícitas no necesita LLM")
    assert resultado["svg"].lstrip().startswith("<svg")
    assert resultado["escena_3d"]["nodes"], "Falta la escena para el editor 3D"


def test_generar_plano_sin_medidas_y_sin_llm_no_finge():
    """
    El fallo que había: sin poder leer la descripción se devolvía una habitación
    4x4 como si fuera lo pedido. Ahora se dice que no se pudo, y el usuario
    decide si escribe las medidas o revisa la clave del agente.
    """
    resultado = plano.generar_plano("remodelar la oficina de dirección", llm=None)

    assert resultado["success"] is False
    assert "medidas" in resultado["message"].lower()
    assert resultado.get("svg") in (None, "")


def test_generar_plano_usa_el_llm_cuando_no_hay_medidas():
    """Sin medidas legibles el trabajo pasa al agente, que es quien lee prosa."""
    from api.paperclip_agents import ArchitectExtraction, WallSegment

    class _LlmFalso:
        def with_structured_output(self, modelo):
            return self

        def invoke(self, _):
            return ArchitectExtraction(walls=[
                WallSegment(start=[0, 0], end=[6, 0]),
                WallSegment(start=[6, 0], end=[6, 3]),
                WallSegment(start=[6, 3], end=[0, 3]),
                WallSegment(start=[0, 3], end=[0, 0]),
            ])

    resultado = plano.generar_plano(
        "una recepción alargada con mostrador al fondo", llm=_LlmFalso())

    assert resultado["success"] is True
    assert resultado["origen"] == "agente"
    assert "6.00 m" in resultado["svg"]


def test_si_el_llm_revienta_se_dice_en_vez_de_dibujar_una_4x4():
    class _LlmRoto:
        def with_structured_output(self, modelo):
            return self

        def invoke(self, _):
            raise RuntimeError("401 api key inválida")

    resultado = plano.generar_plano("una nave industrial", llm=_LlmRoto())

    assert resultado["success"] is False
    assert resultado.get("svg") in (None, "")
    assert "4" not in resultado.get("origen", "")


# ----------------------------------------------------------------------
# 7. Batería de descripciones: lo pedido es lo dibujado
# ----------------------------------------------------------------------
# El caso "8 x 5 con una puerta" es un ejemplo, no la especificación. Esta tabla
# recorre las formas en que la gente escribe de verdad en el campo
# "Descripción del Trabajo a Realizar": sinónimos del espacio, medidas con
# decimales y con coma, cantidades en cifra y en palabra, alturas, y el orden
# de las palabras cambiado.

CASOS = [
    # (descripción, ancho, largo, puertas, ventanas, altura)
    ("habitación de 8 x 5 m con una puerta",                8.0,  5.0,  1, 0, 2.5),
    ("oficina de 6 x 4 m con una puerta y dos ventanas",    6.0,  4.0,  1, 2, 2.5),
    ("bodega de 12 x 8 m con 2 puertas",                   12.0,  8.0,  2, 0, 2.5),
    ("nave industrial de 20 x 10 m con altura de 6 m",     20.0, 10.0,  0, 0, 6.0),
    ("cuarto de máquinas 3.5 x 2.5 m con una puerta",       3.5,  2.5,  1, 0, 2.5),
    ("sala de juntas de 7,5 x 4,5 m con tres ventanas",     7.5,  4.5,  0, 3, 2.5),
    ("almacén 15 por 9 metros con cuatro puertas",         15.0,  9.0,  4, 0, 2.5),
    ("baño de 2 x 2 m con puerta",                          2.0,  2.0,  1, 0, 2.5),
    ("taller de 10 m x 6 m, altura 4.5 m, dos puertas y "
     "cinco ventanas",                                     10.0,  6.0,  2, 5, 4.5),
    ("AREA DE TRABAJO DE 9 X 6 M CON UNA PUERTA",           9.0,  6.0,  1, 0, 2.5),
    ("recepción 5x3 sin puertas ni ventanas",               5.0,  3.0,  0, 0, 2.5),
    ("pasillo de 12 × 1.5 m",                              12.0,  1.5,  0, 0, 2.5),
]


@pytest.mark.parametrize("texto,ancho,largo,puertas,ventanas,altura", CASOS)
def test_la_geometria_es_la_pedida(texto, ancho, largo, puertas, ventanas, altura):
    ext = plano.extraccion_desde_texto(texto)

    assert ext is not None, f"No se pudo leer: {texto}"
    assert len(ext.walls) == 4
    largos = sorted(round(plano.largo_de_muro(m), 2) for m in ext.walls)
    esperados = sorted([round(ancho, 2), round(ancho, 2), round(largo, 2), round(largo, 2)])
    assert largos == esperados, f"{texto}: muros {largos}, esperados {esperados}"
    assert len(ext.doors) == puertas, f"{texto}: {len(ext.doors)} puertas"
    assert len(ext.windows) == ventanas, f"{texto}: {len(ext.windows)} ventanas"
    assert ext.ceiling_height == pytest.approx(altura), f"{texto}: altura"


@pytest.mark.parametrize("texto,ancho,largo,puertas,ventanas,altura", CASOS)
def test_el_plano_de_cada_caso_lleva_sus_cotas(texto, ancho, largo, puertas, ventanas, altura):
    svg = plano.svg_de_extraccion(plano.extraccion_desde_texto(texto))

    assert f"{ancho:.2f} m" in svg, f"{texto}: falta la cota {ancho:.2f} m"
    assert f"{largo:.2f} m" in svg, f"{texto}: falta la cota {largo:.2f} m"
    assert svg.count('class="muro"') == 4
    assert svg.count('class="puerta"') == puertas
    assert svg.count('class="ventana"') == ventanas


@pytest.mark.parametrize("texto,ancho,largo,puertas,ventanas,altura", CASOS)
def test_el_modelo_3d_de_cada_caso_coincide_con_su_plano(texto, ancho, largo, puertas, ventanas, altura):
    """Las dos vistas, caso por caso: mismos muros, mismos huecos, misma altura."""
    from api.paperclip_agents import _build_pascal_scene

    ext = plano.extraccion_desde_texto(texto)
    escena = _build_pascal_scene(
        ext.walls, ext.ceiling_height, ext.doors, ext.windows,
        ext.staircases, ext.roof, ext.furniture, ext.num_levels)
    nodos = list(escena["nodes"].values())

    muros = [n for n in nodos if n["type"] == "wall"]
    assert len(muros) == 4
    assert len([n for n in nodos if n["type"] == "door"]) == puertas
    assert len([n for n in nodos if n["type"] == "window"]) == ventanas

    largos = sorted(round(plano.largo_de_muro_xy(m["start"], m["end"]), 2) for m in muros)
    assert largos == sorted([round(ancho, 2), round(ancho, 2),
                             round(largo, 2), round(largo, 2)]), texto


@pytest.mark.parametrize("texto,ancho,largo,puertas,ventanas,altura", CASOS)
def test_los_huecos_de_cada_caso_caben_en_su_muro(texto, ancho, largo, puertas, ventanas, altura):
    """Ningún hueco puede ser más ancho que el muro que lo aloja, en ningún caso."""
    ext = plano.extraccion_desde_texto(texto)

    for hueco in list(ext.doors) + list(ext.windows):
        muro = ext.walls[hueco.wall_index]
        assert hueco.width <= plano.largo_de_muro(muro), (
            f"{texto}: un hueco de {hueco.width} m no cabe en su muro")


@pytest.mark.parametrize("texto,ancho,largo,puertas,ventanas,altura", CASOS)
def test_ningun_caso_necesita_llm(texto, ancho, largo, puertas, ventanas, altura):
    """
    Todos estos se resuelven leyendo el texto. Es lo que hace que el plano
    funcione con la clave del agente caída, que era el fallo silencioso.
    """
    resultado = plano.generar_plano(texto, llm=None)

    assert resultado["success"] is True, f"{texto}: {resultado.get('message')}"
    assert resultado["origen"] == "medidas"


# ----------------------------------------------------------------------
# 8. Los huecos no se pisan y el dibujo no se desborda
# ----------------------------------------------------------------------

def _tramos_por_muro(ext):
    """Los intervalos que ocupa cada hueco sobre su muro, agrupados por muro."""
    tramos = {}
    for hueco in list(ext.doors) + list(ext.windows):
        muro = ext.walls[hueco.wall_index]
        inicio, fin = plano._tramo_del_hueco(
            muro, hueco.position_along_wall, hueco.width)
        tramos.setdefault(hueco.wall_index, []).append((inicio, fin))
    return tramos


@pytest.mark.parametrize("texto", [c[0] for c in CASOS] + [
    "taller de 10 x 6 m con 4 puertas y 4 ventanas",
    "nave de 12 x 8 m con 6 puertas y 6 ventanas",
    "sala de 5 x 4 m con dos puertas y dos ventanas",
])
def test_ningun_hueco_se_monta_sobre_otro(texto):
    """
    Una ventana dibujada encima de una puerta es un vano que no existe: en el
    plano se ve un trazo de color sobre otro y en el 3D son dos huecos
    solapados en el mismo muro.
    """
    ext = plano.extraccion_desde_texto(texto)

    for indice, tramos in _tramos_por_muro(ext).items():
        ordenados = sorted(tramos)
        for (ini_a, fin_a), (ini_b, fin_b) in zip(ordenados, ordenados[1:]):
            assert fin_a <= ini_b + 1e-9, (
                f"{texto}: dos huecos se solapan en el muro {indice}: "
                f"({ini_a:.2f},{fin_a:.2f}) y ({ini_b:.2f},{fin_b:.2f})")


@pytest.mark.parametrize("texto", [c[0] for c in CASOS])
def test_todo_el_dibujo_cabe_en_el_lienzo(texto):
    """
    El título largo se salía del `viewBox` y aparecía cortado a media palabra.
    Nada de lo que se dibuja puede quedar fuera del lienzo declarado.
    """
    svg = plano.svg_de_extraccion(plano.extraccion_desde_texto(texto), titulo=texto)
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    ancho, alto = float(m.group(1)), float(m.group(2))

    for x in re.findall(r'\sx[12]?="(-?[\d.]+)"', svg):
        assert -1 <= float(x) <= ancho + 1, f"{texto}: x={x} fuera de 0..{ancho}"
    for y in re.findall(r'\sy[12]?="(-?[\d.]+)"', svg):
        assert -1 <= float(y) <= alto + 1, f"{texto}: y={y} fuera de 0..{alto}"


def test_el_titulo_largo_se_recorta_en_vez_de_desbordarse():
    largo = "remodelacion integral del area de produccion " * 4
    svg = plano.svg_de_extraccion(
        plano.extraccion_desde_texto("area de 4 x 3 m"), titulo=largo)

    titulo = re.search(r'class="titulo"[^>]*>([^<]*)<', svg).group(1)
    assert len(titulo) < len(largo)
    assert titulo.endswith("…")


@pytest.mark.parametrize("texto", [
    "habitación de 8 x 5 m con una puerta",
    "bodega de 12 x 8 m con 4 puertas",
])
def test_el_arco_de_la_puerta_abre_hacia_dentro(texto):
    """
    El barrido de una puerta se dibuja del lado por el que se abre, y una puerta
    de fachada abre hacia el interior del recinto. Dibujado hacia fuera, el arco
    invade la cota y sugiere una hoja que no cabe.
    """
    ext = plano.extraccion_desde_texto(texto)
    svg = plano.svg_de_extraccion(ext)
    proyecta, _, _ = plano._proyector(ext.walls)
    centro_px = proyecta([0.0, 0.0])

    arcos = re.findall(r'class="arco" d="M ([\d.]+) ([\d.]+) A [\d.]+ [\d.]+ 0 0 [01] '
                       r'([\d.]+) ([\d.]+)"', svg)
    assert len(arcos) == len(ext.doors), "Falta el arco de alguna puerta"

    for x1, y1, x2, y2 in arcos:
        d_inicio = math.dist((float(x1), float(y1)), centro_px)
        d_fin = math.dist((float(x2), float(y2)), centro_px)
        assert d_fin < d_inicio, (
            f"{texto}: el arco se aleja del centro, abre hacia fuera")


# ----------------------------------------------------------------------
# 9. El agente 3D deja de mentir cuando no puede
# ----------------------------------------------------------------------

class _LlmCaido:
    """Lo que ocurre sin GROQ_API_KEY o con la clave caducada."""

    def with_structured_output(self, modelo):
        return self

    def invoke(self, _):
        raise RuntimeError("401 Unauthorized")


def test_si_el_agente_falla_pero_el_texto_trae_medidas_se_usan_esas():
    """
    El caso que motivó todo: con el agente caído, "8 x 5 m con una puerta" tiene
    que seguir dando 8x5 con una puerta. Antes daba 4x4 sin puertas.
    """
    import json as _json
    from api.paperclip_agents import architect_node

    resultado = architect_node({"levantamiento_data": CASO_DEL_DUENO}, _LlmCaido())
    escena = _json.loads(resultado["architect_data"])
    nodos = list(escena["nodes"].values())

    muros = [n for n in nodos if n["type"] == "wall"]
    largos = sorted(round(plano.largo_de_muro_xy(m["start"], m["end"]), 2) for m in muros)
    assert largos == [5.0, 5.0, 8.0, 8.0], "El respaldo no respetó las medidas del texto"
    assert len([n for n in nodos if n["type"] == "door"]) == 1
    assert resultado["architect_origen"] == "medidas"


def test_sin_medidas_y_sin_agente_la_habitacion_por_defecto_va_marcada():
    """
    Queda el respaldo 4x4 —es mejor que una pantalla vacía— pero deja de
    presentarse como si fuera el proyecto: viene con su aviso.
    """
    from api.paperclip_agents import architect_node

    resultado = architect_node(
        {"levantamiento_data": "remodelar la recepción"}, _LlmCaido())

    assert resultado["architect_origen"] == "supuesto"
    assert "4x4" in resultado["architect_aviso"]
    assert "no la del proyecto" in resultado["architect_aviso"]


# ----------------------------------------------------------------------
# 10. El contrato con el frontend
# ----------------------------------------------------------------------

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def indice() -> str:
    with open(os.path.join(RAIZ, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def adaptador() -> str:
    with open(os.path.join(RAIZ, "api_service.js"), "r", encoding="utf-8") as f:
        return f.read()


def test_el_frontend_ya_no_llama_al_generador_de_imagenes(indice):
    """
    La regresión que hay que impedir: volver a colgar el plano de un servicio de
    difusión externo. Sin clave, sin contrato, sin escala y con el navegador del
    usuario saliendo a un tercero.
    """
    assert "pollinations" not in indice.lower(), (
        "index.html volvió a pedirle el plano a un generador de imágenes")


def test_el_frontend_pide_el_plano_al_backend(indice, adaptador):
    assert "ApiService.generarPlano2D" in indice
    assert "generarPlano2D" in adaptador
    assert "/api/plano_2d" in adaptador


def test_el_endpoint_existe_en_fastapi():
    with open(os.path.join(RAIZ, "api", "main.py"), "r", encoding="utf-8") as f:
        main_py = f.read()
    assert '@app.post("/api/plano_2d")' in main_py


def test_el_boton_3d_sabe_generar_el_modelo(indice):
    """
    Antes abría el iframe vacío si nadie había pulsado la Agencia Paperclip: el
    usuario veía un editor en blanco sin ninguna explicación.
    """
    assert '@click="abrirEditor3D"' in indice
    assert "const abrirEditor3D" in indice


def test_el_plano_se_puede_descargar(indice):
    """Un plano que no se puede guardar no sirve para adjuntarlo a la orden."""
    assert "const descargarPlano2D" in indice
    assert "image/svg+xml" in indice


def test_las_referencias_del_plano_se_exponen_a_la_plantilla(indice):
    """Vue solo ve lo que `setup()` devuelve; una ref no devuelta es `undefined`."""
    for nombre in ("blueprintSvg", "blueprintOrigen", "blueprintResumen",
                   "descargarPlano2D", "abrirEditor3D"):
        assert re.search(r"return\s*\{[^}]*\b" + nombre + r"\b", indice), (
            f"`{nombre}` no se devuelve desde setup()")


def test_el_endpoint_responde_el_caso_del_dueno():
    """De punta a punta por HTTP, que es como lo usa el formulario."""
    from fastapi.testclient import TestClient

    from api.main import app

    respuesta = TestClient(app).post("/api/plano_2d",
                                     json={"descripcion": CASO_DEL_DUENO})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["origen"] == "medidas"
    assert "8.00 m" in cuerpo["svg"] and "5.00 m" in cuerpo["svg"]
    assert cuerpo["resumen"]["puertas"] == 1


def test_el_endpoint_no_revienta_cuando_no_puede():
    """Un 500 no le dice al usuario qué escribir; un mensaje sí."""
    from fastapi.testclient import TestClient

    from api.main import app

    respuesta = TestClient(app).post("/api/plano_2d",
                                     json={"descripcion": "pintar la fachada"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert "medidas" in cuerpo["message"].lower()


# ----------------------------------------------------------------------
# 11. Los bordes del módulo
# ----------------------------------------------------------------------

def test_el_plural_sin_cantidad_son_dos():
    """«con ventanas» no dice cuántas; dos es el mínimo que hace plural."""
    assert plano.cuenta_de("oficina 6 x 4 m con ventanas", "ventana") == 2


def test_no_se_colocan_mas_huecos_de_los_que_caben():
    """
    Diez puertas en un cuarto de 2x2 no caben. Se colocan las que quepan y se
    para: mejor un plano con menos vanos que uno con los muros deshechos.
    """
    ext = plano.extraccion_desde_texto("cuarto de 2 x 2 m con 10 puertas")

    assert 0 < len(ext.doors) < 10
    for d in ext.doors:
        assert d.width <= plano.largo_de_muro(ext.walls[d.wall_index])


def test_un_muro_de_largo_cero_no_dibuja_arco():
    """Defensa ante una geometría degenerada del agente: no se divide por cero."""
    assert plano._arco_de_puerta((10.0, 10.0), (10.0, 10.0), (0.0, 0.0)) == ""


@pytest.mark.parametrize("vacia", ["", "   ", None])
def test_generar_plano_sin_descripcion_lo_dice(vacia):
    resultado = plano.generar_plano(vacia)

    assert resultado["success"] is False
    assert "Descripción" in resultado["message"]


def test_un_agente_que_no_devuelve_muros_no_produce_plano():
    """Una extracción vacía no es una habitación: se pide la medida a mano."""
    from api.paperclip_agents import ArchitectExtraction

    class _LlmVacio:
        def with_structured_output(self, modelo):
            return self

        def invoke(self, _):
            return ArchitectExtraction(walls=[])

    resultado = plano.generar_plano("algo sin forma", llm=_LlmVacio())

    assert resultado["success"] is False
    assert "muro" in resultado["message"].lower()


def test_sin_clave_no_hay_llm(monkeypatch):
    """
    La falta de clave no puede tumbar el plano: devuelve `None` y el camino de
    las medidas sigue funcionando.
    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert plano.llm_disponible() is None


def test_con_clave_pero_sin_libreria_tampoco(monkeypatch):
    from api import paperclip_agents

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(paperclip_agents, "ChatGroq", None)
    assert plano.llm_disponible() is None


def test_si_el_constructor_del_llm_revienta_se_devuelve_none(monkeypatch):
    from api import paperclip_agents

    def _explota(**kwargs):
        raise RuntimeError("modelo retirado")

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(paperclip_agents, "ChatGroq", _explota)
    assert plano.llm_disponible() is None
