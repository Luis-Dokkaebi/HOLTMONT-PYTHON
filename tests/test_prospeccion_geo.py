"""
Backend de lectura del catálogo geoespacial (Fase 2 del plan de prospección).

Qué se prueba y contra qué
--------------------------
Contra un SQLite de **veinte filas construido en `tmp_path`**, nunca contra el
artefacto de 5.6 MB que viaja en `api/data/`. No es comodidad: es lo que hace
que estas pruebas puedan afirmar números exactos. Sobre el archivo real, "el
filtro de Cuauhtémoc devuelve 8" sería una cifra que cambia cada vez que el
INEGI publique, y una prueba que hay que reescribir cada semestre acaba
convertida en `assert len(items) > 0`, que no prueba nada.

Las veinte filas reproducen las patologías del archivo real, no un caso feliz:

- **Siete de veinte no tienen ningún dato de contacto.** En el DENUE real son
  7,885 de 20,957. Un establecimiento sin teléfono, correo ni web no es un
  prospecto, y el filtro tiene que saberlo.
- **`per_ocu` es un rango de texto**, no un número: `"11 a 30 personas"`. No
  existe un `per_ocu >= 11` que se pueda escribir en SQL.
- **`cod_postal` con ceros a la izquierda** (`"06010"`, `"03100"`), la trampa
  clásica del INEGI — que además nunca debe salir por la API, porque no está
  entre las 10 columnas del mapa.

Y se prueba lo que el diseño promete y no se ve en el resultado: que el archivo
se abre en **solo lectura de verdad**, que la conexión se **cachea**, y que
ningún parámetro basura produce un 500.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from api.services import denue_repo, prospeccion
from api.services.denue_repo import COLUMNAS_DEL_MAPA, RepositorioDenue

FERRETERIA = "Comercio al por menor en ferreterías y tlapalerías"
INGENIERIA = "Servicios de ingeniería"
CONCRETO = "Fabricación de concreto"

ESQUEMA = """
CREATE TABLE denue (
  id TEXT PRIMARY KEY, nom_estab TEXT, nombre_act TEXT, codigo_act TEXT,
  per_ocu TEXT, telefono TEXT, correoelec TEXT, www TEXT,
  municipio TEXT, nom_vial TEXT, numero_ext TEXT, cod_postal TEXT,
  latitud REAL, longitud REAL
);
CREATE INDEX idx_mun ON denue(municipio);
CREATE INDEX idx_act ON denue(codigo_act);
CREATE INDEX idx_geo ON denue(latitud, longitud);
"""

# id, nom_estab, nombre_act, codigo_act, per_ocu, telefono, correoelec, www,
# municipio, nom_vial, numero_ext, cod_postal, latitud, longitud
FILAS = (
    ("01", "FERRETERIA EL TORNILLO", FERRETERIA, "467111", "0 a 5 personas",
     "5512345678", None, None, "Cuauhtémoc", "REPUBLICA DE CUBA", "10", "06010", 19.4400, -99.1400),
    ("02", "MATERIALES DEL CENTRO", FERRETERIA, "467111", "6 a 10 personas",
     None, "VENTAS@MDC.MX", None, "Cuauhtémoc", "DONCELES", "22", "06020", 19.4360, -99.1360),
    ("03", "INGENIERIA DEL VALLE", INGENIERIA, "541330", "11 a 30 personas",
     None, "CONTACTO@IDV.MX", None, "Cuauhtémoc", "BUCARELI", "45", "06040", 19.4320, -99.1480),
    ("04", "CONCRETOS ROMA", CONCRETO, "327320", "31 a 50 personas",
     "5555550001", None, "WWW.CROMA.MX", "Cuauhtémoc", "ORIZABA", "9", "06700", 19.4180, -99.1600),
    ("05", "TLAPALERIA SIN TELEFONO", FERRETERIA, "467111", "0 a 5 personas",
     None, None, None, "Cuauhtémoc", "ZACATECAS", "77", "06760", 19.4100, -99.1550),
    ("06", "ESTUDIO DE INGENIERIA MUDA", INGENIERIA, "541330", "11 a 30 personas",
     None, None, None, "Cuauhtémoc", "TABASCO", "101", "06700", 19.4150, -99.1620),
    ("07", "CONCRETOS DEL NORTE", CONCRETO, "327320", "251 y más personas",
     "5555550002", None, None, "Cuauhtémoc", "EJE 1 NORTE", "300", "06900", 19.4500, -99.1300),
    ("08", "FERRETERIA NOCTURNA", FERRETERIA, "467111", "6 a 10 personas",
     None, None, "WWW.FN.MX", "Cuauhtémoc", "MOSQUETA", "5", "06300", 19.4520, -99.1420),
    ("09", "ACEROS DEL SUR", CONCRETO, "327320", "11 a 30 personas",
     "5555550003", None, None, "Benito Juárez", "EJE 8 SUR", "12", "03100", 19.3800, -99.1600),
    ("10", "INGENIERIA NAPOLES", INGENIERIA, "541330", "6 a 10 personas",
     None, "HOLA@INAP.MX", None, "Benito Juárez", "PENNSYLVANIA", "88", "03810", 19.3900, -99.1780),
    ("11", "FERRETERIA DEL VALLE", FERRETERIA, "467111", "0 a 5 personas",
     "5555550004", None, None, "Benito Juárez", "AV. COYOACAN", "1500", "03100", 19.3700, -99.1650),
    ("12", "PROYECTOS SIN CONTACTO", INGENIERIA, "541330", "31 a 50 personas",
     None, None, None, "Benito Juárez", "XOLA", "44", "03020", 19.3950, -99.1500),
    ("13", "FERRETERIA MIXCOAC", FERRETERIA, "467111", "0 a 5 personas",
     None, None, None, "Benito Juárez", "REVOLUCION", "900", "03910", 19.3750, -99.1880),
    ("14", "CONCRETOS PORTALES", CONCRETO, "327320", "6 a 10 personas",
     "5555550005", "C@CP.MX", None, "Benito Juárez", "CALZ. DE TLALPAN", "1200", "03300",
     19.3650, -99.1400),
    ("15", "INGENIERIA POLANCO", INGENIERIA, "541330", "101 a 250 personas",
     "5555550006", None, "WWW.IPOL.MX", "Miguel Hidalgo", "HORACIO", "77", "11550",
     19.4300, -99.1900),
    ("16", "FERRETERIA TACUBA", FERRETERIA, "467111", "0 a 5 personas",
     None, None, None, "Miguel Hidalgo", "CALZ. MEXICO-TACUBA", "33", "11410",
     19.4560, -99.1950),
    ("17", "MATERIALES LOMAS", FERRETERIA, "467111", "11 a 30 personas",
     None, "L@ML.MX", None, "Miguel Hidalgo", "PALOMAS", "22", "11200", 19.4200, -99.2200),
    ("18", "INGENIERIA ANZURES", INGENIERIA, "541330", "0 a 5 personas",
     "5555550007", None, None, "Miguel Hidalgo", "LEIBNITZ", "14", "11590", 19.4350, -99.1750),
    ("19", "CONCRETOS SAN JOAQUIN", CONCRETO, "327320", "51 a 100 personas",
     None, None, None, "Miguel Hidalgo", "SAN JOAQUIN", "500", "11400", 19.4450, -99.2000),
    ("20", "FERRETERIA SIN DATOS", FERRETERIA, "467111", "6 a 10 personas",
     None, None, None, "Miguel Hidalgo", "LAGO ALBERTO", "8", "11320", 19.4400, -99.1850),
)

# El polígono que dibuja el usuario sobre Miguel Hidalgo. En GeoJSON la
# longitud va primero — al revés que el bbox, que sigue el orden del INEGI.
POLIGONO_POLANCO = {
    "type": "Polygon",
    "coordinates": [[
        [-99.23, 19.41], [-99.18, 19.41], [-99.18, 19.46], [-99.23, 19.46], [-99.23, 19.41],
    ]],
}


@pytest.fixture
def catalogo_sqlite(tmp_path: pathlib.Path) -> pathlib.Path:
    """Un catálogo de veinte filas con el esquema exacto del artefacto real."""
    ruta = tmp_path / "denue.sqlite"
    conexion = sqlite3.connect(ruta)
    with conexion:
        conexion.executescript(ESQUEMA)
        conexion.executemany(
            f"INSERT INTO denue VALUES ({', '.join('?' * 14)})", FILAS)
    conexion.close()
    return ruta


@pytest.fixture
def repo(catalogo_sqlite: pathlib.Path) -> RepositorioDenue:
    repositorio = RepositorioDenue(catalogo_sqlite)
    yield repositorio
    repositorio.cerrar()


# ----------------------------------------------------------------------
# El repositorio: lo único que sabe que hay un SQLite
# ----------------------------------------------------------------------

def test_el_catalogo_se_abre_en_solo_lectura(repo: RepositorioDenue):
    """
    El artefacto viaja en el bundle y se regenera desde `ModeloGeo`. Que la
    conexión sea `mode=ro` es lo que garantiza que ningún camino del código
    pueda escribirlo, hoy o cuando alguien añada un endpoint sin pensarlo.
    """
    with pytest.raises(sqlite3.OperationalError) as error:
        repo.conexion().execute("INSERT INTO denue (id) VALUES ('99')")
    assert "readonly" in str(error.value)


def test_la_conexion_se_cachea_dentro_del_proceso(repo: RepositorioDenue):
    """
    Abrir el archivo en cada petición se paga en el arranque en frío. La segunda
    llamada tiene que devolver el mismo objeto, no uno nuevo.
    """
    assert repo.conexion() is repo.conexion()


def test_una_ruta_inexistente_no_devuelve_un_catalogo_vacio(tmp_path: pathlib.Path):
    """
    En modo `ro` SQLite no crea el archivo. Si la ruta está mal, se sabe: sin
    esto, un despliegue sin el artefacto serviría cero establecimientos y
    parecería que la Ciudad de México no tiene ferreterías.
    """
    assert denue_repo.repositorio_disponible(tmp_path / "no_existe.sqlite") is None


def test_el_repositorio_esta_disponible_cuando_el_archivo_existe(
        catalogo_sqlite: pathlib.Path):
    repositorio = denue_repo.repositorio_disponible(catalogo_sqlite)
    assert repositorio is not None
    assert repositorio.escalar("SELECT COUNT(*) FROM denue") == 20
    repositorio.cerrar()


def test_el_repositorio_se_reusa_entre_llamadas_del_mismo_proceso(
        catalogo_sqlite: pathlib.Path):
    """
    La instancia es la que sostiene la caché de conexiones: si cada petición
    construyera una nueva, la caché no existiría y el arranque en frío se
    pagaría en todas.
    """
    primera = denue_repo.repositorio_disponible(catalogo_sqlite)
    segunda = denue_repo.repositorio_disponible(catalogo_sqlite)
    assert primera is segunda
    primera.cerrar()


# ----------------------------------------------------------------------
# Catálogo
# ----------------------------------------------------------------------

def test_el_catalogo_lista_alcaldias_y_giros_ordenados(repo: RepositorioDenue):
    """Los combos salen del archivo, no de una lista escrita a mano."""
    resultado = prospeccion.catalogo(repo)
    assert resultado["success"] is True
    assert resultado["alcaldias"] == ["Benito Juárez", "Cuauhtémoc", "Miguel Hidalgo"]
    assert resultado["giros"] == sorted([FERRETERIA, INGENIERIA, CONCRETO])


def test_sin_artefacto_el_catalogo_explica_que_falta_en_vez_de_reventar():
    """
    Un despliegue sin `api/data/denue.sqlite` no puede tumbar la API entera. Es
    el mismo criterio de `plano.llm_disponible()`: degradar con un motivo
    accionable, no lanzar.
    """
    resultado = prospeccion.catalogo(None)
    assert resultado["success"] is False
    assert "construir_sqlite.py" in resultado["message"]


# ----------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------

def test_sin_filtros_devuelve_el_catalogo_entero(repo: RepositorioDenue):
    resultado = prospeccion.establecimientos(repo)
    assert (resultado["total"], resultado["mostrados"]) == (20, 20)


def test_el_filtro_por_alcaldia_recorta_a_esa_alcaldia(repo: RepositorioDenue):
    resultado = prospeccion.establecimientos(repo, alcaldia="Cuauhtémoc")
    assert resultado["total"] == 8
    assert {fila["municipio"] for fila in resultado["items"]} == {"Cuauhtémoc"}


def test_el_filtro_por_giro_admite_varios_a_la_vez(repo: RepositorioDenue):
    """El notebook usaba `SelectMultiple`: se filtra por conjunto, no por uno."""
    resultado = prospeccion.establecimientos(repo, giros=[INGENIERIA, CONCRETO])
    assert resultado["total"] == 11
    assert {fila["nombre_act"] for fila in resultado["items"]} == {INGENIERIA, CONCRETO}


def test_los_giros_repetidos_o_vacios_no_alteran_el_resultado(repo: RepositorioDenue):
    """La interfaz puede mandar duplicados y cadenas vacías; el conjunto es el mismo."""
    resultado = prospeccion.establecimientos(
        repo, giros=[INGENIERIA, INGENIERIA, "", "   ", INGENIERIA])
    assert resultado["total"] == 6


def test_personal_min_filtra_por_el_piso_del_rango(repo: RepositorioDenue):
    """
    `per_ocu` es texto (`"11 a 30 personas"`). Se incluyen los rangos cuyo piso
    llega al mínimo: un negocio de `"6 a 10 personas"` puede tener 8, pero nadie
    puede afirmar que tiene 11, así que queda fuera.
    """
    resultado = prospeccion.establecimientos(repo, personal_min=11)
    assert resultado["total"] == 9
    assert "6 a 10 personas" not in {fila["per_ocu"] for fila in resultado["items"]}


def test_solo_con_contacto_descarta_a_quien_no_se_puede_llamar(repo: RepositorioDenue):
    """
    La regla de negocio del módulo: un establecimiento sin teléfono, sin correo
    y sin web no es un prospecto. Siete de las veinte filas están en ese caso.
    """
    resultado = prospeccion.establecimientos(repo, solo_con_contacto=True)
    assert resultado["total"] == 13
    for fila in resultado["items"]:
        assert fila["telefono"] or fila["correoelec"] or fila["www"]


def test_los_proveedores_grandes_con_contacto_son_el_cruce_de_los_dos_filtros(
        repo: RepositorioDenue):
    """
    El cruce que produce la lista que compras recorre de verdad. Sobre el archivo
    real este mismo cruce da 1,972 de 20,957; aquí, 6 de 20.
    """
    resultado = prospeccion.establecimientos(repo, personal_min=11, solo_con_contacto=True)
    assert resultado["total"] == 6
    assert [fila["id"] for fila in resultado["items"]] == ["03", "04", "07", "09", "15", "17"]


def test_los_filtros_se_combinan_en_un_solo_and(repo: RepositorioDenue):
    resultado = prospeccion.establecimientos(
        repo, alcaldia="Miguel Hidalgo", giros=[FERRETERIA], solo_con_contacto=True)
    assert [fila["id"] for fila in resultado["items"]] == ["17"]


# ----------------------------------------------------------------------
# Bbox
# ----------------------------------------------------------------------

def test_el_bbox_recorta_a_la_vista_del_mapa(repo: RepositorioDenue):
    """
    El mapa pide lo que cabe en pantalla. La caja elegida cubre exactamente las
    seis filas de Benito Juárez.
    """
    resultado = prospeccion.establecimientos(repo, bbox="19.36,-99.19,19.40,-99.14")
    assert resultado["total"] == 6
    assert {fila["municipio"] for fila in resultado["items"]} == {"Benito Juárez"}


def test_el_bbox_se_combina_con_los_demas_filtros(repo: RepositorioDenue):
    resultado = prospeccion.establecimientos(
        repo, bbox="19.36,-99.19,19.40,-99.14", solo_con_contacto=True)
    assert [fila["id"] for fila in resultado["items"]] == ["09", "10", "11", "14"]


def test_un_bbox_de_tres_numeros_no_devuelve_la_ciudad_entera(repo: RepositorioDenue):
    """
    Servir toda la ciudad cuando el mapa pidió una manzana es el fallo caro: el
    navegador dibuja 20,957 marcadores y nadie entiende por qué. Se rechaza con
    el motivo.
    """
    resultado = prospeccion.establecimientos(repo, bbox="19.36,-99.19,19.40")
    assert resultado["success"] is False
    assert "cuatro números" in resultado["message"]
    assert "items" not in resultado


def test_un_bbox_con_texto_se_rechaza_con_el_motivo(repo: RepositorioDenue):
    resultado = prospeccion.establecimientos(repo, bbox="norte,sur,este,oeste")
    assert resultado["success"] is False
    assert "cuatro números" in resultado["message"]


def test_un_bbox_invertido_se_rechaza_en_vez_de_devolver_cero(repo: RepositorioDenue):
    """
    `BETWEEN 19.5 AND 19.3` no falla: devuelve cero filas. Un mapa vacío se lee
    como "aquí no hay negocios", que es una respuesta falsa.
    """
    resultado = prospeccion.establecimientos(repo, bbox="19.50,-99.10,19.30,-99.30")
    assert resultado["success"] is False
    assert "invertido" in resultado["message"]


def test_un_bbox_vacio_equivale_a_no_filtrar(repo: RepositorioDenue):
    assert prospeccion.establecimientos(repo, bbox="")["total"] == 20
    assert prospeccion.establecimientos(repo, bbox=None)["total"] == 20


# ----------------------------------------------------------------------
# Paginación y límites
# ----------------------------------------------------------------------

def test_la_paginacion_avanza_sin_repetir_ni_saltarse_filas(repo: RepositorioDenue):
    """`ORDER BY id` fija el orden: sin él, `OFFSET` puede repetir u omitir."""
    primera = prospeccion.establecimientos(repo, limite=5)
    segunda = prospeccion.establecimientos(repo, limite=5, desplazamiento=5)
    assert [f["id"] for f in primera["items"]] == ["01", "02", "03", "04", "05"]
    assert [f["id"] for f in segunda["items"]] == ["06", "07", "08", "09", "10"]


def test_total_y_mostrados_son_numeros_distintos_cuando_hay_recorte(repo: RepositorioDenue):
    """
    El notebook cortaba en 2,000 marcadores sin avisar. Aquí el recorte se
    declara: 20 cumplen, 5 se muestran.
    """
    resultado = prospeccion.establecimientos(repo, limite=5)
    assert (resultado["total"], resultado["mostrados"]) == (20, 5)


def test_el_desplazamiento_mas_alla_del_final_devuelve_lista_vacia(repo: RepositorioDenue):
    resultado = prospeccion.establecimientos(repo, desplazamiento=500)
    assert (resultado["total"], resultado["mostrados"], resultado["items"]) == (20, 0, [])


@pytest.mark.parametrize("basura", [0, -5, "muchas", "", None, [1, 2]])
def test_un_limite_absurdo_cae_al_valor_por_defecto(basura):
    """
    `limite` no lo teclea nadie: lo manda el mapa. Un valor imposible es un error
    del cliente que no debe dejar al usuario sin mapa.
    """
    assert prospeccion.acotar_limite(basura) == prospeccion.LIMITE_POR_DEFECTO


def test_un_limite_fraccionario_se_trunca_en_vez_de_descartarse(repo: RepositorioDenue):
    """
    `3.7` no es basura: es una cifra con parte decimal, y "3 filas" es su lectura
    obvia. Descartarla y devolver 500 filas sería peor que truncarla.
    """
    assert prospeccion.acotar_limite(3.7) == 3
    assert prospeccion.establecimientos(repo, limite=3.7)["mostrados"] == 3


def test_el_limite_tiene_techo_duro(repo: RepositorioDenue):
    """El techo protege al servidor de un cliente que pida el catálogo entero."""
    assert prospeccion.acotar_limite(999_999) == prospeccion.LIMITE_MAXIMO
    assert prospeccion.establecimientos(repo, limite=999_999)["mostrados"] == 20


@pytest.mark.parametrize("basura", [-1, "atras", None])
def test_un_desplazamiento_absurdo_se_lee_como_el_principio(basura):
    assert prospeccion.acotar_desplazamiento(basura) == 0


def test_personal_min_ilegible_no_filtra_nada(repo: RepositorioDenue):
    """Un `personal_min` que no es un número no puede convertirse en cero filas."""
    assert prospeccion.establecimientos(repo, personal_min="grandes")["total"] == 20


# ----------------------------------------------------------------------
# El contrato de salida
# ----------------------------------------------------------------------

def test_cada_item_lleva_las_diez_columnas_del_mapa_y_ninguna_mas(repo: RepositorioDenue):
    """
    El DENUE tiene 42 columnas y el SQLite 14. Por la API salen 10. Una fila
    completa son ~1.5 KB: 3,000 marcadores serían 4.5 MB de JSON por paneo.
    """
    item = prospeccion.establecimientos(repo, limite=1)["items"][0]
    assert tuple(item.keys()) == COLUMNAS_DEL_MAPA
    assert len(COLUMNAS_DEL_MAPA) == 10


def test_no_se_filtran_columnas_de_domicilio_por_la_api(repo: RepositorioDenue):
    """
    `cod_postal`, `nom_vial` y `numero_ext` están en el SQLite —los necesita la
    ficha impresa— pero no en la respuesta del mapa.
    """
    item = prospeccion.establecimientos(repo, limite=1)["items"][0]
    for columna in ("cod_postal", "nom_vial", "numero_ext", "codigo_act"):
        assert columna not in item


def test_sin_artefacto_los_establecimientos_degradan_con_motivo():
    resultado = prospeccion.establecimientos(None)
    assert resultado["success"] is False
    assert "denue.sqlite" in resultado["message"]


# ----------------------------------------------------------------------
# Selección por polígono
# ----------------------------------------------------------------------

def test_la_seleccion_devuelve_solo_lo_que_cae_dentro_del_poligono(repo: RepositorioDenue):
    """
    Es el `gdf.geometry.within(poligono)` del notebook, sin GeoPandas ni Shapely.
    El polígono cubre Polanco y deja fuera Anzures (`18`), que queda al este.
    """
    resultado = prospeccion.seleccion(repo, POLIGONO_POLANCO)
    assert resultado["success"] is True
    assert [fila["id"] for fila in resultado["items"]] == ["15", "16", "17", "19", "20"]


def test_la_seleccion_acepta_el_feature_que_manda_leaflet_draw(repo: RepositorioDenue):
    """`Leaflet.draw` envuelve la geometría en un `Feature`; las dos formas valen."""
    feature = {"type": "Feature", "properties": {}, "geometry": POLIGONO_POLANCO}
    assert prospeccion.seleccion(repo, feature)["total"] == 5


def test_la_seleccion_aplica_tambien_los_filtros_de_negocio(repo: RepositorioDenue):
    """Dibujar un polígono no anula la regla de "solo prospectos contactables"."""
    resultado = prospeccion.seleccion(repo, POLIGONO_POLANCO, solo_con_contacto=True)
    assert [fila["id"] for fila in resultado["items"]] == ["15", "17"]


def test_geojson_pone_la_longitud_primero_y_el_bbox_la_latitud(repo: RepositorioDenue):
    """
    La confusión clásica. Si se leyera el GeoJSON como `(lat, lon)`, el polígono
    de Polanco caería en el Índico y la selección saldría vacía sin error.
    """
    anillo = prospeccion.anillo_de_geojson(POLIGONO_POLANCO)
    assert anillo[0] == (-99.23, 19.41)
    assert prospeccion.punto_dentro(-99.19, 19.43, anillo) is True
    assert prospeccion.punto_dentro(19.43, -99.19, anillo) is False


def test_un_poligono_de_dos_vertices_se_rechaza(repo: RepositorioDenue):
    dos_puntos = {"type": "Polygon", "coordinates": [[[-99.2, 19.4], [-99.1, 19.4]]]}
    resultado = prospeccion.seleccion(repo, dos_puntos)
    assert resultado["success"] is False
    assert "tres vértices" in resultado["message"]


def test_una_geometria_que_no_es_poligono_se_rechaza(repo: RepositorioDenue):
    punto = {"type": "Point", "coordinates": [-99.2, 19.4]}
    resultado = prospeccion.seleccion(repo, punto)
    assert resultado["success"] is False
    assert "Polygon" in resultado["message"]


@pytest.mark.parametrize("basura", ["un polígono", 42, None, {"type": "Polygon"}])
def test_una_seleccion_con_basura_no_revienta(repo: RepositorioDenue, basura):
    resultado = prospeccion.seleccion(repo, basura)
    assert resultado["success"] is False
    assert resultado["message"]


def test_un_poligono_con_vertices_ilegibles_se_rechaza(repo: RepositorioDenue):
    """
    `Leaflet.draw` manda pares de números. Un vértice con texto, o con un solo
    valor, es un cliente roto: se dice, no se interpreta a medias.
    """
    torcido = {"type": "Polygon",
               "coordinates": [[[-99.2, 19.4], ["norte", 19.4], [-99.1, "sur"]]]}
    resultado = prospeccion.seleccion(repo, torcido)
    assert resultado["success"] is False
    assert "ilegibles" in resultado["message"]


def test_sin_artefacto_la_seleccion_degrada_con_motivo():
    assert prospeccion.seleccion(None, POLIGONO_POLANCO)["success"] is False


# ----------------------------------------------------------------------
# Las rutas HTTP (R9: el contrato que ve el frontend)
# ----------------------------------------------------------------------
#
# Con `TestClient` y el catálogo apuntado al SQLite de veinte filas. Lo que se
# prueba aquí no es la lógica —ya está probada arriba— sino la traducción de la
# query string: que `giros` repetido llegue como lista, que `solo_con_contacto`
# se lea como booleano y que un parámetro inválido devuelva 200 con
# `success: false` en vez de un 500 que el frontend no sabe mostrar.

@pytest.fixture
def cliente(catalogo_sqlite: pathlib.Path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setattr(denue_repo, "RUTA_CATALOGO", catalogo_sqlite)
    monkeypatch.setattr(denue_repo, "_repositorio", None)
    with TestClient(app) as cliente_http:
        yield cliente_http
    monkeypatch.setattr(denue_repo, "_repositorio", None)


def test_la_ruta_del_catalogo_responde_con_alcaldias_y_giros(cliente):
    respuesta = cliente.get("/api/geo/catalogo")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["alcaldias"] == ["Benito Juárez", "Cuauhtémoc", "Miguel Hidalgo"]


def test_la_ruta_de_establecimientos_traduce_los_filtros_de_la_query(cliente):
    """`giros` repetido tiene que llegar al servicio como lista, no como cadena."""
    respuesta = cliente.get(
        "/api/geo/establecimientos",
        params=[("giros", INGENIERIA), ("giros", CONCRETO), ("solo_con_contacto", "true")])
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 8
    assert {fila["nombre_act"] for fila in cuerpo["items"]} == {INGENIERIA, CONCRETO}


def test_la_ruta_devuelve_las_diez_columnas_del_mapa(cliente):
    """R9: el frontend pinta con estas claves. Si cambian, el mapa se queda mudo."""
    cuerpo = cliente.get("/api/geo/establecimientos", params={"limite": 1}).json()
    assert tuple(cuerpo["items"][0].keys()) == COLUMNAS_DEL_MAPA


def test_un_bbox_invalido_no_devuelve_500_por_la_ruta(cliente):
    """
    Un 500 en el navegador es "algo se rompió". Un `success: false` con motivo es
    "el bbox tiene que traer cuatro números", que el usuario puede corregir.
    """
    respuesta = cliente.get("/api/geo/establecimientos", params={"bbox": "1,2,3"})
    assert respuesta.status_code == 200
    assert respuesta.json()["success"] is False


def test_sin_el_artefacto_desplegado_la_ruta_lo_dice(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from api.main import app

    monkeypatch.setattr(denue_repo, "RUTA_CATALOGO", tmp_path / "no_existe.sqlite")
    monkeypatch.setattr(denue_repo, "_repositorio", None)
    with TestClient(app) as cliente_http:
        cuerpo = cliente_http.get("/api/geo/catalogo").json()
    assert cuerpo["success"] is False
    assert "construir_sqlite.py" in cuerpo["message"]
