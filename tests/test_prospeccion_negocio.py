"""
El puente entre el mapa y el negocio (Fase 5 del plan de prospección).

Tres piezas, tres razones distintas para probarlas:

1. **`geo_prospectos`** — el estado comercial de un establecimiento. Se prueba
   contra `MemoryEngine`, nunca contra Supabase: R7 dice que ninguna prueba
   escribe en la base de producción y `tests/conftest.py` fuerza
   `BACKEND_ENGINE=memoria`. El doble no es un `dict` ingenuo: reproduce el
   `23502` de una columna NOT NULL y la fusión del upsert, que es de lo que
   depende que `created_at` sobreviva a un cambio de estado.

2. **La exportación** — un CSV que Excel abre mal y un XLSX que Excel no abre
   son el mismo fallo desde la silla de quien lo descarga. Se comprueba el
   contenido, los encabezados y que el XLSX generado a mano lo lea `openpyxl`.

3. **La solicitud de cotización** — hoy está bloqueada a propósito, y lo que se
   prueba es justamente que **no manda nada**. Falta el aviso de la LFPDPPP
   (plan §11, punto 5) y esa es una decisión del dueño. Una prueba que solo
   comprobara el camino feliz dejaría pasar el día en que alguien encienda la
   bandera creyendo que el texto ya estaba.
"""

from __future__ import annotations

import io
import pathlib

import pytest
from pydantic import ValidationError

from api.services import exportacion, prospeccion_correo
from api.services.denue_repo import COLUMNAS_DEL_MAPA
from backend.core.engines.memoria import MemoryEngine
from backend.core.errors import ErrorDeMotor
from backend.repositories.geo_prospectos import (
    TABLA,
    GeoProspectoRepository,
    ProspectoNoEncontrado,
)
from backend.schemas.geo_prospecto import ESTADOS_VALIDOS, ProspectoWrite

FERRETERIA = {
    "id": "9274655", "nom_estab": "FERRETERIA EL TORNILLO",
    "nombre_act": "Comercio al por menor en ferreterías y tlapalerías",
    "per_ocu": "0 a 5 personas", "telefono": "5512345678",
    "correoelec": "VENTAS@TORNILLO.MX", "www": "WWW.TORNILLO.MX",
    "municipio": "Cuauhtémoc", "latitud": 19.41887981, "longitud": -99.09012648,
}

INGENIERIA = {
    "id": "11767053", "nom_estab": "INGENIERIA DEL VALLE",
    "nombre_act": "Servicios de ingeniería", "per_ocu": "11 a 30 personas",
    "telefono": None, "correoelec": None, "www": None,
    "municipio": "Benito Juárez", "latitud": 19.38, "longitud": -99.16,
}


@pytest.fixture
def repo() -> GeoProspectoRepository:
    """Repositorio sobre el doble en memoria. Nunca toca Supabase (R7)."""
    return GeoProspectoRepository(MemoryEngine())


def _marcar(repo: GeoProspectoRepository, denue_id: str, estado: str, **extra):
    return repo.guardar(ProspectoWrite(establecimiento_id=denue_id, estado=estado, **extra))


# ----------------------------------------------------------------------
# El estado comercial del prospecto
# ----------------------------------------------------------------------

def test_marcar_un_establecimiento_lo_da_de_alta_como_prospecto(repo):
    prospecto = _marcar(repo, "9274655", "NUEVO")
    assert prospecto.denue_id == "9274655"
    assert prospecto.estado == "NUEVO"
    assert prospecto.created_at is not None


def test_un_establecimiento_tiene_un_solo_estado_comercial(repo):
    """
    Alta y cambio son la misma llamada. Dos filas para el mismo negocio serían
    dos verdades sobre a quién ya se llamó, que es lo que este módulo evita.
    """
    _marcar(repo, "9274655", "NUEVO")
    _marcar(repo, "9274655", "CONTACTADO")
    assert len(repo.engine.select(TABLA)) == 1
    assert repo.obtener("9274655").estado == "CONTACTADO"


def test_cambiar_de_estado_no_reescribe_la_fecha_de_alta(repo):
    """
    `created_at` es lo único con lo que se puede medir cuánto tarda un negocio
    en pasar de NUEVO a COTIZANDO. Reescribirlo en cada cambio borraría el dato
    sin que nada fallara.
    """
    alta = _marcar(repo, "9274655", "NUEVO")
    despues = _marcar(repo, "9274655", "COTIZANDO")
    assert despues.created_at == alta.created_at
    assert despues.updated_at >= alta.updated_at


