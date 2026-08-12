"""
El Plano 2D de la Pre Work Order: geometría, no ilustración.

Por qué existe este módulo
--------------------------
El botón "Plano 2D (IA)" llamaba desde el navegador a `image.pollinations.ai`,
un servicio de difusión texto→imagen. Lo que devolvía se parecía a un plano,
pero era un dibujo: sin escala, sin cotas, distinto en cada intento y sin
relación con el modelo que abre el Editor 3D. Para una orden de trabajo que
acaba en obra, un plano con medidas inventadas es peor que no tener plano.

Aquí el plano se **construye** a partir de la misma geometría que alimenta el
editor 3D (`api.paperclip_agents.ArchitectExtraction`), de modo que las dos
vistas no puedan discrepar: son la misma habitación mirada de dos maneras.

La lectura de la descripción tiene dos caminos, en este orden:

1. **Medidas explícitas** (`extraccion_desde_texto`). "8 x 5 m con una puerta"
   se resuelve leyendo el texto, sin LLM: determinista, instantáneo y disponible
   aunque la clave del agente esté caída. Cubre la forma en que se escribe el
   campo en la práctica.
2. **El agente** (`generar_plano` con `llm`), para los levantamientos en prosa
   que el paso 1 no sabe leer.

Lo que **no** se hace nunca es inventar una habitación por defecto cuando los
dos caminos fallan. `architect_node` devolvía una 4x4 m sin puertas y el
frontend la anunciaba como éxito: pedir 8x5 con puerta y recibir 4x4 sin puerta
sin ningún aviso es el fallo más caro de todos, porque nadie lo revisa.
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from html import escape
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api.paperclip_agents import (
    ArchitectExtraction,
    DoorOpening,
    WallSegment,
    WindowOpening,
    _build_pascal_scene,
)

# Medidas fuera de este rango no son una habitación: son un folio, un importe o
# un código de partida que casualmente lleva una "x" en medio.
MEDIDA_MINIMA_M = 0.3
MEDIDA_MAXIMA_M = 200.0

ALTURA_POR_DEFECTO_M = 2.5
ALTURA_MAXIMA_M = 30.0

ANCHO_PUERTA_M = 0.9
ALTO_PUERTA_M = 2.1
ANCHO_VENTANA_M = 1.2
ALTO_VENTANA_M = 1.0
ALFEIZAR_M = 0.9

# Proporción máxima del muro que puede ocupar un hueco. Un vano que se come el
# muro entero deja la esquina sin apoyo en el 3D y sin trazo en el 2D.
FRACCION_MAXIMA_HUECO = 0.8

NUMEROS_ESCRITOS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

# Orden en que se reparten los huecos entre los cuatro muros. Las puertas
# empiezan por el muro frontal (0) y las ventanas por los laterales, que es la
# convención de cualquier levantamiento: se entra por el frente y se ilumina por
# los lados.
ORDEN_MUROS_PUERTA = (0, 2, 1, 3)
ORDEN_MUROS_VENTANA = (1, 3, 0, 2)


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _normalizar(texto: Any) -> str:
    return _sin_acentos(str("" if texto is None else texto)).lower()


def _a_float(crudo: str) -> float:
    """`"10,5"` y `"10.5"` son el mismo número: aquí se escribe de las dos formas."""
    return float(crudo.replace(",", "."))


def _medida_valida(valor: float) -> bool:
    return MEDIDA_MINIMA_M <= valor <= MEDIDA_MAXIMA_M


# El separador puede ser `x`, `×` o la palabra `por`, con unidad opcional en
# medio ("8 m x 5 m"). `por` va con límites de palabra para no partir "porton".
_PATRON_MEDIDAS = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m|mt|mts|metros?)?\s*(?:x|×|\bpor\b)\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

_PATRON_ALTURA = re.compile(
    r"(?:altura|alto|altura de|techo de|h)\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*(?:m|mt|mts|metros?)\b"
    r"|(\d+(?:[.,]\d+)?)\s*(?:m|mt|mts|metros?)\s*de\s*(?:altura|alto)",
    re.IGNORECASE,
)


def medidas_de_texto(texto: Any) -> Optional[Tuple[float, float]]:
    """
    `"habitación de 8 x 5 m"` -> `(8.0, 5.0)`; sin medidas legibles -> `None`.

    `None` no es un fallo: significa "esto lo tiene que leer el agente". Lo que
    no hace nunca es devolver una medida inventada.
    """
    plano_txt = _normalizar(texto)
    if not plano_txt:
        return None
    for coincidencia in _PATRON_MEDIDAS.finditer(plano_txt):
        ancho, largo = _a_float(coincidencia.group(1)), _a_float(coincidencia.group(2))
        if _medida_valida(ancho) and _medida_valida(largo):
            return (ancho, largo)
    return None


def altura_de_texto(texto: Any) -> float:
    """Altura libre mencionada en la descripción, o la de siempre (2.5 m)."""
    coincidencia = _PATRON_ALTURA.search(_normalizar(texto))
    if coincidencia:
        crudo = coincidencia.group(1) or coincidencia.group(2)
        valor = _a_float(crudo)
        if MEDIDA_MINIMA_M <= valor <= ALTURA_MAXIMA_M:
            return valor
    return ALTURA_POR_DEFECTO_M


def cuenta_de(texto: Any, sustantivo: str) -> int:
    """
    Cuántas puertas (o ventanas) pide la descripción.

    Entiende la cifra (`"2 puertas"`), la palabra (`"dos puertas"`) y el
    singular sin cantidad (`"con puerta"` = 1). `"sin puertas"` es 0, y se
    comprueba primero: sin eso, "sin ventanas" contaría una por el singular.
    """
    plano_txt = _normalizar(texto)
    palabra = _sin_acentos(sustantivo).lower()

    # La negación se encadena con "ni": en "sin puertas ni ventanas" las dos
    # están negadas. Solo se sigue la cadena por "ni" — "sin acceso y con dos
    # ventanas" no niega las ventanas.
    for negacion in re.finditer(r"\bsin\s+\w+(?:\s+ni\s+\w+)*", plano_txt):
        if re.search(rf"\b{palabra}s?\b", negacion.group(0)):
            return 0

    escritos = "|".join(NUMEROS_ESCRITOS)
    con_cantidad = re.search(
        rf"\b(\d+|{escritos})\s+{palabra}s?\b", plano_txt)
    if con_cantidad:
        crudo = con_cantidad.group(1)
        return int(crudo) if crudo.isdigit() else NUMEROS_ESCRITOS[crudo]

    if re.search(rf"\b{palabra}s\b", plano_txt):
        return 2  # plural sin cantidad: al menos dos
    if re.search(rf"\b{palabra}\b", plano_txt):
        return 1
    return 0


def largo_de_muro_xy(inicio: Sequence[float], fin: Sequence[float]) -> float:
    return math.hypot(fin[0] - inicio[0], fin[1] - inicio[1])


def largo_de_muro(muro: WallSegment) -> float:
    return largo_de_muro_xy(muro.start, muro.end)


def _muros_rectangulares(ancho: float, largo: float) -> List[WallSegment]:
    """
    Rectángulo centrado en el origen, recorrido en sentido antihorario.

    Centrado porque es lo que ya hacía `_default_room_scene` y lo que espera el
    editor 3D al encuadrar la cámara; cerrado porque cuatro muros que no cierran
    no son una habitación.
    """
    mx, my = ancho / 2.0, largo / 2.0
    esquinas = [(-mx, -my), (mx, -my), (mx, my), (-mx, my)]
    return [
        WallSegment(start=[esquinas[i][0], esquinas[i][1]],
                    end=[esquinas[(i + 1) % 4][0], esquinas[(i + 1) % 4][1]])
        for i in range(4)
    ]


def _ancho_util(muro: WallSegment, deseado: float) -> float:
    return min(deseado, largo_de_muro(muro) * FRACCION_MAXIMA_HUECO)


# Separación mínima entre dos vanos del mismo muro, en fracción del muro. Sin
# ella dos huecos pueden quedar pegados y leerse como uno solo.
HOLGURA_ENTRE_HUECOS = 0.02


def _posiciones_candidatas():
    """
    Centro primero, luego cuartos, sextos… Es el orden en que un proyectista
    coloca vanos: el primero al centro y los siguientes repartidos a los lados.
    """
    for denominador in (2, 4, 6, 8, 10, 12):
        for numerador in range(1, denominador, 2):
            yield numerador / denominador


def _hay_sitio(ocupados: Sequence[Tuple[float, float]],
               tramo: Tuple[float, float]) -> bool:
    inicio, fin = tramo
    return all(fin <= ini - HOLGURA_ENTRE_HUECOS or inicio >= f + HOLGURA_ENTRE_HUECOS
               for ini, f in ocupados)


def _colocar_hueco(muros: Sequence[WallSegment], ocupados: Dict[int, List[Tuple[float, float]]],
                   orden: Sequence[int], intento: int,
                   ancho_deseado: float) -> Optional[Tuple[int, float, float]]:
    """
    Sitio libre para un vano: `(muro, posición, ancho)`, o `None` si no cabe.

    Puertas y ventanas comparten el registro `ocupados`, que es la corrección de
    fondo: repartidas por separado, una ventana caía justo encima de una puerta
    —los dos al centro de su muro— y el plano dibujaba un trazo sobre otro
    mientras el 3D abría dos huecos solapados.
    """
    total = len(muros)
    for salto in range(total):
        indice = orden[(intento + salto) % len(orden)] % total
        muro = muros[indice]
        ancho = _ancho_util(muro, ancho_deseado)
        for posicion in _posiciones_candidatas():
            tramo = _tramo_del_hueco(muro, posicion, ancho)
            if _hay_sitio(ocupados.get(indice, []), tramo):
                ocupados.setdefault(indice, []).append(tramo)
                return (indice, posicion, ancho)
    return None


def extraccion_desde_texto(texto: Any) -> Optional[ArchitectExtraction]:
    """
    La geometría que describe el texto, o `None` si no trae medidas legibles.

    Es el camino sin LLM: cubre las descripciones con medidas, que son la
    mayoría, y es el que sostiene el plano cuando el agente no está disponible.
    """
    medidas = medidas_de_texto(texto)
    if not medidas:
        return None

    ancho, largo = medidas
    muros = _muros_rectangulares(ancho, largo)

    # Un solo registro para los dos tipos: las puertas se colocan antes porque
    # son el acceso —mandan sobre la fachada— y las ventanas se acomodan en lo
    # que queda libre.
    ocupados: Dict[int, List[Tuple[float, float]]] = {}

    puertas = []
    for i in range(cuenta_de(texto, "puerta")):
        sitio = _colocar_hueco(muros, ocupados, ORDEN_MUROS_PUERTA, i, ANCHO_PUERTA_M)
        if sitio is None:
            break
        indice, posicion, ancho_hueco = sitio
        puertas.append(DoorOpening(wall_index=indice, position_along_wall=posicion,
                                   width=ancho_hueco, height=ALTO_PUERTA_M))

    ventanas = []
    for i in range(cuenta_de(texto, "ventana")):
        sitio = _colocar_hueco(muros, ocupados, ORDEN_MUROS_VENTANA, i, ANCHO_VENTANA_M)
        if sitio is None:
            break
        indice, posicion, ancho_hueco = sitio
        ventanas.append(WindowOpening(wall_index=indice, position_along_wall=posicion,
                                      width=ancho_hueco, height=ALTO_VENTANA_M,
                                      sill_height=ALFEIZAR_M))

    return ArchitectExtraction(
        walls=muros,
        ceiling_height=altura_de_texto(texto),
        doors=puertas,
        windows=ventanas,
    )


# ----------------------------------------------------------------------
# El dibujo
# ----------------------------------------------------------------------

MARGEN_PX = 70.0
ESCALA_PX_POR_M = 40.0
GROSOR_MURO_PX = 6.0
# Ancho medio de un carácter del título a 14 px. Sirve para recortarlo al
# lienzo; no hace falta más precisión porque solo decide dónde cortar.
ANCHO_MEDIO_CARACTER_PX = 7.4

_ESTILO = """
  .fondo { fill: #ffffff; }
  .muro { stroke: #111827; stroke-width: %(grosor).1f; stroke-linecap: square; }
  .puerta { stroke: #b45309; stroke-width: %(grosor).1f; stroke-linecap: butt; }
  .arco { fill: none; stroke: #b45309; stroke-width: 1; stroke-dasharray: 4 3; }
  .ventana { stroke: #1d4ed8; stroke-width: %(grosor).1f; stroke-linecap: butt; }
  .cota { stroke: #6b7280; stroke-width: 1; }
  .texto { font-family: system-ui, sans-serif; font-size: 13px; fill: #374151; }
  .titulo { font-family: system-ui, sans-serif; font-size: 14px; fill: #111827; font-weight: 600; }
""" % {"grosor": GROSOR_MURO_PX}


def _proyector(muros: Sequence[WallSegment]):
    """Convierte metros a píxeles. El eje Y se invierte: en SVG crece hacia abajo."""
    xs = [p[0] for m in muros for p in (m.start, m.end)]
    ys = [p[1] for m in muros for p in (m.start, m.end)]
    min_x, max_y = min(xs), max(ys)

    def proyecta(punto: Sequence[float]) -> Tuple[float, float]:
        return (MARGEN_PX + (punto[0] - min_x) * ESCALA_PX_POR_M,
                MARGEN_PX + (max_y - punto[1]) * ESCALA_PX_POR_M)

    ancho = (max(xs) - min_x) * ESCALA_PX_POR_M + 2 * MARGEN_PX
    alto = (max_y - min(ys)) * ESCALA_PX_POR_M + 2 * MARGEN_PX
    return proyecta, ancho, alto


def _punto_en_muro(muro: WallSegment, t: float) -> Tuple[float, float]:
    return (muro.start[0] + (muro.end[0] - muro.start[0]) * t,
            muro.start[1] + (muro.end[1] - muro.start[1]) * t)


def _tramo_del_hueco(muro: WallSegment, posicion: float, ancho: float) -> Tuple[float, float]:
    """Los dos extremos del vano, en fracción del muro, recortados a [0, 1]."""
    largo = largo_de_muro(muro) or 1.0
    mitad = (ancho / largo) / 2.0
    return (max(0.0, posicion - mitad), min(1.0, posicion + mitad))


def _titulo_recortado(titulo: str, ancho_px: float) -> str:
    """
    El título cabe en el lienzo o se recorta con puntos suspensivos.

    Es la descripción que escribió el usuario y puede tener cualquier largo; sin
    recorte se salía del `viewBox` y se leía cortado a media palabra.
    """
    limpio = " ".join(titulo.split())
    cabe = max(12, int((ancho_px - 2 * MARGEN_PX) / ANCHO_MEDIO_CARACTER_PX))
    if len(limpio) <= cabe:
        return limpio
    return limpio[:cabe - 1].rstrip() + "…"


def _centroide(muros: Sequence[WallSegment]) -> Tuple[float, float]:
    """El centro del recinto, que es el lado por el que abren las puertas."""
    puntos = [p for m in muros for p in (m.start, m.end)]
    return (sum(p[0] for p in puntos) / len(puntos),
            sum(p[1] for p in puntos) / len(puntos))


def _arco_de_puerta(bisagra: Tuple[float, float], extremo: Tuple[float, float],
                    centro: Tuple[float, float]) -> str:
    """
    El barrido de la hoja, dibujado SIEMPRE hacia el interior del recinto.

    Antes el arco se trazaba hacia arriba en pantalla, sin mirar dónde estaba el
    muro: en el muro superior salía fuera del recinto, pisaba la cota y sugería
    una hoja que se abre a la calle. Aquí la normal se elige por el lado en el
    que queda el centro del espacio.
    """
    dx, dy = extremo[0] - bisagra[0], extremo[1] - bisagra[1]
    radio = math.hypot(dx, dy)
    if radio == 0:
        return ""
    ux, uy = dx / radio, dy / radio

    medio = ((bisagra[0] + extremo[0]) / 2.0, (bisagra[1] + extremo[1]) / 2.0)
    hacia_centro = (centro[0] - medio[0], centro[1] - medio[1])
    normal = (-uy, ux)
    if normal[0] * hacia_centro[0] + normal[1] * hacia_centro[1] < 0:
        normal = (uy, -ux)

    destino = (bisagra[0] + normal[0] * radio, bisagra[1] + normal[1] * radio)
    # `sweep` en el sistema de pantalla (Y hacia abajo): 1 gira en el sentido
    # de las agujas del reloj.
    sweep = 1 if (ux * normal[1] - uy * normal[0]) > 0 else 0
    return (f'<path class="arco" d="M {extremo[0]:.1f} {extremo[1]:.1f} '
            f'A {radio:.1f} {radio:.1f} 0 0 {sweep} '
            f'{destino[0]:.1f} {destino[1]:.1f}" />')


def svg_de_extraccion(extraccion: ArchitectExtraction, titulo: str = "") -> str:
    """
    El plano en SVG: muros a escala, vanos en su sitio y las cotas reales.

    Autocontenido y sin scripts — se inyecta en el DOM de la aplicación, así que
    no puede traer código ni pedir nada a un tercero. El título lo escribe el
    usuario y va escapado.
    """
    muros = list(extraccion.walls)
    proyecta, ancho_px, alto_px = _proyector(muros)
    centro_px = proyecta(_centroide(muros))
    partes: List[str] = []

    huecos_por_muro: Dict[int, List[Tuple[float, float, str]]] = {}
    for puerta in extraccion.doors:
        inicio, fin = _tramo_del_hueco(
            muros[puerta.wall_index], puerta.position_along_wall, puerta.width)
        huecos_por_muro.setdefault(puerta.wall_index, []).append((inicio, fin, "puerta"))
    for ventana in extraccion.windows:
        inicio, fin = _tramo_del_hueco(
            muros[ventana.wall_index], ventana.position_along_wall, ventana.width)
        huecos_por_muro.setdefault(ventana.wall_index, []).append((inicio, fin, "ventana"))

    # Cada muro se dibuja entero y encima va el vano en su color: el trazo del
    # hueco tapa el del muro, que es como se lee un plano de arquitectura.
    for muro in muros:
        (x1, y1), (x2, y2) = proyecta(muro.start), proyecta(muro.end)
        partes.append(
            f'<line class="muro" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" />')

    for indice, huecos in sorted(huecos_por_muro.items()):
        muro = muros[indice]
        for inicio, fin, clase in huecos:
            (x1, y1) = proyecta(_punto_en_muro(muro, inicio))
            (x2, y2) = proyecta(_punto_en_muro(muro, fin))
            partes.append(
                f'<line class="{clase}" x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}" />')
            if clase == "puerta":
                partes.append(_arco_de_puerta((x1, y1), (x2, y2), centro_px))

    partes.extend(_cotas(muros, proyecta, alto_px, ancho_px))

    encabezado = ""
    if titulo:
        encabezado = (f'<text class="titulo" x="{MARGEN_PX:.1f}" y="26">'
                      f'{escape(_titulo_recortado(str(titulo), ancho_px))}</text>')

    cuerpo = "\n  ".join(partes)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho_px:.1f} {alto_px:.1f}" '
        f'width="100%" role="img" aria-label="Plano 2D a escala">\n'
        f'  <style>{_ESTILO}</style>\n'
        f'  <rect class="fondo" x="0" y="0" width="{ancho_px:.1f}" height="{alto_px:.1f}" />\n'
        f'  {encabezado}\n  {cuerpo}\n</svg>'
    )


def _cotas(muros: Sequence[WallSegment], proyecta, alto_px: float,
           ancho_px: float) -> List[str]:
    """
    Las medidas escritas: la horizontal debajo y la vertical a la izquierda.

    Es lo que distingue un plano de un dibujo bonito, y lo que faltaba por
    completo en la imagen que devolvía el generador anterior.
    """
    xs = [p[0] for m in muros for p in (m.start, m.end)]
    ys = [p[1] for m in muros for p in (m.start, m.end)]
    ancho_m, largo_m = max(xs) - min(xs), max(ys) - min(ys)

    (izq_x, _), (der_x, _) = proyecta([min(xs), 0]), proyecta([max(xs), 0])
    (_, arriba_y), (_, abajo_y) = proyecta([0, max(ys)]), proyecta([0, min(ys)])
    y_cota = abajo_y + 32
    x_cota = izq_x - 34

    return [
        f'<line class="cota" x1="{izq_x:.1f}" y1="{y_cota:.1f}" '
        f'x2="{der_x:.1f}" y2="{y_cota:.1f}" />',
        f'<text class="texto" x="{(izq_x + der_x) / 2:.1f}" y="{y_cota + 18:.1f}" '
        f'text-anchor="middle">{ancho_m:.2f} m</text>',
        f'<line class="cota" x1="{x_cota:.1f}" y1="{arriba_y:.1f}" '
        f'x2="{x_cota:.1f}" y2="{abajo_y:.1f}" />',
        f'<text class="texto" x="{x_cota - 6:.1f}" y="{(arriba_y + abajo_y) / 2:.1f}" '
        f'text-anchor="middle" transform="rotate(-90 {x_cota - 6:.1f} '
        f'{(arriba_y + abajo_y) / 2:.1f})">{largo_m:.2f} m</text>',
    ]


# ----------------------------------------------------------------------
# Lo que consume el endpoint
# ----------------------------------------------------------------------

def _extraccion_con_agente(descripcion: str, llm: Any) -> ArchitectExtraction:
    """La lectura en prosa. Deja subir la excepción: quien llama decide qué decir."""
    from api.paperclip_agents import _validate_and_fix_extraction

    estructurado = llm.with_structured_output(ArchitectExtraction)
    return _validate_and_fix_extraction(estructurado.invoke(descripcion))


def llm_disponible() -> Any:
    """
    El LLM estructurado del proyecto, o `None` si no está configurado.

    Devolver `None` en vez de lanzar es deliberado: la falta de clave no puede
    tumbar el plano, porque el camino de las medidas no la necesita. Solo
    limita: sin clave se resuelven las descripciones con medidas y se dice
    claramente que las demás no.
    """
    from api import paperclip_agents

    clave = os.environ.get("GROQ_API_KEY")
    if not clave or paperclip_agents.ChatGroq is None:
        return None
    try:
        return paperclip_agents.ChatGroq(
            model="llama-3.3-70b-versatile", temperature=0.2, api_key=clave)
    except Exception as exc:  # noqa: BLE001
        print(f"[plano] No se pudo construir el LLM: {exc}")
        return None


def generar_plano(descripcion: Any, llm: Any = None) -> Dict[str, Any]:
    """
    El plano 2D y la escena 3D de una descripción, o el motivo de no poder.

    `origen` dice de dónde salió la geometría —`"medidas"` si se leyó del texto,
    `"agente"` si la interpretó el LLM— porque no es lo mismo un plano con las
    medidas que escribió el usuario que uno inferido de una frase, y quien lo
    firma tiene derecho a saberlo.

    Nunca devuelve una habitación por defecto: si no se pudo, `success` es
    `False` y `message` explica qué falta.
    """
    texto = str("" if descripcion is None else descripcion).strip()
    if not texto:
        return {"success": False, "message":
                "Escribe la Descripción del Trabajo a Realizar antes de generar el plano."}

    extraccion = extraccion_desde_texto(texto)
    origen = "medidas"

    if extraccion is None:
        if llm is None:
            return {"success": False, "message":
                    "No se encontraron medidas en la descripción. Escríbelas como "
                    "«8 x 5 m» (el agente de IA no está disponible para deducirlas)."}
        try:
            extraccion = _extraccion_con_agente(texto, llm)
            origen = "agente"
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "message":
                    f"El agente no pudo interpretar la descripción ({exc}). "
                    f"Escribe las medidas como «8 x 5 m» y vuelve a intentarlo."}
        if not extraccion.walls:
            return {"success": False, "message":
                    "El agente no encontró ningún muro en la descripción. "
                    "Escribe las medidas como «8 x 5 m»."}

    escena = _build_pascal_scene(
        extraccion.walls, extraccion.ceiling_height, extraccion.doors,
        extraccion.windows, extraccion.staircases, extraccion.roof,
        extraccion.furniture, extraccion.num_levels)

    return {
        "success": True,
        "origen": origen,
        "svg": svg_de_extraccion(extraccion, titulo=texto.splitlines()[0][:90]),
        "escena_3d": escena,
        "resumen": {
            "muros": len(extraccion.walls),
            "puertas": len(extraccion.doors),
            "ventanas": len(extraccion.windows),
            "altura_m": extraccion.ceiling_height,
        },
    }
