"""
Prospección geoespacial: el catálogo del DENUE convertido en reglas de negocio.

Qué resuelve
------------
El equipo de compras necesita, sobre un mapa de la Ciudad de México, la lista de
proveedores de la cadena de valor de la construcción que puede recorrer de
verdad: filtrada por alcaldía, por giro, por tamaño y —la condición que manda—
**con al menos un dato de contacto**. De los 20,957 establecimientos del DENUE,
13,072 traen teléfono, correo o sitio web; los otros 7,885 no son prospectos,
son puntos en un mapa.

Cómo está armado
----------------
Este módulo no sabe que existe un SQLite. Recibe el repositorio inyectado —el
mismo patrón con el que `api/services/plano.py` recibe su `llm` de
`llm_disponible()`— y con eso se prueba entero contra una base de veinte filas
construida en `tmp_path`, sin red, sin credenciales y sin cargar el artefacto de
5.6 MB.

Tres reglas de contrato que no son obvias y que las pruebas fijan:

1. **Salen 10 columnas, nunca 42.** Ver `denue_repo.COLUMNAS_DEL_MAPA`.
2. **`personal_min` filtra por el piso del rango.** El DENUE no publica la
   plantilla exacta sino un rango de texto (`"11 a 30 personas"`). Se incluyen
   los rangos cuyo **piso** alcanza el mínimo pedido, que es la lectura
   conservadora: un negocio declarado como `"6 a 10 personas"` puede tener 8,
   pero nadie puede afirmar que tiene 11.
3. **Nunca lanza 500.** Un parámetro basura devuelve `success: false` con el
   motivo, igual que `/api/plano_2d`. Un mapa que se queda en blanco sin decir
   por qué es peor que uno que dice "el bbox tiene que traer cuatro números".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from api.services.denue_repo import COLUMNAS_DEL_MAPA

# Cuántos establecimientos se devuelven si nadie pide un número, y el techo
# duro. 3,000 es lo que se midió que el mapa dibuja con soltura usando
# clustering; por encima de eso el navegador es el cuello de botella, no la
# consulta (el bbox con índice tarda 10.7 ms para 3,000 filas).
LIMITE_POR_DEFECTO = 500
LIMITE_MAXIMO = 3000

# El DENUE de construcción tiene 99 giros en total. Una petición con más que eso
# no puede venir de la interfaz, y una lista sin tope se acerca al máximo de
# variables por sentencia de SQLite (999 por defecto).
MAXIMO_GIROS = 99

# Los rangos de plantilla del DENUE, con el piso de cada uno. El campo es texto,
# no un número: no existe un `per_ocu >= 11` que se pueda escribir en SQL.
RANGOS_PERSONAL: Tuple[Tuple[str, int], ...] = (
    ("0 a 5 personas", 0),
    ("6 a 10 personas", 6),
    ("11 a 30 personas", 11),
    ("31 a 50 personas", 31),
    ("51 a 100 personas", 51),
    ("101 a 250 personas", 101),
    ("251 y más personas", 251),
)

# Un prospecto es alguien a quien se puede contactar. Sin esto la lista tiene
# 20,957 nombres y ninguna forma de llamar a 7,885 de ellos.
CONDICION_CONTACTO = "(telefono IS NOT NULL OR correoelec IS NOT NULL OR www IS NOT NULL)"

_SELECCION = ", ".join(COLUMNAS_DEL_MAPA)

_SIN_CATALOGO = {
    "success": False,
    "message": "El catálogo del DENUE no está disponible en este despliegue "
               "(falta api/data/denue.sqlite). Se genera con scripts/construir_sqlite.py "
               "del repositorio ModeloGeo.",
}


def _sin_catalogo() -> Dict[str, Any]:
    return dict(_SIN_CATALOGO)


# ----------------------------------------------------------------------
# Saneado de parámetros — todos vienen de la barra de direcciones
# ----------------------------------------------------------------------

def acotar_limite(limite: Any) -> int:
    """
    Cuántas filas devolver: entre 1 y `LIMITE_MAXIMO`.

    Se acota en vez de rechazar porque `limite` no lo teclea nadie, lo manda el
    mapa. Un valor absurdo (`0`, `-5`, `"muchas"`, `99999`) es un error del
    cliente que no debe dejar al usuario sin mapa; el techo es lo que protege al
    servidor.
    """
    try:
        valor = int(limite)
    except (TypeError, ValueError):
        return LIMITE_POR_DEFECTO
    if valor <= 0:
        return LIMITE_POR_DEFECTO
    return min(valor, LIMITE_MAXIMO)


def acotar_desplazamiento(desplazamiento: Any) -> int:
    """Página desde la que se lee. Negativo o ilegible se lee como el principio."""
    try:
        valor = int(desplazamiento)
    except (TypeError, ValueError):
        return 0
    return max(0, valor)


def rangos_desde(personal_min: Any) -> List[str]:
    """
    Los rangos de `per_ocu` cuyo piso alcanza `personal_min`.

    `11` devuelve los cinco rangos de 11 personas en adelante — los 2,278
    establecimientos que, cruzados con la condición de contacto, dan los 1,972
    proveedores que publica el README de `ModeloGeo`.
    """
    try:
        minimo = int(personal_min)
    except (TypeError, ValueError):
        return []
    return [etiqueta for etiqueta, piso in RANGOS_PERSONAL if piso >= minimo]


def bbox_desde(bbox: Any) -> Optional[Tuple[float, float, float, float]]:
    """
    `"19.3,-99.25,19.55,-99.0"` -> `(lat_min, lon_min, lat_max, lon_max)`.

    Orden de INEGI y de Leaflet (`latitud` primero), no el de GeoJSON. `None`
    significa "sin recorte"; un texto ilegible **lanza**, porque servir toda la
    ciudad cuando el mapa pidió una manzana es peor que un mensaje de error.
    """
    if bbox is None or (isinstance(bbox, str) and not bbox.strip()):
        return None
    partes = str(bbox).split(",") if isinstance(bbox, str) else list(bbox)
    if len(partes) != 4:
        raise ValueError("El bbox tiene que traer cuatro números: "
                         "lat_min,lon_min,lat_max,lon_max.")
    try:
        lat_min, lon_min, lat_max, lon_max = (float(p) for p in partes)
    except (TypeError, ValueError):
        raise ValueError("El bbox tiene que traer cuatro números: "
                         "lat_min,lon_min,lat_max,lon_max.") from None
    if lat_min > lat_max or lon_min > lon_max:
        raise ValueError("El bbox está invertido: el mínimo no puede ser mayor que el máximo.")
    return (lat_min, lon_min, lat_max, lon_max)


def _giros_saneados(giros: Any) -> List[str]:
    """Lista de giros sin vacíos ni repetidos, con tope. Preserva el orden."""
    if not giros:
        return []
    vistos: Dict[str, None] = {}
    for crudo in giros:
        texto = str(crudo).strip()
        if texto:
            vistos.setdefault(texto, None)
    return list(vistos)[:MAXIMO_GIROS]


# ----------------------------------------------------------------------
# Construcción del WHERE
# ----------------------------------------------------------------------

def _condiciones_de_atributo(alcaldia: Any, giros: Any, personal_min: Any,
                             solo_con_contacto: Any) -> Tuple[List[str], List[Any]]:
    """Filtros sobre columnas indexadas o de texto. Todo por marcador `?`."""
    condiciones: List[str] = []
    parametros: List[Any] = []

    if alcaldia and str(alcaldia).strip():
        condiciones.append("municipio = ?")
        parametros.append(str(alcaldia).strip())

    lista_giros = _giros_saneados(giros)
    if lista_giros:
        condiciones.append(f"nombre_act IN ({', '.join('?' * len(lista_giros))})")
        parametros.extend(lista_giros)

    rangos = rangos_desde(personal_min)
    if rangos:
        condiciones.append(f"per_ocu IN ({', '.join('?' * len(rangos))})")
        parametros.extend(rangos)

    if solo_con_contacto:
        condiciones.append(CONDICION_CONTACTO)

    return condiciones, parametros


def _condiciones_de_bbox(bbox: Any) -> Tuple[List[str], List[Any]]:
    """El recorte del mapa. `BETWEEN` sobre `latitud, longitud` usa `idx_geo`."""
    caja = bbox_desde(bbox)
    if caja is None:
        return [], []
    lat_min, lon_min, lat_max, lon_max = caja
    return (["latitud BETWEEN ? AND ?", "longitud BETWEEN ? AND ?"],
            [lat_min, lat_max, lon_min, lon_max])


def _clausula_where(condiciones: Sequence[str]) -> str:
    return f" WHERE {' AND '.join(condiciones)}" if condiciones else ""


# ----------------------------------------------------------------------
# Lo que consumen los endpoints
# ----------------------------------------------------------------------

def catalogo(repositorio: Any) -> Dict[str, Any]:
    """
    Las 16 alcaldías y los 99 giros que existen en el catálogo, para los combos.

    Salen del propio archivo y no de una lista escrita a mano: si el INEGI
    publica un giro nuevo, el combo lo tiene el día que se regenera el artefacto,
    sin tocar código.
    """
    if repositorio is None:
        return _sin_catalogo()
    alcaldias = repositorio.consultar(
        "SELECT DISTINCT municipio FROM denue WHERE municipio IS NOT NULL ORDER BY municipio")
    giros = repositorio.consultar(
        "SELECT DISTINCT nombre_act FROM denue WHERE nombre_act IS NOT NULL ORDER BY nombre_act")
    return {
        "success": True,
        "alcaldias": [fila["municipio"] for fila in alcaldias],
        "giros": [fila["nombre_act"] for fila in giros],
    }


def establecimientos(repositorio: Any, alcaldia: Any = None, giros: Any = None,
                     personal_min: Any = None, solo_con_contacto: Any = False,
                     bbox: Any = None, limite: Any = None,
                     desplazamiento: Any = 0) -> Dict[str, Any]:
    """
    Los establecimientos que pasan los filtros, recortados al límite pedido.

    `total` son los que cumplen (sin recorte) y `mostrados` los que van en
    `items`. Los dos números por separado son lo que deja al mapa decir "3,000
    de 8,412": con uno solo, el usuario no sabe si está viendo todo o una parte,
    que es exactamente el error del notebook —cortaba en 2,000 marcadores sin
    avisar—.
    """
    if repositorio is None:
        return _sin_catalogo()
    try:
        condiciones, parametros = _condiciones_de_atributo(
            alcaldia, giros, personal_min, solo_con_contacto)
        condiciones_bbox, parametros_bbox = _condiciones_de_bbox(bbox)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    where = _clausula_where(condiciones + condiciones_bbox)
    todos = parametros + parametros_bbox

    total = repositorio.escalar(f"SELECT COUNT(*) FROM denue{where}", todos)
    tope = acotar_limite(limite)
    salto = acotar_desplazamiento(desplazamiento)
    items = repositorio.consultar(
        f"SELECT {_SELECCION} FROM denue{where} ORDER BY id LIMIT ? OFFSET ?",
        todos + [tope, salto])

    return {"success": True, "total": int(total or 0), "mostrados": len(items), "items": items}


# ----------------------------------------------------------------------
# Selección por polígono
# ----------------------------------------------------------------------

def anillo_de_geojson(poligono: Any) -> List[Tuple[float, float]]:
    """
    El anillo exterior de un GeoJSON, como pares `(longitud, latitud)`.

    Acepta un `Polygon`, un `Feature` que lo envuelva o la geometría suelta que
    manda `Leaflet.draw`. **GeoJSON escribe la longitud primero**, al revés que
    el DENUE y que Leaflet: es la confusión clásica y aquí se resuelve en un
    solo sitio, no en cada llamada.
    """
    if isinstance(poligono, dict) and "geometry" in poligono:
        poligono = poligono["geometry"]
    if not isinstance(poligono, dict):
        raise ValueError("El polígono tiene que ser un objeto GeoJSON.")
    if str(poligono.get("type", "")).lower() != "polygon":
        raise ValueError("Solo se admite una geometría de tipo Polygon.")

    coordenadas = poligono.get("coordinates") or []
    anillo = coordenadas[0] if coordenadas else []
    try:
        puntos = [(float(par[0]), float(par[1])) for par in anillo]
    except (TypeError, ValueError, IndexError):
        raise ValueError("El polígono trae vértices ilegibles.") from None
    if len(puntos) < 3:
        raise ValueError("Un polígono necesita al menos tres vértices.")
    return puntos


def punto_dentro(longitud: float, latitud: float,
                 anillo: Sequence[Tuple[float, float]]) -> bool:
    """
    Punto en polígono por lanzamiento de rayo, sin dependencias.

    Es el `gdf.geometry.within(poligono)` del notebook —que arrastraba GeoPandas
    y Shapely— reducido a lo único que hace falta aquí. El rayo va hacia +∞ en X
    y cuenta cruces: impar dentro, par fuera.
    """
    dentro = False
    total = len(anillo)
    for i in range(total):
        x1, y1 = anillo[i]
        x2, y2 = anillo[(i + 1) % total]
        if (y1 > latitud) == (y2 > latitud):
            continue
        corte = x1 + (latitud - y1) * (x2 - x1) / (y2 - y1)
        if longitud < corte:
            dentro = not dentro
    return dentro


def _caja_del_anillo(anillo: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    """La caja que envuelve al polígono, en el orden del bbox (latitud primero)."""
    longitudes = [p[0] for p in anillo]
    latitudes = [p[1] for p in anillo]
    return (min(latitudes), min(longitudes), max(latitudes), max(longitudes))


def seleccion(repositorio: Any, poligono: Any, personal_min: Any = None,
              solo_con_contacto: Any = False, limite: Any = None) -> Dict[str, Any]:
    """
    Los establecimientos dentro del polígono dibujado, para exportar.

    Dos pasos, y el orden importa: primero SQL recorta por la caja del polígono
    —que usa `idx_geo` y descarta el 99% de las filas sin mirar geometría— y
    solo después se prueba punto en polígono sobre lo que quedó. Al revés serían
    20,957 pruebas geométricas en Python por cada trazo del usuario.
    """
    if repositorio is None:
        return _sin_catalogo()
    try:
        anillo = anillo_de_geojson(poligono)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    lat_min, lon_min, lat_max, lon_max = _caja_del_anillo(anillo)
    candidatos = establecimientos(
        repositorio, personal_min=personal_min, solo_con_contacto=solo_con_contacto,
        bbox=(lat_min, lon_min, lat_max, lon_max), limite=LIMITE_MAXIMO)
    if not candidatos.get("success"):
        return candidatos

    dentro = [fila for fila in candidatos["items"]
              if punto_dentro(fila["longitud"], fila["latitud"], anillo)]
    tope = acotar_limite(limite)
    return {"success": True, "total": len(dentro), "mostrados": len(dentro[:tope]),
            "items": dentro[:tope]}