def test_el_vendedor_y_la_nota_se_guardan(repo):
    prospecto = _marcar(repo, "9274655", "CONTACTADO",
                        vendedor="RAMIRO RODRIGUEZ", nota="Pidió catálogo de tubería")
    assert prospecto.vendedor == "RAMIRO RODRIGUEZ"
    assert prospecto.nota == "Pidió catálogo de tubería"


def test_un_vendedor_en_blanco_es_nulo_y_no_cadena_vacia(repo):
    """
    `vendedor = ""` es un vendedor llamado cadena vacía: filtrar por vendedor lo
    devolvería y el panel mostraría una columna vacía como si fuera una persona.
    """
    prospecto = _marcar(repo, "9274655", "NUEVO", vendedor="   ", nota="")
    assert prospecto.vendedor is None
    assert prospecto.nota is None


@pytest.mark.parametrize("estado", ESTADOS_VALIDOS)
def test_los_cuatro_estados_del_embudo_se_aceptan(repo, estado):
    assert _marcar(repo, "9274655", estado).estado == estado


def test_un_estado_desconocido_se_rechaza_en_vez_de_degradar_a_nuevo():
    """
    Degradar en silencio a `NUEVO` convertiría un error de tecleo en "este
    negocio nunca se ha contactado", borrando trabajo que alguien ya hizo.
    """
    with pytest.raises(ValidationError, match="estado debe ser uno de"):
        ProspectoWrite(establecimiento_id="9274655", estado="PERDIDO")


def test_el_estado_llega_en_mayusculas_venga_como_venga():
    assert ProspectoWrite(establecimiento_id="1", estado="contactado").estado == "CONTACTADO"


def test_el_cuerpo_no_puede_colar_columnas_que_no_le_tocan():
    """
    `extra="forbid"`. `web_cache` la escribe el job de enriquecimiento fuera de
    línea y `created_at` sirve para auditar: si el navegador pudiera mandarlas
    en un round-trip ingenuo, las dos dejarían de significar algo.
    """
    with pytest.raises(ValidationError):
        ProspectoWrite(establecimiento_id="1", estado="NUEVO", web_cache="texto")
    with pytest.raises(ValidationError):
        ProspectoWrite(establecimiento_id="1", estado="NUEVO", created_at="2020-01-01")


def test_guardar_no_borra_la_cache_del_sitio(repo):
    """
    El upsert fusiona en vez de reemplazar. Omitir `web_cache` la conserva, que
    es lo que permite que marcar un prospecto no tire el texto que costó
    scrapear.
    """
    repo.engine.datos[TABLA] = [{
        "denue_id": "9274655", "estado": "NUEVO", "web_cache": "texto del sitio",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    }]
    assert _marcar(repo, "9274655", "CONTACTADO").web_cache == "texto del sitio"


def test_listar_filtra_por_estado_y_por_vendedor(repo):
    _marcar(repo, "1", "NUEVO")
    _marcar(repo, "2", "CONTACTADO", vendedor="RAMIRO RODRIGUEZ")
    _marcar(repo, "3", "CONTACTADO", vendedor="SEBASTIAN PADILLA")

    assert {p.denue_id for p in repo.listar(estado="CONTACTADO")} == {"2", "3"}
    assert [p.denue_id for p in repo.listar(vendedor="RAMIRO RODRIGUEZ")] == ["2"]
    assert len(repo.listar()) == 3


def test_obtener_un_establecimiento_que_nadie_marco_lo_dice(repo):
    """
    Devolver una fila vacía haría creer al panel que el negocio está en `NUEVO`
    cuando en realidad nunca entró al embudo.
    """
    with pytest.raises(ProspectoNoEncontrado, match="9274655"):
        repo.obtener("9274655")


def test_si_el_motor_no_devuelve_la_fila_el_guardado_no_se_da_por_bueno(repo, monkeypatch):
    """
    PostgREST devuelve la fila porque el upsert pide `return=representation`. Si
    llega vacío, el guardado no está confirmado: mejor un error visible que un
    `IndexError` que sale a pantalla como un 500 sin causa.
    """
    monkeypatch.setattr(repo.engine, "upsert", lambda *a, **k: [])
    with pytest.raises(ErrorDeMotor, match="no devolvió la fila guardada"):
        _marcar(repo, "9274655", "NUEVO")


