"""
Lectura de las hojas de ventas desde el esquema relacional.

Cubre los defectos reales que tenía el adaptador `api/services/sheets.py` al
reconstruir la forma de hoja a partir de la tabla `quotes`:

  1. `QUOTE_HEADER_MAP` apuntaba a `prio_cot`, una columna que no existe en el
     esquema (la real es `prioridad_cot`), y omitía `MONTO`, que el frontend
     espera en toda hoja de ventas (`DEFAULT_SALES_HEADERS` en CODIGO.js).
  2. El filtro por `source_sheet` comparaba con igualdad exacta, y los nombres
     almacenados no están normalizados. Cinco de las siete hojas de ventas
     devolvían cero filas.
  3. `str(valor or "")` convertía el 0 en cadena vacía, borrando el avance de
     198 cotizaciones al 0 %.

No requieren base de datos: se inyecta un doble de `sb_manager`.

Ejecución:  python -m pytest tests/test_ventas_columns.py -v
"""

import pytest

from api.services import sheets


# Nombres tal como están realmente guardados en `quotes.source_sheet`:
# capitalización mixta y, en `tasks`, alguna hoja con espacio inicial.
SOURCE_SHEETS_REALES = [
    "ANTONIA_VENTAS",
    "Sebastian Padilla (VENTAS)",
    "Eduardo Manzanares (VENTAS)",
    "TERESA GARZA (VENTAS)",
]


class FakeSupabase:
    """Doble mínimo de `sb_manager` con datos con la forma de los reales."""

    def __init__(self, quotes=None, tasks=None):
        self._quotes = quotes or []
        self._tasks = tasks or []
        self.consultas = []

    def select(self, table, filters=None):
        self.consultas.append((table, dict(filters or {})))
        filas = self._quotes if table == "quotes" else self._tasks if table == "tasks" else []
        if not filters:
            return list(filas)
        return [f for f in filas if all(f.get(k) == v for k, v in filters.items())]

    def select_distinct(self, table, column):
        filas = self._quotes if table == "quotes" else self._tasks if table == "tasks" else []
        vistos, salida = set(), []
        for f in filas:
            v = f.get(column)
            if v is not None and v not in vistos:
                vistos.add(v)
                salida.append({column: v})
        return salida

    def get_sheet_values(self, sheet_name):
        return []


def cotizacion(**campos):
    """Fila de `quotes` con todas las columnas que el adaptador consulta."""
    base = {col: None for _, col in sheets.QUOTE_HEADER_MAP}
    base["source_sheet"] = "ANTONIA_VENTAS"
    base.update(campos)
    return base


@pytest.fixture
def fake(monkeypatch):
    def instalar(quotes=None, tasks=None):
        doble = FakeSupabase(quotes, tasks)
        monkeypatch.setattr(sheets, "sb_manager", doble)
        monkeypatch.setattr(sheets.gs_manager, "is_mock", True, raising=False)
        sheets.reset_source_sheet_cache()
        return doble
    yield instalar
    sheets.reset_source_sheet_cache()


def encabezados(valores):
    return list(valores[0])


def fila_como_dict(valores, indice=1):
    return dict(zip(valores[0], valores[indice]))


# ----------------------------------------------------------------------
# 1. Columnas expuestas
# ----------------------------------------------------------------------

def test_el_mapa_solo_referencia_columnas_que_existen():
    """
    `PRIO. COT.` apuntaba a `prio_cot`, inexistente en el esquema, así que la
    columna salía siempre vacía pese a tener datos en la base.
    """
    columnas_reales = {
        "folio", "area", "cliente", "concepto", "clasificacion", "vendedor_id",
        "vendedor_raw", "f_visita", "f_inicio", "f_entrega", "dias", "avance",
        "estatus", "comentarios", "requisitor", "prioridad_cot", "info_cliente",
        "f2", "cotizacion", "timeline", "layout", "proceso", "proceso_log",
        "map_cot", "monto", "source_sheet", "extra", "created_at", "archivo",
        "fecha", "comentario", "estatus_2", "fecha_envio", "dias_2",
        "llamada_cliente", "reloj", "completada",
    }
    invalidas = [(h, c) for h, c in sheets.QUOTE_HEADER_MAP if c not in columnas_reales]
    assert not invalidas, f"El mapa referencia columnas inexistentes: {invalidas}"


def test_se_exponen_las_columnas_que_el_frontend_espera():
    """DEFAULT_SALES_HEADERS de CODIGO.js es el contrato de una hoja de ventas."""
    expuestos = {h.upper().replace(".", "").replace(" ", "") for h, _ in sheets.QUOTE_HEADER_MAP}
    for requerido in ["FOLIO", "CLIENTE", "CONCEPTO", "VENDEDOR", "ESTATUS",
                      "COMENTARIOS", "MONTO", "F2", "COTIZACION", "TIMELINE",
                      "LAYOUT", "AVANCE"]:
        clave = requerido.replace(".", "").replace(" ", "")
        assert clave in expuestos, f"El frontend espera {requerido} y no se expone"


