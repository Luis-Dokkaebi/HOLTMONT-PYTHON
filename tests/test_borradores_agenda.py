"""
Borradores de PPC, agenda personal, hábitos, banco de información,
PPC maestro, calendario combinado, logout y directorio.

Los once métodos que cubre este archivo eran stubs: seis devolvían vacío y
cinco un error visible. Con esto el adaptador queda sin más stubs que
`uploadFileToDrive`, que depende del storage de archivos.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.repositories.agenda import (  # noqa: E402
    DIAS_VACIOS,
    RepositorioAgenda,
    RepositorioBorradores,
    TablaAusente,
)


class EngineEstricto(MemoryEngine):
    """
    `MemoryEngine` con la distinción que hace PostgREST: consultar una tabla que
    no existe **falla** (PGRST205), no devuelve cero filas.

    El doble base resuelve con `self.datos.get(tabla, [])`, así que una tabla
    ausente y una vacía son indistinguibles y el código que depende de esa
    diferencia —el aviso de `habits_log`— no se podría probar.
    """

    def select(self, tabla, **kw):
        if tabla not in self.datos:
            raise RuntimeError(f"PGRST205: no existe la tabla public.{tabla}")
        return super().select(tabla, **kw)


# --- Borradores -------------------------------------------------------

def _engine_borradores(filas=None):
    return MemoryEngine({"ppc_borradores": filas if filas is not None else []})


def test_listar_borradores_devuelve_las_claves_del_frontend():
    engine = _engine_borradores([{
        "especialidad": "HVAC", "concepto": "Cambiar filtro", "responsable": "ROLANDO MORENO",
        "horas": "4", "cumplimiento": "NO", "archivo": "", "comentarios": "urgente",
        "previos": "", "prioridad": "ALTA", "riesgos": "", "restricciones": "",
        "fecha_resp": "", "clasificacion": "A", "fecha_alta": "2026-07-01",
        "ruta_critica": "", "zona": "", "contratista": "", "cuant_req": "", "cuant_real": "",
        "dias_json": json.dumps({"l": True, "m": False, "x": False, "j": False,
                                 "v": False, "s": False, "d": False}),
    }])
    borradores = RepositorioBorradores(engine).listar()

    assert len(borradores) == 1
    b = borradores[0]
    # camelCase: es como los nombra el original al mandarlos al frontend.
    assert b["concepto"] == "Cambiar filtro"
    assert b["comentariosPrevios"] == ""
    assert b["archivoUrl"] == ""
    assert b["dias"]["l"] is True


def test_un_borrador_sin_concepto_se_descarta():
    """Filas que quedaron de una captura abandonada."""
    engine = _engine_borradores([
        {"concepto": "Real", "dias_json": "{}"},
        {"concepto": "   ", "dias_json": "{}"},
        {"concepto": None, "dias_json": "{}"},
    ])
    assert [b["concepto"] for b in RepositorioBorradores(engine).listar()] == ["Real"]


def test_dias_json_corrupto_no_tumba_la_cola_completa():
    """
    El original envuelve el `JSON.parse` en try/catch: un borrador con el JSON
    roto no puede impedir que se carguen los demás.
    """
    engine = _engine_borradores([{"concepto": "Con JSON roto", "dias_json": "{esto no es json"}])
    b = RepositorioBorradores(engine).listar()[0]
    assert b["dias"] == DIAS_VACIOS


def test_sincronizar_reemplaza_la_cola_no_la_fusiona():
    """
    El original hace `sheet.clear()` y reescribe. El frontend manda siempre la
    lista completa, así que fusionar dejaría vivos los borradores ya borrados.
    """
    engine = _engine_borradores([{"concepto": "VIEJO", "dias_json": "{}"}])
    repo = RepositorioBorradores(engine)

    repo.reemplazar([{"concepto": "NUEVO", "especialidad": "HVAC"}])

    conceptos = [f.get("concepto") for f in engine.select("ppc_borradores")]
    assert conceptos == ["NUEVO"]
    assert "VIEJO" not in conceptos


def test_sincronizar_aplica_el_respaldo_de_cumplimiento():
    """Regla del original: sin valor, 'NO'."""
    engine = _engine_borradores()
    RepositorioBorradores(engine).reemplazar([{"concepto": "X"}])
    assert engine.select("ppc_borradores")[0]["cumplimiento"] == "NO"


def test_sincronizar_serializa_los_dias_como_json():
    engine = _engine_borradores()
    RepositorioBorradores(engine).reemplazar([{"concepto": "X", "dias": {"l": True}}])
    assert json.loads(engine.select("ppc_borradores")[0]["dias_json"]) == {"l": True}


def test_sincronizar_con_lista_vacia_deja_la_cola_limpia():
    engine = _engine_borradores([{"concepto": "VIEJO", "dias_json": "{}"}])
    assert RepositorioBorradores(engine).reemplazar([]) == 0
    assert engine.select("ppc_borradores") == []


def test_limpiar_borra_todo():
    engine = _engine_borradores([{"concepto": "A", "dias_json": "{}"},
                                 {"concepto": "B", "dias_json": "{}"}])
    RepositorioBorradores(engine).limpiar()
    assert engine.select("ppc_borradores") == []


def test_un_fallo_de_lectura_de_borradores_es_visible():
    class Roto(MemoryEngine):
        def select(self, tabla, **kw):
            raise RuntimeError("red caída")

    with pytest.raises(TablaAusente):
        RepositorioBorradores(Roto()).listar()


# --- Agenda y hábitos -------------------------------------------------

def test_guardar_evento_traduce_las_claves_de_hoja_a_columnas():
    engine = MemoryEngine({"personal_agenda": []})
    RepositorioAgenda(engine).guardar_evento(
        {"TITULO": "Gimnasio", "HORA_INICIO": "07:30", "USUARIO": "LUIS_CARLOS",
         "_rowIndex": 4, "_tempId": "t1"},
        "LUIS_CARLOS")

    fila = engine.select("personal_agenda")[0]
    assert fila["titulo"] == "Gimnasio"
    assert fila["hora_inicio"] == "07:30"
    # USUARIO -> usuario_raw, que es la columna real de la tabla.
    assert fila["usuario_raw"] == "LUIS_CARLOS"
    # El estado del cliente no se persiste.
    assert "_rowindex" not in fila and "_tempid" not in fila


def test_guardar_evento_genera_id_si_falta():
    engine = MemoryEngine({"personal_agenda": []})
    fila = RepositorioAgenda(engine).guardar_evento({"TITULO": "Comida"}, "LUIS")
    assert fila["id"].startswith("P-")


def test_guardar_evento_respeta_el_id_existente():
    """Con ID, es una actualización: no debe duplicar la fila."""
    engine = MemoryEngine({"personal_agenda": [{"id": "P-1", "titulo": "Viejo"}]})
    RepositorioAgenda(engine).guardar_evento({"ID": "P-1", "TITULO": "Nuevo"}, "LUIS")

    filas = engine.select("personal_agenda")
    assert len(filas) == 1
    assert filas[0]["titulo"] == "Nuevo"


def test_el_usuario_del_payload_gana_sobre_el_de_la_sesion():
    engine = MemoryEngine({"personal_agenda": []})
    fila = RepositorioAgenda(engine).guardar_evento(
        {"TITULO": "X", "USUARIO": "OTRO"}, "LUIS_CARLOS")
    assert fila["usuario_raw"] == "OTRO"


def test_guardar_habito_avisa_que_la_tabla_no_existe():
    """
    `habits_log` está mapeada en sheets.py pero no aparece en el inventario de
    tablas reales. En vez de fallar con un error opaco de PostgREST, el mensaje
    dice qué crear y dónde está el DDL.
    """
    engine = EngineEstricto({"personal_agenda": []})  # sin habits_log

    with pytest.raises(TablaAusente) as exc:
        RepositorioAgenda(engine).guardar_habito({"HABITO": "Leer"}, "LUIS")

    assert "habits_log" in str(exc.value)
    assert "DDL_PENDIENTE.sql" in str(exc.value)


def test_guardar_habito_funciona_cuando_la_tabla_existe():
    engine = MemoryEngine({"habits_log": []})
    fila = RepositorioAgenda(engine).guardar_habito(
        {"HABITO": "Leer 30min", "META": 5, "LOG_JSON": "[true,false]"}, "LUIS")

    assert fila["id"].startswith("H-")
    assert engine.select("habits_log")[0]["habito"] == "Leer 30min"


def test_el_servicio_traduce_tabla_ausente_a_mensaje_visible(monkeypatch):
    """
    Un stub devolvía `{success:false}` con un aviso; lo que no puede pasar es
    que un fallo se convierta en `{success:true}`.
    """
    from api.services import tracker_store

    monkeypatch.setattr(tracker_store, "_repo",
                        lambda clase: RepositorioAgenda(EngineEstricto({})))
    res = tracker_store.save_habit_log({"HABITO": "Leer"}, "LUIS")

    assert res["success"] is False
    assert "habits_log" in res["message"]


# --- Banco de información --------------------------------------------

ENCABEZADOS_VENTAS = ["FOLIO", "CLIENTE", "CONCEPTO", "F. INICIO", "MONTO"]


def _hoja_ventas():
    return [
        ENCABEZADOS_VENTAS,
        ["AV-1", "ACME INDUSTRIAL", "Cotizar nave", "05/03/26", "1000"],
        ["AV-2", "GLOBEX", "Otra cosa", "07/03/26", "2000"],
        ["AV-3", "ACME INDUSTRIAL", "Fuera de mes", "05/04/26", "3000"],
        ["AV-4", "", "Sin cliente", "05/03/26", "4000"],
    ]


@pytest.fixture
def store_ventas(monkeypatch):
    from api.services import tracker_store

    monkeypatch.setattr(tracker_store, "read_values",
                        lambda n: _hoja_ventas() if n == tracker_store.rules.SALES_MASTER_SHEET else [])
    return tracker_store


def test_banco_filtra_por_cliente_y_periodo(store_ventas):
    res = store_ventas.fetch_info_bank_data(2026, "MARZO", "ACME INDUSTRIAL")
    assert res["success"] is True
    assert [f["FOLIO"] for f in res["data"]] == ["AV-1"]


def test_banco_acepta_el_cliente_abreviado(store_ventas):
    """
    El original compara con inclusión bidireccional para tolerar abreviaturas y
    sufijos en la hoja. "ACME" debe encontrar "ACME INDUSTRIAL".
    """
    res = store_ventas.fetch_info_bank_data(2026, "MARZO", "ACME")
    assert [f["FOLIO"] for f in res["data"]] == ["AV-1"]


def test_banco_ignora_filas_sin_cliente(store_ventas):
    folios = [f["FOLIO"] for f in store_ventas.fetch_info_bank_data(2026, "MARZO", "")["data"]]
    assert "AV-4" not in folios


def test_banco_acepta_el_mes_por_numero_y_por_nombre(store_ventas):
    por_nombre = store_ventas.fetch_info_bank_data(2026, "MARZO", "ACME")["data"]
    por_numero = store_ventas.fetch_info_bank_data(2026, 3, "ACME")["data"]
    assert len(por_nombre) == len(por_numero) == 1


def test_banco_rechaza_un_mes_invalido(store_ventas):
    res = store_ventas.fetch_info_bank_data(2026, "MARBRERO", "ACME")
    assert res["success"] is False
    assert "Mes inválido" in res["message"]


# --- Calendario combinado --------------------------------------------

def test_el_calendario_une_tracker_y_agenda_personal(monkeypatch):
    from api.services import tracker_store

    hojas = {
        "ROLANDO MORENO": [["FOLIO", "CONCEPTO", "FECHA"],
                           ["RM-1", "Cambiar filtro", "05/03/26"]],
        "AGENDA_PERSONAL": [["ID", "TITULO", "FECHA", "USUARIO_RAW"],
                            ["P-1", "Gimnasio", "05/03/26", "ROLANDO MORENO"],
                            ["P-2", "Ajeno", "05/03/26", "OTRA PERSONA"]],
    }
    monkeypatch.setattr(tracker_store, "read_values", lambda n: hojas.get(n, []))

    res = tracker_store.fetch_combined_calendar("ROLANDO MORENO")
    assert res["success"] is True
    por_concepto = {f.get("CONCEPTO"): f for f in res["data"]}
    assert "Cambiar filtro" in por_concepto
    # El evento personal se expone con CONCEPTO y CLIENTE=PERSONAL, como el
    # original, para que el frontend lo distinga.
    assert por_concepto["Gimnasio"]["CLIENTE"] == "PERSONAL"
    assert "Ajeno" not in por_concepto


def test_el_calendario_deduplica_por_folio(monkeypatch):
    from api.services import tracker_store

    hojas = {
        "X": [["FOLIO", "CONCEPTO"], ["F-1", "Una"]],
        "X (VENTAS)": [["FOLIO", "CONCEPTO"], ["F-1", "La misma"]],
    }
    monkeypatch.setattr(tracker_store, "read_values", lambda n: hojas.get(n, []))
    assert len(tracker_store.fetch_combined_calendar("X")["data"]) == 1


def test_toñita_no_suma_una_hoja_de_ventas(monkeypatch):
    """Ella distribuye desde la tabla maestra; no tiene hoja `(VENTAS)` aparte."""
    from api.services import tracker_store

    pedidas = []
    monkeypatch.setattr(tracker_store, "read_values",
                        lambda n: pedidas.append(n) or [])
    tracker_store.fetch_combined_calendar("ANTONIA_VENTAS")
    assert "ANTONIA_VENTAS (VENTAS)" not in pedidas


def test_el_calendario_exige_una_hoja():
    from api.services import tracker_store

    assert tracker_store.fetch_combined_calendar("")["success"] is False


# --- PPC maestro ------------------------------------------------------

def test_ppc_data_devuelve_las_ultimas_300_en_orden_inverso(monkeypatch):
    from api.services import tracker_store

    filas = [["ID", "CONCEPTO"]] + [[f"P-{i}", f"Actividad {i}"] for i in range(400)]
    monkeypatch.setattr(tracker_store, "read_values",
                        lambda n: filas if n == tracker_store.PPC_MASTER_SHEET else [])

    data = tracker_store.fetch_ppc_data()["data"]
    assert len(data) == 300
    # La más reciente primero, y solo las últimas 300 de las 400.
    assert data[0]["concepto"] == "Actividad 399"
    assert data[-1]["concepto"] == "Actividad 100"


def test_ppc_data_descarta_filas_sin_concepto(monkeypatch):
    from api.services import tracker_store

    filas = [["ID", "CONCEPTO"], ["P-1", "Real"], ["P-2", ""]]
    monkeypatch.setattr(tracker_store, "read_values",
                        lambda n: filas if n == tracker_store.PPC_MASTER_SHEET else [])
    assert [d["id"] for d in tracker_store.fetch_ppc_data()["data"]] == ["P-1"]


# --- Logout -----------------------------------------------------------

def test_logout_registra_en_la_auditoria(monkeypatch):
    from api.services import tracker_store
    from backend.services import auditoria

    registros = []
    monkeypatch.setattr(auditoria, "registrar",
                        lambda usuario, accion, detalle: registros.append((usuario, accion, detalle)))

    assert tracker_store.logout("luis_carlos")["success"] is True
    assert registros == [("LUIS_CARLOS", "LOGOUT", "Sesión cerrada")]


def test_logout_no_falla_si_la_auditoria_falla(monkeypatch):
    """Cerrar sesión no puede depender de que la bitácora responda."""
    from api.services import tracker_store
    from backend.services import auditoria

    def explota(*_a, **_k):
        raise RuntimeError("red caída")

    monkeypatch.setattr(auditoria, "registrar", explota)
    assert tracker_store.logout("LUIS")["success"] is True


# --- Directorio -------------------------------------------------------

def test_alta_de_empleado_rechaza_duplicados(monkeypatch):
    from api.services import sheets, tracker_store

    monkeypatch.setattr(sheets, "get_directory_from_db",
                        lambda: [{"name": "MIGUEL GALLARDO", "dept": "ELECTROMECANICA",
                                  "type": "ESTANDAR"}])
    res = tracker_store.add_employee("miguel gallardo", "electromecanica")
    assert res["success"] is False
    assert "ya está" in res["message"]


def test_alta_de_empleado_exige_nombre_y_departamento():
    from api.services import tracker_store

    assert tracker_store.add_employee("", "HVAC")["success"] is False
    assert tracker_store.add_employee("ALGUIEN", "")["success"] is False


def test_si_la_escritura_del_directorio_falla_el_alta_no_se_da_por_buena(monkeypatch):
    from api.services import sheets, tracker_store

    monkeypatch.setattr(sheets, "get_directory_from_db", lambda: [])

    class ManagerRoto:
        def append_row(self, *_a, **_k):
            return None  # es lo que devuelve `append_row` cuando no persiste

    monkeypatch.setattr(tracker_store, "_manager", lambda: ManagerRoto())
    res = tracker_store.add_employee("NUEVA PERSONA", "HVAC")

    assert res["success"] is False
    assert "NO se guardó" in res["message"]


def test_baja_de_empleado_exige_nombre():
    from api.services import tracker_store

    assert tracker_store.delete_employee("")["success"] is False