def test_el_doble_rechaza_una_fila_sin_estado_igual_que_postgres(repo):
    """
    `estado` es NOT NULL sin DEFAULT en el DDL (§8). El doble tiene que fallar
    donde falla la base, no donde no.
    """
    with pytest.raises(ErrorDeMotor):
        repo.engine.upsert(TABLA, [{"denue_id": "9274655"}], en_conflicto="denue_id")


# --- La caché del texto del sitio (capa 1 del agente) ------------------

def test_leer_el_sitio_de_un_negocio_no_lo_convierte_en_prospecto(repo):
    """
    La fila se crea con el estado inicial porque `estado` es NOT NULL y omitirlo
    abortaría el alta con un 23502. Pero eso NO es una decisión comercial: nadie
    ha contactado a este negocio todavía.
    """
    repo.guardar_texto_del_sitio("9274655", "Venden tubería de cobre.")
    guardado = repo.obtener("9274655")
    assert guardado.estado == "NUEVO"
    assert guardado.web_cache == "Venden tubería de cobre."
    assert guardado.web_cache_at is not None


def test_la_cache_del_sitio_sobrevive_al_cambio_de_estado(repo):
    """
    Marcar un prospecto no puede tirar el texto que costó scrapear: el upsert
    fusiona y `guardar` omite `web_cache` a propósito.
    """
    repo.guardar_texto_del_sitio("9274655", "Venden tubería de cobre.")
    _marcar(repo, "9274655", "CONTACTADO", vendedor="RAMIRO RODRIGUEZ")
    assert repo.texto_del_sitio("9274655") == "Venden tubería de cobre."


def test_guardar_el_estado_no_reescribe_la_cache_con_vacio(repo):
    """El caso al revés del anterior, y el que más fácil se cuela."""
    _marcar(repo, "9274655", "NUEVO")
    repo.guardar_texto_del_sitio("9274655", "Texto del sitio.")
    _marcar(repo, "9274655", "COTIZANDO")
    assert repo.texto_del_sitio("9274655") == "Texto del sitio."


def test_un_negocio_sin_cache_devuelve_cadena_vacia(repo):
    """`None` obligaría a comprobar el nulo en el agente por una fila que no existe."""
    assert repo.texto_del_sitio("9274655") == ""


def test_no_se_guarda_cache_sin_identificador(repo):
    """Una fila con `denue_id` vacío no pertenece a ningún negocio."""
    repo.guardar_texto_del_sitio("   ", "texto")
    assert repo.engine.select(TABLA) == []


# ----------------------------------------------------------------------
# La exportación de la selección
# ----------------------------------------------------------------------

def test_el_csv_lleva_los_encabezados_legibles_y_las_diez_columnas():
    """La API habla en nombres del INEGI; una hoja que abre compras, no."""
    texto = exportacion.a_csv([FERRETERIA]).decode("utf-8-sig")
    encabezado = texto.splitlines()[0].split(",")
    assert encabezado == ["ID DENUE", "NOMBRE", "GIRO", "PERSONAL", "TELEFONO",
                          "CORREO", "SITIO WEB", "ALCALDIA", "LATITUD", "LONGITUD"]
    assert len(encabezado) == len(COLUMNAS_DEL_MAPA) == 10


def test_el_csv_trae_bom_para_que_excel_no_rompa_los_acentos():
    """
    Sin BOM, Excel en Windows lee el archivo como ANSI y "Cuauhtémoc" llega como
    "CuauhtÃ©moc". Es el destino real de esta descarga.
    """
    crudo = exportacion.a_csv([FERRETERIA])
    assert crudo.startswith(b"\xef\xbb\xbf")
    assert "Cuauhtémoc" in crudo.decode("utf-8-sig")


def test_el_csv_escribe_el_nulo_como_celda_vacia():
    """`None` impreso tal cual pondría la cadena "None" en la columna TELEFONO."""
    fila = exportacion.a_csv([INGENIERIA]).decode("utf-8-sig").splitlines()[1]
    assert "None" not in fila
    assert fila.startswith("11767053,INGENIERIA DEL VALLE")


def test_el_csv_usa_fin_de_linea_de_excel():
    assert b"\r\n" in exportacion.a_csv([FERRETERIA])


