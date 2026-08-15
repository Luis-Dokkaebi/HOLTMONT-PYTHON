"""
Storage de archivos, canal de correo, métricas de productividad y cron diario.

La prueba con más valor es
`test_los_destinatarios_se_resuelven_por_rol_no_por_cuenta`: el original resuelve
`USER_DB['ADMIN_CONTROL']`, que no existe porque ADMIN_CONTROL es un rol y no una
cuenta, así que el reporte de productividad nunca llegó a quien debía. Es uno de
los tres bugs 🐛 que el SSD pedía corregir al migrar, no replicar.
"""

import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import correo, storage  # noqa: E402
from api.services import tracker_rules as rules  # noqa: E402


# --- Storage: rutas y decodificación ---------------------------------

def test_data_url_se_decodifica_y_da_el_mime():
    contenido, mime = storage.decodificar_data_url(
        "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4").decode())
    assert contenido == b"%PDF-1.4"
    assert mime == "application/pdf"


def test_se_acepta_base64_sin_prefijo():
    contenido, mime = storage.decodificar_data_url(base64.b64encode(b"hola").decode())
    assert contenido == b"hola"
    assert mime is None


def test_un_contenido_vacio_se_rechaza():
    with pytest.raises(ValueError):
        storage.decodificar_data_url("")


def test_la_ruta_del_banco_es_anio_mes_cliente():
    from datetime import datetime

    ruta = storage.ruta_de_archivo("cotizacion.pdf", "ACME INDUSTRIAL",
                                   datetime(2026, 3, 4, 10, 0))
    assert ruta.startswith("2026/MARZO/ACME INDUSTRIAL/")
    assert ruta.endswith(".pdf")


def test_sin_cliente_la_ruta_es_solo_anio_mes():
    from datetime import datetime

    ruta = storage.ruta_de_archivo("plano.dwg", None, datetime(2026, 7, 1))
    assert ruta.startswith("2026/JULIO/")
    assert "SIN_CLIENTE" not in ruta


def test_los_acentos_se_transliteran_no_se_borran():
    """`DISEÑO` no puede acabar como `DISEO`: rompería el nombre del cliente."""
    assert storage.limpiar_segmento("DISEÑO") == "DISENO"
    assert storage.limpiar_segmento("Cotización #5 (final)") == "Cotizacion 5 final"


def test_un_segmento_vacio_cae_al_respaldo():
    assert storage.limpiar_segmento("", "SIN_NOMBRE") == "SIN_NOMBRE"
    assert storage.limpiar_segmento("///") == "SIN_NOMBRE"


def test_dos_archivos_del_mismo_nombre_no_se_pisan():
    """
    En Drive dos homónimos conviven; en Storage el segundo sobreescribiría al
    primero, así que la ruta lleva marca de tiempo.
    """
    from datetime import datetime

    a = storage.ruta_de_archivo("plano.dwg", "ACME", datetime(2026, 3, 4, 10, 0, 0))
    b = storage.ruta_de_archivo("plano.dwg", "ACME", datetime(2026, 3, 4, 10, 0, 1))
    assert a != b


def test_sin_supabase_no_se_inventa_una_url(monkeypatch):
    """
    El fallo más dañino del adaptador era devolver `http://mock.url/file`, que se
    guardaba en la base como si el archivo existiera.
    """
    from api.services import supabase_manager

    monkeypatch.setattr(type(supabase_manager.sb_manager), "is_configured",
                        property(lambda self: False))
    res = storage.subir("data:text/plain;base64,aG9sYQ==", "text/plain", "a.txt")

    assert res["success"] is False
    assert "fileUrl" not in res


def test_la_ruta_se_extrae_de_la_url_publica(monkeypatch):
    monkeypatch.setenv(storage.BUCKET_ENV, "archivos")
    url = ("https://x.supabase.co/storage/v1/object/public/archivos/"
           "2026/MARZO/ACME/plano-123.dwg?token=abc")
    assert storage._ruta_desde_url(url) == "2026/MARZO/ACME/plano-123.dwg"


def test_una_url_ajena_no_se_archiva(monkeypatch):
    """Como el original, que ignoraba lo que no fuera una URL de Drive."""
    monkeypatch.setenv(storage.BUCKET_ENV, "archivos")
    assert storage._ruta_desde_url("https://drive.google.com/file/d/abc") is None


# --- Correo: el bug de destinatarios ---------------------------------

