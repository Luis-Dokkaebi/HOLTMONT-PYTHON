"""
Paridad con REAL-HOLTMONT: las piezas migradas en la revisión del 2026-07-30.

Cada bloque de aquí corresponde a una función de `CODIGO.js` que en este repo
no tenía equivalente o lo tenía divergente. La referencia es siempre el
original, así que las aserciones citan la línea de allá cuando el valor exacto
importa (el formato del folio, el nombre de la carpeta de mes).

Lo que se cubre:

* `generateWorkOrderFolio` — las 3 abreviaturas de departamento que faltaban.
* `processQuoteRow` — el nombre de la carpeta de mes, con el número delante.
* `archiveFile` — archivar dos veces no puede renombrar el archivo.
* `batchArchiveExistingQuotes` — el lote y su tolerancia a filas incompletas.
* `incrementarContadorDias` — a qué hojas llega, qué escribe y qué no reescribe.
* `generateNumericSequence` — el candado que evita dos folios iguales.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import storage  # noqa: E402
from api.services import tracker_rules as rules  # noqa: E402
from api.services import tracker_store  # noqa: E402
from api.services.work_order import generate_work_order_folio  # noqa: E402


# ======================================================================
# generateWorkOrderFolio: ABBR_MAP completo
# ======================================================================

@pytest.mark.parametrize("departamento, esperado", [
    # Las tres que faltaban (CODIGO.js:4193-4195). Sin ellas, FINANZAS caía al
    # truncado de 5 letras y salía "Finan"; FACTURACION salía "Factu".
    ("FINANZAS", "Finanzas"),
    ("FACTURACION", "Factura"),
    ("FACTURACIÓN", "Factura"),
    # Un par de las que ya estaban, para que la prueba también detecte una
    # regresión al agregar las nuevas.
    ("ELECTROMECANICA", "Electro"),
    ("SEGURIDAD", "EHS"),
])
def test_el_folio_de_wo_usa_la_abreviatura_del_original(departamento, esperado):
    folio = generate_work_order_folio("ACME INDUSTRIAL", departamento)
    assert f" {esperado} " in folio, folio


def test_un_departamento_fuera_del_mapa_sigue_cayendo_al_truncado():
    """El fallback no cambió: sigue siendo primera letra + 4 en minúscula."""
    folio = generate_work_order_folio("ACME INDUSTRIAL", "TOPOGRAFIA")
    assert " Topog " in folio, folio


# ======================================================================
# processQuoteRow: la carpeta de mes lleva el número delante
# ======================================================================

def test_la_carpeta_de_mes_lleva_numero_como_en_drive():
    """
    `processQuoteRow` escribe "03 - MARZO", no "MARZO". El número es lo que hace
    que el banco se liste en orden cronológico y no alfabético.
    """
    assert storage.carpeta_de_archivo("ACME", datetime(2026, 3, 4)) == "2026/03 - MARZO/ACME"
    assert storage.carpeta_de_archivo(None, datetime(2026, 1, 9)) == "2026/01 - ENERO"
    assert storage.carpeta_de_archivo(None, datetime(2026, 12, 31)) == "2026/12 - DICIEMBRE"


def test_los_doce_meses_estan_numerados_y_en_orden():
    assert len(storage.MESES) == 12
    for i, mes in enumerate(storage.MESES, start=1):
        assert mes.startswith(f"{i:02d} - "), mes
    # Ordenar alfabéticamente la lista tiene que dar el orden del calendario:
    # es exactamente la propiedad por la que el original pone el número.
    assert sorted(storage.MESES) == list(storage.MESES)


# ======================================================================
# archiveFile: idempotente y sin renombrar
# ======================================================================

class _AlmacenFalso:
    """Lo justo de la API de Storage que usa `archivar_cotizacion`."""

    def __init__(self):
        self.movimientos = []

    def move(self, origen, destino):
        self.movimientos.append((origen, destino))

    def get_public_url(self, ruta):
        return f"https://x.supabase.co/storage/v1/object/public/archivos/{ruta}"


@pytest.fixture
def almacen(monkeypatch):
    falso = _AlmacenFalso()

    class _Storage:
        def from_(self, _bucket):
            return falso

    class _Cliente:
        storage = _Storage()

    class _Manager:
        is_configured = True
        client = _Cliente()

    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _Manager())
    return falso


def _url(ruta):
    return f"https://x.supabase.co/storage/v1/object/public/archivos/{ruta}"


def test_archivar_conserva_el_nombre_del_archivo(almacen):
    """
    Antes el destino se calculaba con `ruta_de_archivo`, que pega una marca de
    tiempo nueva: cada archivado renombraba el objeto. `archiveFile` solo lo
    mueve.
    """
    res = storage.archivar_cotizacion(
        _url("2026/03 - MARZO/plano-111.dwg"), "ACME", datetime(2026, 3, 4))
    assert res["success"]
    assert res["path"] == "2026/03 - MARZO/ACME/plano-111.dwg"
    assert almacen.movimientos == [
        ("2026/03 - MARZO/plano-111.dwg", "2026/03 - MARZO/ACME/plano-111.dwg")]


def test_archivar_dos_veces_no_mueve_nada_la_segunda(almacen):
    """
    El "Already there" del original. Es lo que permite correr el lote a diario:
    sin esto, cada corrida movía y renombraba los 4.600 archivos otra vez.
    """
    primera = storage.archivar_cotizacion(
        _url("2026/03 - MARZO/plano-111.dwg"), "ACME", datetime(2026, 3, 4))
    segunda = storage.archivar_cotizacion(
        _url(primera["path"]), "ACME", datetime(2026, 3, 4))

    assert segunda["success"] and segunda["movido"] is False
    assert segunda["path"] == primera["path"]
    assert len(almacen.movimientos) == 1  # solo la primera movió


def test_una_url_ajena_al_bucket_no_se_toca(almacen):
    res = storage.archivar_cotizacion("https://drive.google.com/file/d/abc", "ACME")
    assert res["success"] is False
    assert almacen.movimientos == []


# ======================================================================
# processQuoteRow / batchArchiveExistingQuotes
# ======================================================================

def test_una_fila_sin_cliente_fecha_o_archivo_se_salta(almacen):
    """`"Missing Data"` del original: no es un error, es una fila que no aplica."""
    for fila in [
        {"CLIENTE": "", "FECHA": "04/03/2026", "COTIZACION": _url("a/b.pdf")},
        {"CLIENTE": "ACME", "FECHA": "", "COTIZACION": _url("a/b.pdf")},
        {"CLIENTE": "ACME", "FECHA": "04/03/2026", "COTIZACION": ""},
    ]:
        res = storage.archivar_fila_cotizacion(fila)
        assert res["success"] is False and res["message"] == "Missing Data"
    assert almacen.movimientos == []


def test_una_fila_archiva_todas_sus_urls(almacen):
    """
    El campo de archivo puede traer varias URLs separadas por salto de línea,
    espacio o coma; el original archiva cada una.
    """
    fila = {
        "CLIENTE": "ACME INDUSTRIAL",
        "F. INICIO": "04/03/2026",
        "COTIZACION": (_url("2026/03 - MARZO/uno-1.pdf") + "\n"
                       + _url("2026/03 - MARZO/dos-2.pdf")),
    }
    res = storage.archivar_fila_cotizacion(fila)
    assert res["success"] and res["processed"] == 2
    destinos = [d for _, d in almacen.movimientos]
    assert destinos == ["2026/03 - MARZO/ACME INDUSTRIAL/uno-1.pdf",
                        "2026/03 - MARZO/ACME INDUSTRIAL/dos-2.pdf"]


def test_una_url_con_espacios_no_se_trocea():
    """
    El original parte también por espacios, pero sus URLs de Drive no los tienen.
    Las nuestras sí (`2026/03 - MARZO/ACME INDUSTRIAL/...`), y partir por espacio
    dejaba solo `.../2026/03` — se archivaba una ruta truncada.
    """
    una = _url("2026/03 - MARZO/ACME INDUSTRIAL/plano-1.pdf")
    assert storage.separar_urls(una) == [una]

    otra = _url("2026/04 - ABRIL/BETA SA/plano-2.pdf")
    # Separadas por espacio, por salto de línea y por coma: los tres casos del
    # original siguen funcionando.
    assert storage.separar_urls(f"{una} {otra}") == [una, otra]
    assert storage.separar_urls(f"{una}\n{otra}") == [una, otra]
    assert storage.separar_urls(f"{una},{otra}") == [una, otra]
    assert storage.separar_urls("") == []
    assert storage.separar_urls("pendiente de subir") == []


def test_una_url_escapada_resuelve_a_la_clave_literal():
    """
    `get_public_url` puede devolver los espacios como `%20`; la API de Storage
    espera la clave literal, así que un `move` sobre la forma escapada apuntaría
    a un objeto inexistente.
    """
    escapada = _url("2026/03%20-%20MARZO/ACME%20INDUSTRIAL/plano-1.pdf")
    assert storage._ruta_desde_url(escapada) == "2026/03 - MARZO/ACME INDUSTRIAL/plano-1.pdf"
    # Y sin escapar sigue dando lo mismo.
    literal = _url("2026/03 - MARZO/ACME INDUSTRIAL/plano-1.pdf")
    assert storage._ruta_desde_url(literal) == "2026/03 - MARZO/ACME INDUSTRIAL/plano-1.pdf"


def test_lo_que_no_es_http_no_se_intenta_archivar(almacen):
    fila = {"CLIENTE": "ACME", "FECHA": "04/03/2026", "COTIZACION": "pendiente de subir"}
    res = storage.archivar_fila_cotizacion(fila)
    assert res["success"] is False and res["message"] == "Missing Data"


def test_una_fecha_ilegible_no_archiva_en_una_carpeta_inventada(almacen):
    fila = {"CLIENTE": "ACME", "FECHA": "el mes pasado",
            "COTIZACION": _url("2026/03 - MARZO/uno-1.pdf")}
    res = storage.archivar_fila_cotizacion(fila)
    assert res["success"] is False and res["message"] == "Invalid Date"
    assert almacen.movimientos == []


def test_el_lote_recorre_la_maestra_de_ventas_y_resume(almacen, monkeypatch):
    filas = [
        {"CLIENTE": "ACME", "FECHA": "04/03/2026",
         "COTIZACION": _url("2026/03 - MARZO/uno-1.pdf")},
        {"CLIENTE": "", "FECHA": "", "COTIZACION": ""},  # se salta sin contar error
    ]
    historico = [
        {"CLIENTE": "BETA", "FECHA": "10/04/2026",
         "COTIZACION": _url("2026/04 - ABRIL/dos-2.pdf")},
    ]
    monkeypatch.setattr(tracker_store, "read_rows",
                        lambda hoja: (filas, historico, ["CLIENTE", "FECHA", "COTIZACION"]))
    monkeypatch.setattr(storage, "registrar_auditoria", lambda *a: None)

    res = storage.archivar_lote_cotizaciones()
    assert res["success"]
    # El histórico también se archiva: en el original `internalFetchSheetData`
    # devuelve las dos mitades y `forEach` las recorre juntas.
    assert res["processed"] == 2
    assert res["errors"] == []


# ======================================================================
# incrementarContadorDias
# ======================================================================

def test_el_contador_recorre_la_maestra_y_las_hojas_de_ventas():
    hojas = tracker_store.hojas_del_contador_de_dias()
    assert hojas[0] == rules.SALES_MASTER_SHEET
    # La maestra no se repite con sufijo: el original la excluye del bucle.
    assert f"{rules.SALES_MASTER_SHEET} (VENTAS)" not in hojas
    assert len(hojas) == len(set(hojas))  # el `[...new Set(...)]` de allá
    assert any(h.endswith(" (VENTAS)") for h in hojas)


def test_los_dias_se_cuentan_desde_la_fecha_y_nunca_son_negativos():
    hoy = datetime(2026, 3, 25)
    assert tracker_store._dias_desde("15/03/2026", hoy) == 10
    assert tracker_store._dias_desde("25/03/2026", hoy) == 0
    # Una fecha futura da 0, no un negativo: el `Math.max(0, diffDays)` del
    # original. Una cotización con fecha de entrega adelantada mostraría "-5".
    assert tracker_store._dias_desde("30/03/2026", hoy) == 0
    assert tracker_store._dias_desde("", hoy) is None
    assert tracker_store._dias_desde("no es fecha", hoy) is None


def test_la_columna_del_contador_se_resuelve_como_en_el_original():
    """
    `DIAS` y `RELOJ` por igualdad; `DIAS FINALIZ. COTIZ` por fragmento. El orden
    importa: un `DIAS` exacto gana al fragmento aunque esté más a la derecha.
    """
    pick = rules.pick_header
    dias, frag = tracker_store._COLUMNAS_DIAS, tracker_store._FRAGMENTOS_DIAS

    assert pick(["FOLIO", "DIAS", "DIAS FINALIZ. COTIZ"], dias, frag) == "DIAS"
    assert pick(["FOLIO", "DIAS FINALIZ. COTIZ"], dias, frag) == "DIAS FINALIZ. COTIZ"
    assert pick(["FOLIO", "RELOJ"], dias, frag) == "RELOJ"
    assert pick(["FOLIO", "CONCEPTO"], dias, frag) is None
    # El encabezado real se devuelve tal cual viene, no normalizado: hace falta
    # para poder escribir en esa misma columna.
    assert pick(["folio", " dias "], dias, frag) == " dias "


class _PersistenciaFalsa:
    def __init__(self):
        self.guardados = []

    def guardar(self, hoja, filas):
        self.guardados.append((hoja, filas))

        class _Res:
            mensaje = ""
            exito = True
        return _Res()


def test_el_contador_solo_escribe_folio_y_dias(monkeypatch):
    """
    Se manda una fila parcial a propósito: el upsert toca únicamente `dias`, así
    que recalcular el contador no puede pisar una edición que alguien haya hecho
    mientras corría el trabajo.
    """
    falsa = _PersistenciaFalsa()
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: falsa)
    monkeypatch.setattr(tracker_store, "hojas_del_contador_de_dias",
                        lambda: [rules.SALES_MASTER_SHEET])
    monkeypatch.setattr(tracker_store, "read_rows", lambda hoja: (
        [{"FOLIO": "AV-3250", "F. INICIO": "15/03/2026", "DIAS": "2"}],
        [],
        ["FOLIO", "F. INICIO", "DIAS"],
    ))

    res = tracker_store.incrementar_contador_dias(hoy=datetime(2026, 3, 25))

    assert res["actualizados"] == 1
    hoja, filas = falsa.guardados[0]
    assert hoja == rules.SALES_MASTER_SHEET
    assert filas == [{"FOLIO": "AV-3250", "DIAS": 10}]


def test_una_fila_que_ya_tiene_el_valor_correcto_no_se_reescribe(monkeypatch):
    """Sin esto, cada corrida diaria reescribiría las 4.600 filas."""
    falsa = _PersistenciaFalsa()
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: falsa)
    monkeypatch.setattr(tracker_store, "hojas_del_contador_de_dias",
                        lambda: [rules.SALES_MASTER_SHEET])
    monkeypatch.setattr(tracker_store, "read_rows", lambda hoja: (
        [{"FOLIO": "AV-3250", "F. INICIO": "15/03/2026", "DIAS": "10"}],
        [],
        ["FOLIO", "F. INICIO", "DIAS"],
    ))

    res = tracker_store.incrementar_contador_dias(hoy=datetime(2026, 3, 25))
    assert res["actualizados"] == 0
    assert falsa.guardados == []


def test_sin_motor_de_datos_el_contador_avisa_y_no_revienta(monkeypatch):
    """
    Lo llama un cron. Un 500 con traza deja al workflow sin saber qué pasó y, al
    ir de primer paso en `auto_update_quote_metrics`, tumbaría también los KPIs y
    los dos correos, que no dependen del contador.
    """
    def _explota():
        from backend.core.errors import SinMotorConfigurado
        raise SinMotorConfigurado("No hay motor de datos configurado")

    monkeypatch.setattr(tracker_store, "_persistencia", _explota)

    res = tracker_store.incrementar_contador_dias()
    assert res["success"] is False
    assert res["actualizados"] == 0
    assert "contador de días" in res["message"]


def test_una_hoja_sin_columna_de_contador_se_salta(monkeypatch):
    falsa = _PersistenciaFalsa()
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: falsa)
    monkeypatch.setattr(tracker_store, "hojas_del_contador_de_dias",
                        lambda: [rules.SALES_MASTER_SHEET])
    monkeypatch.setattr(tracker_store, "read_rows", lambda hoja: (
        [{"FOLIO": "AV-3250", "F. INICIO": "15/03/2026"}], [], ["FOLIO", "F. INICIO"]))

    res = tracker_store.incrementar_contador_dias(hoy=datetime(2026, 3, 25))
    assert res["actualizados"] == 0
    assert falsa.guardados == []


def test_el_cron_diario_recalcula_los_dias_antes_de_medir(monkeypatch):
    """
    En el original el contador corre a la 1 a.m. y las métricas a las 07:00, así
    que las métricas siempre leen un contador fresco. Al juntarlos en un solo
    endpoint hay que conservar ese orden.
    """
    orden = []

    def registrar(nombre, respuesta):
        def _fn():
            orden.append(nombre)
            return respuesta
        return _fn

    monkeypatch.setattr(tracker_store, "incrementar_contador_dias",
                        registrar("dias", {"actualizados": 3}))
    monkeypatch.setattr(tracker_store, "write_quote_metrics_to_sheet",
                        registrar("kpi", {"success": True}))
    monkeypatch.setattr(tracker_store, "send_quote_metrics_email",
                        registrar("correo", {"data": {"emailSent": True}}))
    monkeypatch.setattr(tracker_store, "run_tracker_productivity_agent",
                        registrar("productividad", {"data": {"emailSent": True}}))

    res = tracker_store.auto_update_quote_metrics()
    assert orden[0] == "dias"
    assert orden == ["dias", "kpi", "correo", "productividad"]
    assert res["data"]["diasActualizados"] == 3


# ======================================================================
# generateNumericSequence: el candado de folios
# ======================================================================

def test_el_alcance_del_candado_sigue_al_del_consecutivo():
    """
    Un prefijo global se cuenta sobre toda la tabla, así que dos hojas compiten
    por el mismo número y el candado tiene que ser global. Uno de iniciales solo
    es único dentro de su hoja; hacerlo global pondría cada alta del sistema a
    esperar detrás de todas las demás.
    """
    global_1 = tracker_store._clave_de_candado("AV-", "ANTONIA_VENTAS")
    global_2 = tracker_store._clave_de_candado("AV-", "RAMIRO RODRIGUEZ (VENTAS)")
    assert global_1 == global_2

    propio_1 = tracker_store._clave_de_candado("JO-", "JAIME OLIVO")
    propio_2 = tracker_store._clave_de_candado("JO-", "OTRA PERSONA")
    assert propio_1 != propio_2


def test_sin_folio_nuevo_no_se_toma_candado():
    """
    El caso normal —actualizar filas que ya tienen folio— no debe serializarse.
    El proveedor solo avisa cuando de verdad va a leer el consecutivo.
    """
    tomados = []

    class _Persistencia:
        def ultimo_consecutivo(self, prefijo, hoja):
            return 3250

    siguiente = tracker_store._secuencia_desde_la_base(
        _Persistencia(), "ANTONIA_VENTAS", al_reservar=tomados.append)

    assert tomados == []  # nadie pidió folio todavía
    assert siguiente("k") == "3251"
    assert tomados == ["AV-"]  # se tomó al pedir el primero
    assert siguiente("k") == "3252"
    assert tomados == ["AV-"]  # y no se vuelve a tomar


def test_el_candado_se_sostiene_hasta_despues_de_escribir(monkeypatch):
    """
    La prueba de fondo del candado: leer el consecutivo más alto y escribir la
    fila con ese folio son las dos mitades de una sola operación. Si el candado
    se soltara entre ellas no serviría de nada, así que se verifica que la
    escritura ocurre **dentro** del contexto y que se suelta después.
    """
    eventos = []

    class _Candado:
        def __init__(self, clave):
            self.clave = clave

        def __enter__(self):
            eventos.append(("candado", self.clave))
            return None

        def __exit__(self, *_):
            eventos.append(("suelta", self.clave))
            return False

    class _Motor:
        soporta_candados = True

        def candado(self, clave):
            return _Candado(clave)

    class _Guardado:
        mensaje = ""
        exito = True
        filas = []
        hoja = "ANTONIA_VENTAS"

    class _Persistencia:
        engine = _Motor()

        def ultimo_consecutivo(self, prefijo, hoja):
            eventos.append(("lee_consecutivo", prefijo))
            return 3250

        def guardar(self, hoja, filas):
            eventos.append(("guarda", hoja))
            return _Guardado()

    monkeypatch.setattr(tracker_store, "_matriz_de_trabajo",
                        lambda hoja: [["FOLIO", "CLIENTE", "CONCEPTO", "FECHA"]])
    monkeypatch.setattr(tracker_store, "_auditar", lambda *a: None)
    monkeypatch.setattr(tracker_store, "send_to_outlook", lambda payload: None)

    tracker_store._persist_batch(
        "ANTONIA_VENTAS",
        [{"CLIENTE": "ACME", "CONCEPTO": "Nueva cotización", "FECHA": "04/03/2026"}],
        persistencia=_Persistencia(),
    )

    nombres = [e[0] for e in eventos]
    assert nombres.index("candado") < nombres.index("lee_consecutivo")
    assert nombres.index("guarda") < nombres.index("suelta")