def test_el_xlsx_generado_a_mano_lo_abre_una_hoja_de_calculo_de_verdad():
    """
    El archivo se arma con `zipfile` y `xml` para no meter `openpyxl` al runtime.
    La prueba sí usa `openpyxl` —es dependencia de desarrollo— justamente para
    comprobar que lo escrito a mano es un XLSX válido y no un ZIP con XML dentro.
    """
    openpyxl = pytest.importorskip("openpyxl")
    libro = openpyxl.load_workbook(io.BytesIO(exportacion.a_xlsx([FERRETERIA, INGENIERIA])))
    hoja = libro[exportacion.NOMBRE_HOJA]
    assert [c.value for c in hoja[1]][:2] == ["ID DENUE", "NOMBRE"]
    assert hoja.cell(row=2, column=2).value == "FERRETERIA EL TORNILLO"
    assert hoja.max_row == 3


def test_las_coordenadas_del_xlsx_son_numeros_y_no_texto():
    """Como texto, ordenar por latitud en Excel daría un orden alfabético."""
    openpyxl = pytest.importorskip("openpyxl")
    libro = openpyxl.load_workbook(io.BytesIO(exportacion.a_xlsx([FERRETERIA])))
    hoja = libro[exportacion.NOMBRE_HOJA]
    assert hoja.cell(row=2, column=9).value == pytest.approx(19.41887981)
    assert isinstance(hoja.cell(row=2, column=10).value, float)


def test_el_xlsx_escapa_el_nombre_del_negocio():
    """
    Los nombres vienen del INEGI y hay establecimientos con `&` y `<` en el
    nombre. Sin escapar, el XML del libro queda mal formado y Excel se niega a
    abrirlo entero — no falla la celda, falla el archivo.
    """
    openpyxl = pytest.importorskip("openpyxl")
    raro = {**FERRETERIA, "nom_estab": 'ACEROS & CIA <"EL FIERRO">'}
    libro = openpyxl.load_workbook(io.BytesIO(exportacion.a_xlsx([raro])))
    assert libro[exportacion.NOMBRE_HOJA].cell(row=2, column=2).value == 'ACEROS & CIA <"EL FIERRO">'


def test_dos_exportaciones_del_mismo_dato_dan_el_mismo_archivo():
    """
    La fecha dentro del ZIP es fija. Con la hora del reloj, comparar dos
    descargas para ver si el catálogo cambió sería imposible.
    """
    assert exportacion.a_xlsx([FERRETERIA]) == exportacion.a_xlsx([FERRETERIA])


def test_exportar_una_seleccion_vacia_deja_los_encabezados():
    """Un archivo de cero bytes se lee como "la descarga falló"."""
    openpyxl = pytest.importorskip("openpyxl")
    assert exportacion.a_csv([]).decode("utf-8-sig").startswith("ID DENUE")
    hoja = openpyxl.load_workbook(io.BytesIO(exportacion.a_xlsx([])))[exportacion.NOMBRE_HOJA]
    assert hoja.max_row == 1


def test_la_letra_de_columna_sigue_creciendo_despues_de_la_z():
    """Hoy son 10 columnas y llegan a J; el día que sean 27, `AA` tiene que salir."""
    assert [exportacion._columna(i) for i in (0, 9, 25, 26, 27)] == ["A", "J", "Z", "AA", "AB"]


# ----------------------------------------------------------------------
# La solicitud de cotización — bloqueada a propósito
# ----------------------------------------------------------------------

def test_hoy_no_se_manda_ningun_correo_porque_falta_el_aviso_legal():
    """
    El DENUE es público; usar sus correos para contacto comercial no lo es. La
    LFPDPPP exige identificar a la empresa y ofrecer una vía de baja, y ese
    texto es decisión del dueño (plan §11, punto 5).
    """
    assert prospeccion_correo.AVISO_LFPDPPP.strip() == ""
    assert prospeccion_correo.aviso_definido() is False
    assert prospeccion_correo.envio_habilitado() is False