def test_los_destinatarios_se_resuelven_por_rol_no_por_cuenta():
    """
    ADMIN_CONTROL es un rol. El original buscaba `USER_DB['ADMIN_CONTROL']`, que
    no existe, así que la condición era siempre falsa y ni JAIME_OLIVO ni
    DIMAS_RAMOS —los dos con ese rol— recibieron nunca el reporte.
    """
    correos = correo.destinatarios_por_rol(["ADMIN_CONTROL"])

    assert correos, "ADMIN_CONTROL debe resolver a cuentas reales"
    assert "jaimeolivo@empresa.com" in correos
    assert "dimas.ramos@holtmont.com" in correos


def test_un_rol_sin_correos_devuelve_lista_vacia():
    assert correo.destinatarios_por_rol(["ROL_INEXISTENTE"]) == []


def test_no_se_repiten_destinatarios():
    dos_veces = correo.destinatarios_por_rol(["ADMIN", "ADMIN"])
    assert len(dos_veces) == len(set(dos_veces))


def test_sin_smtp_no_se_reporta_un_envio_que_no_ocurrio(monkeypatch):
    monkeypatch.delenv(correo.SMTP_HOST_ENV, raising=False)
    res = correo.enviar("Asunto", "<b>hola</b>", destinatarios=["a@b.com"])

    assert res["success"] is False
    assert correo.SMTP_HOST_ENV in res["message"]


def test_sin_destinatarios_no_se_intenta_enviar(monkeypatch):
    monkeypatch.setenv(correo.SMTP_HOST_ENV, "smtp.example.com")
    res = correo.enviar("Asunto", "<b>hola</b>", destinatarios=[])
    assert res["success"] is False
    assert "destinatarios" in res["message"].lower()


def test_el_cuerpo_del_reporte_incluye_resumen_kpis_y_alertas():
    html = correo.cuerpo_reporte(
        titulo="Reporte", subtitulo="sub", resumen_ia="Todo bien.\nSegunda línea.",
        kpis=[("Total", 10), ("A Tiempo", "90%")],
        alertas=[{"icon": "🔴", "mensaje": "Algo pasa", "severity": "ALTA"}])

    assert "Reporte" in html
    assert "Todo bien.<br>Segunda línea." in html   # los saltos se convierten
    assert "Total" in html and "90%" in html
    assert "Algo pasa" in html and "#dc3545" in html  # severidad ALTA en rojo


def test_sin_alertas_el_reporte_lo_dice():
    html = correo.cuerpo_reporte("T", "s", "resumen", [], [])
    assert "Sin alertas críticas" in html


# --- Métricas de productividad y las 3 reglas ------------------------

def _tarea(**kw):
    base = {"FOLIO": "X-1", "CONCEPTO": "Algo", "FECHA": "01/03/26"}
    base.update(kw)
    return base


def test_una_tarea_entregada_despues_del_compromiso_cuenta_como_tarde():
    m = rules.compute_productivity_metrics({
        "A": [_tarea(FECHA="01/03/26", FECHA_RESPUESTA="05/03/26", **{"F. ENTREGA": "10/03/26"})],
    })
    assert m["lateTasks"] == 1
    assert m["onTimePct"] == 0


def test_sin_fecha_de_compromiso_no_se_juzga_como_tarde():
    """No hay con qué comparar; el original solo marca `isLate` si puede."""
    m = rules.compute_productivity_metrics({"A": [_tarea()]})
    assert m["lateTasks"] == 0
    assert m["onTimePct"] == 100


def test_se_cuentan_restricciones_riesgos_y_prioridades():
    m = rules.compute_productivity_metrics({
        "A": [
            _tarea(RESTRICCIONES="falta material", RIESGOS="ALTO", PRIORIDAD="ALTA"),
            _tarea(RESTRICCIONES="", RIESGOS="BAJO", PRIORIDAD="MEDIA"),
            _tarea(RIESGOS="NINGUNO", PRIORIDAD=""),
        ],
    })
    assert m["tasksWithRestrictions"] == 1
    # BAJO y NINGUNO no cuentan como riesgo, igual que en el original.
    assert m["tasksWithRisks"] == 1
    assert m["priorityStats"] == {"BAJA": 0, "MEDIA": 1, "ALTA": 1, "URGENTE": 0,
                                  "SIN_PRIORIDAD": 1}


def test_urgente_es_una_prioridad_y_no_una_tarea_sin_prioridad():
    """
    `URGENTE` entró al catálogo de alta en 2026-08. Antes caía en SIN_PRIORIDAD
    junto con las filas que nadie clasificó, que es lo contrario de lo que el
    panel intenta mostrar: son las tareas más priorizadas de todas.
    """
    m = rules.compute_productivity_metrics({
        "A": [_tarea(PRIORIDAD="URGENTE"), _tarea(PRIORIDADES="urgente"), _tarea()],
    })
    assert m["priorityStats"]["URGENTE"] == 2
    assert m["priorityStats"]["SIN_PRIORIDAD"] == 1