def test_prioridad_cot_llega_con_su_valor(fake):
    doble = fake(quotes=[cotizacion(folio="AV-0161", prioridad_cot="URGENTE")])
    fila = fila_como_dict(sheets.gs_manager.get_sheet_values("ANTONIA_VENTAS"))
    assert fila["PRIO. COT."] == "URGENTE"


def test_se_exponen_las_columnas_del_timeline_de_cotizacion(fake):
    """`MAP COT` y `PROCESO_LOG` alimentan la vista de Papa Caliente."""
    fake(quotes=[cotizacion(folio="AV-1", map_cot="L,CD", proceso_log='[{"step":"L"}]')])
    fila = fila_como_dict(sheets.gs_manager.get_sheet_values("ANTONIA_VENTAS"))
    assert fila["MAP COT"] == "L,CD"
    assert fila["PROCESO_LOG"] == '[{"step":"L"}]'


# ----------------------------------------------------------------------
# 2. Resolución del nombre de hoja
# ----------------------------------------------------------------------

@pytest.mark.parametrize("pedido,esperado", [
    ("SEBASTIAN PADILLA (VENTAS)", "Sebastian Padilla (VENTAS)"),
    ("sebastian padilla (ventas)", "Sebastian Padilla (VENTAS)"),
    ("EDUARDO MANZANARES (VENTAS)", "Eduardo Manzanares (VENTAS)"),
    ("TERESA GARZA (VENTAS)", "TERESA GARZA (VENTAS)"),
    ("ANTONIA_VENTAS", "ANTONIA_VENTAS"),
])
def test_el_nombre_de_hoja_se_resuelve_sin_distinguir_mayusculas(fake, pedido, esperado):
    fake(quotes=[cotizacion(source_sheet=s) for s in SOURCE_SHEETS_REALES])
    assert sheets.resolve_source_sheet("quotes", pedido) == esperado


def test_hojas_de_ventas_con_capitalizacion_distinta_devuelven_sus_filas(fake):
    """
    Regresión: el frontend pide en mayúsculas y la base guarda capitalización
    mixta, así que cinco de las siete hojas de ventas salían vacías.
    """
    fake(quotes=[
        cotizacion(folio="SP-1", source_sheet="Sebastian Padilla (VENTAS)"),
        cotizacion(folio="SP-2", source_sheet="Sebastian Padilla (VENTAS)"),
        cotizacion(folio="AV-1", source_sheet="ANTONIA_VENTAS"),
    ])
    valores = sheets.gs_manager.get_sheet_values("SEBASTIAN PADILLA (VENTAS)")
    assert valores is not None and len(valores) - 1 == 2


def test_las_hojas_con_espacio_inicial_se_encuentran(fake):
    """Hay hojas reales cuyo nombre empieza con espacio."""
    fake(tasks=[{"folio": "LM-1", "source_sheet": " LILIANA AYLIN MARTINEZ IBARRA"}])
    assert sheets.resolve_source_sheet(
        "tasks", "LILIANA AYLIN MARTINEZ IBARRA"
    ) == " LILIANA AYLIN MARTINEZ IBARRA"


def test_una_hoja_desconocida_se_consulta_tal_cual(fake):
    """Sin coincidencia no se inventa una hoja: se consulta lo pedido."""
    fake(quotes=[cotizacion(source_sheet="ANTONIA_VENTAS")])
    assert sheets.resolve_source_sheet("quotes", "HOJA QUE NO EXISTE") == "HOJA QUE NO EXISTE"


# ----------------------------------------------------------------------
# 3. Serialización de celdas
# ----------------------------------------------------------------------

@pytest.mark.parametrize("valor,esperado", [
    (0, "0"),          # el bug: `0 or ""` -> ""
    (0.0, "0"),        # numeric de Postgres
    (45.0, "45"),      # sin decimal sobrante
    (45.5, "45.5"),
    (None, ""),
    ("", ""),
    ("TEXTO", "TEXTO"),
    (True, "SI"),
    (False, "NO"),
])
def test_celda_preserva_el_cero_y_limpia_los_flotantes(valor, esperado):
    assert sheets._celda(valor) == esperado


def test_un_avance_de_cero_no_se_muestra_vacio(fake):
    """
    Regresión: 198 cotizaciones están al 0 % y la vista las mostraba en blanco,
    como si nadie hubiera capturado el dato.
    """
    fake(quotes=[cotizacion(folio="AV-0189", avance=0.0, dias=3)])
    fila = fila_como_dict(sheets.gs_manager.get_sheet_values("ANTONIA_VENTAS"))
    assert fila["AVANCE"] == "0"
    assert fila["DIAS"] == "3"


def test_los_encabezados_no_se_duplican():
    nombres = [h for h, _ in sheets.QUOTE_HEADER_MAP]
    assert len(nombres) == len(set(nombres)), "Hay encabezados repetidos en QUOTE_HEADER_MAP"