def test_la_solicitud_bloqueada_explica_el_motivo_y_deja_el_correo_escrito():
    """
    Bloquear no es no servir: el correo redactado vuelve como vista previa para
    copiarlo y mandarlo a mano, asumiendo quien lo manda la responsabilidad.
    """
    salida = prospeccion_correo.solicitar_cotizacion(
        "FERRETERIA EL TORNILLO", "VENTAS@TORNILLO.MX",
        "Solicitud de cotización", "Buen día, necesitamos tubería.")
    assert salida["success"] is False
    assert salida["motivo"] == prospeccion_correo.MOTIVO_AVISO_PENDIENTE
    assert "LFPDPPP" in salida["message"]
    assert "necesitamos tubería" in salida["vista_previa"]["html"]


def test_encender_solo_la_bandera_no_alcanza_para_mandar(monkeypatch):
    """
    Los dos cerrojos protegen de cosas distintas. Este es el caso que preocupa:
    alguien pone la variable de entorno creyendo que el texto legal ya estaba.
    """
    monkeypatch.setenv(prospeccion_correo.BANDERA_ENVIO_ENV, "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.mx")
    enviados = []
    salida = prospeccion_correo.solicitar_cotizacion(
        "X", "a@b.mx", "Asunto", "Cuerpo",
        enviar=lambda *a, **k: enviados.append(a) or {"success": True})
    assert salida["success"] is False
    assert salida["motivo"] == prospeccion_correo.MOTIVO_AVISO_PENDIENTE
    assert enviados == [], "no se puede abrir el canal de correo sin el aviso legal"


def test_un_establecimiento_sin_correo_lo_dice_en_vez_de_fallar():
    """De 20,957 establecimientos, solo 7,324 declararon correo."""
    salida = prospeccion_correo.solicitar_cotizacion("SIN CORREO", None, "A", "B")
    assert salida["motivo"] == prospeccion_correo.MOTIVO_SIN_DESTINATARIO
    assert "no declaró correo" in salida["message"]


def test_con_el_aviso_definido_el_correo_sale_por_el_canal_que_ya_existe(monkeypatch):
    """
    El día que el dueño escriba el texto. Se inyecta `enviar` para verificar
    QUÉ se manda sin abrir un socket: el aviso legal tiene que ir dentro del
    cuerpo, no en un correo aparte que nadie lee.
    """
    monkeypatch.setattr(prospeccion_correo, "AVISO_LFPDPPP",
                        "Holtmont S.A. de C.V. Para no recibir más correos, responde BAJA.")
    monkeypatch.setenv(prospeccion_correo.BANDERA_ENVIO_ENV, "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.mx")

    despachos = []

    def espiar(asunto, html, destinatarios):
        despachos.append((asunto, html, destinatarios))
        return {"success": True, "recipients": destinatarios}

    salida = prospeccion_correo.solicitar_cotizacion(
        "FERRETERIA EL TORNILLO", "VENTAS@TORNILLO.MX",
        "Solicitud de cotización", "Buen día.", enviar=espiar)

    assert salida["success"] is True
    asunto, html, destinatarios = despachos[0]
    assert asunto == "Solicitud de cotización"
    assert destinatarios == ["VENTAS@TORNILLO.MX"]
    assert "responde BAJA" in html