def test_los_colaboradores_salen_ordenados_por_volumen():
    m = rules.compute_productivity_metrics({
        "POCO": [_tarea()],
        "MUCHO": [_tarea(), _tarea(), _tarea()],
    })
    assert [c["name"] for c in m["byCollabArr"]] == ["MUCHO", "POCO"]


def test_el_departamento_viene_del_directorio():
    m = rules.compute_productivity_metrics(
        {"MIGUEL GALLARDO": [_tarea()]},
        departamento_de={"MIGUEL GALLARDO": "ELECTROMECANICA"}.get)
    assert m["byDeptArr"] == [{"dept": "ELECTROMECANICA", "count": 1}]


def test_regla_1_entregas_a_tiempo_por_debajo_del_80():
    alertas = rules.productivity_alerts(
        {"totalTasks": 10, "onTimePct": 70, "restrictionsPct": 0, "byCollabArr": []})
    tipos = [a["type"] for a in alertas]
    assert "ENTREGAS_ATRASADAS" in tipos
    assert alertas[0]["severity"] == "ALTA"


def test_regla_1_no_dispara_con_80_exacto():
    """El umbral del original es `< 80`, no `<= 80`."""
    alertas = rules.productivity_alerts(
        {"totalTasks": 10, "onTimePct": 80, "restrictionsPct": 0, "byCollabArr": []})
    assert "ENTREGAS_ATRASADAS" not in [a["type"] for a in alertas]


def test_regla_1_no_dispara_sin_tareas():
    """Un mes sin tareas no es un mes con 0% a tiempo."""
    alertas = rules.productivity_alerts(
        {"totalTasks": 0, "onTimePct": 0, "restrictionsPct": 0, "byCollabArr": []})
    assert alertas == []


def test_regla_2_restricciones_por_encima_del_20():
    alertas = rules.productivity_alerts(
        {"totalTasks": 10, "onTimePct": 100, "restrictionsPct": 25, "byCollabArr": []})
    assert [a["type"] for a in alertas] == ["ALTAS_RESTRICCIONES"]
    assert alertas[0]["severity"] == "MEDIA"


def test_regla_3_colaborador_top_con_mal_cumplimiento():
    alertas = rules.productivity_alerts({
        "totalTasks": 10, "onTimePct": 100, "restrictionsPct": 0,
        "byCollabArr": [{"name": "ALGUIEN", "onTimePct": 40, "count": 6}],
    })
    assert [a["type"] for a in alertas] == ["PRODUCTIVIDAD_COLAB"]
    assert "ALGUIEN" in alertas[0]["mensaje"]


def test_regla_3_exige_al_menos_5_tareas():
    """Con 4 tareas el porcentaje no es significativo; el original pide >= 5."""
    alertas = rules.productivity_alerts({
        "totalTasks": 10, "onTimePct": 100, "restrictionsPct": 0,
        "byCollabArr": [{"name": "ALGUIEN", "onTimePct": 0, "count": 4}],
    })
    assert alertas == []


def test_las_tres_reglas_pueden_dispararse_juntas():
    alertas = rules.productivity_alerts({
        "totalTasks": 10, "onTimePct": 50, "restrictionsPct": 40,
        "byCollabArr": [{"name": "ALGUIEN", "onTimePct": 30, "count": 8}],
    })
    assert {a["type"] for a in alertas} == {
        "ENTREGAS_ATRASADAS", "ALTAS_RESTRICCIONES", "PRODUCTIVIDAD_COLAB"}


def test_el_prompt_de_productividad_lleva_las_metricas_clave():
    prompt = rules.build_productivity_prompt(
        {"totalTasks": 10, "onTimePct": 70, "lateTasks": 3, "avgDurationDays": 4.5,
         "restrictionsPct": 10, "risksPct": 5, "priorityStats": {}, "byCollabArr": []},
        "Marzo")
    assert "Marzo" in prompt
    assert "volumen_total" in prompt and "a_tiempo_pct" in prompt
    assert "180 palabras" in prompt


# --- Cron -------------------------------------------------------------

def test_el_cron_se_rechaza_sin_secreto_configurado(monkeypatch):
    """
    Un endpoint que lanza tres agentes y manda correos no puede quedar abierto
    porque nadie definió la variable.
    """
    from api import main

    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert main._cron_autorizado("cualquier-cosa") is False
    assert main._cron_autorizado("") is False


def test_el_cron_solo_acepta_el_secreto_correcto(monkeypatch):
    from api import main

    monkeypatch.setenv("CRON_SECRET", "el-bueno")
    assert main._cron_autorizado("el-bueno") is True
    assert main._cron_autorizado("el-malo") is False
    assert main._cron_autorizado(None) is False