def test_con_el_aviso_escrito_pero_la_bandera_apagada_tampoco_se_manda(monkeypatch):
    """
    El segundo cerrojo, por separado. Cuando el dueño escriba el texto legal, el
    envío no debe encenderse solo con desplegar: hace falta poner
    `GEO_CORREO_HABILITADO=1` a propósito.
    """
    monkeypatch.setattr(prospeccion_correo, "AVISO_LFPDPPP", "Holtmont. Responde BAJA.")
    monkeypatch.delenv(prospeccion_correo.BANDERA_ENVIO_ENV, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.mx")
    salida = prospeccion_correo.solicitar_cotizacion("X", "a@b.mx", "A", "B")
    assert salida["success"] is False
    assert salida["motivo"] == prospeccion_correo.MOTIVO_ENVIO_APAGADO


def test_si_el_servidor_de_correo_rechaza_el_mensaje_se_dice(monkeypatch):
    """
    `correo.enviar` nunca lanza: devuelve `success: false` con el motivo. Ese
    resultado no puede convertirse aquí en un éxito, y la vista previa vuelve
    para que el mensaje no se pierda.
    """
    monkeypatch.setattr(prospeccion_correo, "AVISO_LFPDPPP", "Holtmont. Responde BAJA.")
    monkeypatch.setenv(prospeccion_correo.BANDERA_ENVIO_ENV, "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.mx")
    salida = prospeccion_correo.solicitar_cotizacion(
        "X", "a@b.mx", "A", "B",
        enviar=lambda *a, **k: {"success": False, "message": "550 buzón lleno"})
    assert salida["success"] is False
    assert salida["message"] == "550 buzón lleno"
    assert salida["vista_previa"]["destinatario"] == "a@b.mx"


def test_sin_smtp_configurado_no_se_reporta_un_envio_que_no_ocurrio(monkeypatch):
    monkeypatch.setattr(prospeccion_correo, "AVISO_LFPDPPP", "Holtmont. Responde BAJA.")
    monkeypatch.setenv(prospeccion_correo.BANDERA_ENVIO_ENV, "1")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    salida = prospeccion_correo.solicitar_cotizacion("X", "a@b.mx", "A", "B")
    assert salida["success"] is False
    assert salida["motivo"] == prospeccion_correo.MOTIVO_SMTP


def test_el_cuerpo_del_correo_escapa_lo_que_redacto_el_agente():
    """
    El texto lo escribe un LLM o una persona. Sin escapar, un `<script>` en la
    redacción viaja como marcado dentro del correo.
    """
    html = prospeccion_correo.cuerpo_html("X", '<script>alert("x")</script>')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ----------------------------------------------------------------------
# Las rutas HTTP
# ----------------------------------------------------------------------
#
# `construir_engine()` con `BACKEND_ENGINE=memoria` devuelve un motor NUEVO en
# cada llamada, así que dos peticiones no compartirían datos. Aquí se fija uno
# solo para toda la prueba: es lo que permite comprobar que un POST y el
# siguiente hablan de la misma fila.

_ESQUEMA_DENUE = """
CREATE TABLE denue (
  id TEXT PRIMARY KEY, nom_estab TEXT, nombre_act TEXT, codigo_act TEXT,
  per_ocu TEXT, telefono TEXT, correoelec TEXT, www TEXT,
  municipio TEXT, nom_vial TEXT, numero_ext TEXT, cod_postal TEXT,
  latitud REAL, longitud REAL
);
"""

# Un cuadrado sobre Polanco. GeoJSON pone la longitud primero.
POLIGONO = {
    "type": "Polygon",
    "coordinates": [[
        [-99.23, 19.41], [-99.18, 19.41], [-99.18, 19.46], [-99.23, 19.46], [-99.23, 19.41],
    ]],
}


@pytest.fixture
def catalogo_sqlite(tmp_path: pathlib.Path) -> pathlib.Path:
    """Catálogo de tres filas: dos dentro del polígono y una fuera."""
    import sqlite3

    ruta = tmp_path / "denue.sqlite"
    conexion = sqlite3.connect(ruta)
    with conexion:
        conexion.executescript(_ESQUEMA_DENUE)
        conexion.executemany(
            f"INSERT INTO denue VALUES ({', '.join('?' * 14)})",
            [
                ("15", "INGENIERIA POLANCO", "Servicios de ingeniería", "541330",
                 "101 a 250 personas", "5555550006", None, "WWW.IPOL.MX",
                 "Miguel Hidalgo", "HORACIO", "77", "11550", 19.4300, -99.1900),
                ("17", "MATERIALES LOMAS",
                 "Comercio al por menor en ferreterías y tlapalerías", "467111",
                 "11 a 30 personas", None, "L@ML.MX", None,
                 "Miguel Hidalgo", "PALOMAS", "22", "11200", 19.4200, -99.2200),
                ("01", "FERRETERIA DEL CENTRO",
                 "Comercio al por menor en ferreterías y tlapalerías", "467111",
                 "0 a 5 personas", "5512345678", None, None,
                 "Cuauhtémoc", "DONCELES", "10", "06010", 19.4400, -99.1400),
            ],
        )
    conexion.close()
    return ruta


@pytest.fixture
def cliente(catalogo_sqlite: pathlib.Path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.services import denue_repo
    from api.main import app
    from backend.core import engine as motor

    monkeypatch.setattr(denue_repo, "RUTA_CATALOGO", catalogo_sqlite)
    monkeypatch.setattr(denue_repo, "_repositorio", None)
    compartido = MemoryEngine()
    monkeypatch.setattr(motor, "construir_engine", lambda settings=None: compartido)
    with TestClient(app) as http:
        yield http
    monkeypatch.setattr(denue_repo, "_repositorio", None)


def test_la_ruta_marca_un_prospecto_y_lo_conserva_entre_peticiones(cliente):
    primera = cliente.post("/api/geo/prospecto", json={
        "establecimiento_id": "15", "estado": "CONTACTADO", "vendedor": "RAMIRO RODRIGUEZ"})
    assert primera.status_code == 200
    assert primera.json()["success"] is True

    segunda = cliente.post("/api/geo/prospecto", json={
        "establecimiento_id": "15", "estado": "COTIZANDO", "nota": "Mandó lista"})
    cuerpo = segunda.json()["prospecto"]
    assert cuerpo["estado"] == "COTIZANDO"
    assert cuerpo["created_at"] == primera.json()["prospecto"]["created_at"]


def test_la_ruta_rechaza_un_estado_que_no_existe(cliente):
    """422 y no 200: un estado inventado es un cliente roto, no un dato válido."""
    respuesta = cliente.post("/api/geo/prospecto", json={
        "establecimiento_id": "15", "estado": "PERDIDO"})
    assert respuesta.status_code == 422


def test_sin_motor_configurado_la_ruta_degrada_con_el_motivo(cliente, monkeypatch):
    """
    Mismo criterio que `/api/plano_2d`: nunca un 500. La tabla la crea el dueño
    con `docs/DDL_PENDIENTE.sql` §8 y hasta entonces hay que decirlo, no reventar.
    """
    from backend.core import engine as motor
    from backend.core.errors import SinMotorConfigurado

    def sin_motor(settings=None):
        raise SinMotorConfigurado("No hay motor de datos configurado")

    monkeypatch.setattr(motor, "construir_engine", sin_motor)
    cuerpo = cliente.post("/api/geo/prospecto",
                          json={"establecimiento_id": "15", "estado": "NUEVO"}).json()
    assert cuerpo["success"] is False
    assert "motor de datos" in cuerpo["message"]


def test_la_seleccion_devuelve_solo_lo_que_cae_dentro_del_poligono(cliente):
    cuerpo = cliente.post("/api/geo/seleccion",
                          json={"poligono": POLIGONO, "formato": "json"}).json()
    assert cuerpo["success"] is True
    assert [f["id"] for f in cuerpo["items"]] == ["15", "17"]


def test_la_seleccion_se_descarga_como_csv_con_nombre_de_archivo(cliente):
    respuesta = cliente.post("/api/geo/seleccion",
                             json={"poligono": POLIGONO, "formato": "csv"})
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert 'filename="prospectos.csv"' in respuesta.headers["content-disposition"]
    texto = respuesta.content.decode("utf-8-sig")
    assert texto.splitlines()[0].startswith("ID DENUE")
    assert "INGENIERIA POLANCO" in texto
    assert "FERRETERIA DEL CENTRO" not in texto


def test_la_seleccion_se_descarga_como_xlsx_que_excel_reconoce(cliente):
    openpyxl = pytest.importorskip("openpyxl")
    respuesta = cliente.post("/api/geo/seleccion",
                             json={"poligono": POLIGONO, "formato": "xlsx"})
    assert respuesta.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    hoja = openpyxl.load_workbook(io.BytesIO(respuesta.content))[exportacion.NOMBRE_HOJA]
    assert hoja.max_row == 3


def test_un_poligono_invalido_no_devuelve_un_archivo_roto(cliente):
    """
    Un CSV con el mensaje de error dentro se descarga igual y parece un archivo
    bueno. El fallo tiene que salir como JSON.
    """
    respuesta = cliente.post("/api/geo/seleccion", json={
        "poligono": {"type": "Point", "coordinates": [-99.2, 19.4]}, "formato": "csv"})
    assert respuesta.headers["content-type"].startswith("application/json")
    assert respuesta.json()["success"] is False


def test_la_ruta_de_cotizacion_no_manda_nada_todavia(cliente):
    cuerpo = cliente.post("/api/geo/solicitar_cotizacion", json={
        "establecimiento_id": "15", "destinatario": "VENTAS@TORNILLO.MX",
        "asunto": "Solicitud de cotización", "mensaje": "Buen día."}).json()
    assert cuerpo["success"] is False
    assert cuerpo["motivo"] == prospeccion_correo.MOTIVO_AVISO_PENDIENTE
    assert "Buen día." in cuerpo["vista_previa"]["html"]
