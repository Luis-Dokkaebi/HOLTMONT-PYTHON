"""
Pruebas unitarias e integración del motor de reglas en Python
(api/services/tracker_rules.py), espejo de tests/gas/run_tests.js.

Cubren los mismos 6 bloques del plan de migración para garantizar que el
stack de FastAPI/Supabase se comporta igual que el backend de Apps Script.

Ejecución:  python -m pytest tests/test_tracker_rules.py -v
"""

import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.tracker_rules import (  # noqa: E402
    Gatekeeper,
    apply_batch_update,
    apply_hot_potato,
    build_map_cot,
    build_notification_payload,
    build_quote_metrics_prompt,
    build_reverse_sync_payload,
    compute_quote_metrics,
    extract_phase_from_concepto,
    generate_prefix,
    is_progress_complete,
    is_terminal_status,
    resolve_tracker_target,
    resolve_user_email,
    rows_to_dicts,
    traffic_light_color,
)

TRACKER_HEADERS = ["ID", "ESPECIALIDAD", "CONCEPTO", "FECHA", "RELOJ", "AVANCE", "ESTATUS",
                   "COMENTARIOS", "ARCHIVO", "CLASIFICACION", "PRIORIDAD", "FECHA_RESPUESTA",
                   "RESPONSABLE", "CUMPLIMIENTO"]

SALES_HEADERS = ["FOLIO", "CLIENTE", "CONCEPTO", "VENDEDOR", "FECHA", "ESTATUS", "COMENTARIOS",
                 "ARCHIVO", "MONTO", "F2", "COTIZACION", "TIMELINE", "LAYOUT", "AVANCE",
                 "MAP COT", "PROCESO_LOG"]


def tracker(rows=None):
    """Hoja de tracker con filas de UI encima de los encabezados (caso real)."""
    grid = [
        ["HOLTMONT — TRACKER PERSONAL"] + [""] * (len(TRACKER_HEADERS) - 1),
        [""] * len(TRACKER_HEADERS),
        list(TRACKER_HEADERS),
    ]
    for row in rows or []:
        line = [""] * len(TRACKER_HEADERS)
        for key, value in row.items():
            line[TRACKER_HEADERS.index(key)] = value
        grid.append(line)
    return grid


def sales(rows=None):
    grid = [
        ["TABLA DE VENTAS"] + [""] * (len(SALES_HEADERS) - 1),
        list(SALES_HEADERS),
    ]
    for row in rows or []:
        line = [""] * len(SALES_HEADERS)
        for key, value in row.items():
            line[SALES_HEADERS.index(key)] = value
        grid.append(line)
    return grid


def find_row(values, text, headers=TRACKER_HEADERS):
    needle = str(text).upper()
    for i, row in enumerate(values):
        if needle in "|".join(str(c).upper() for c in row):
            if all(str(c).upper().strip() != needle for c in [row[headers.index("CONCEPTO")]] if False):
                pass
            return {"index": i, "row": row, "obj": {h: row[j] for j, h in enumerate(headers) if j < len(row)}}
    return None


def count_rows(values, text):
    needle = str(text).upper()
    return sum(1 for row in values if needle in "|".join(str(c).upper() for c in row))


def separator_index(values):
    for i, row in enumerate(values):
        if "TAREAS REALIZADAS" in "|".join(str(c).upper() for c in row):
            return i
    return -1


def is_archived(values, text):
    sep = separator_index(values)
    hit = find_row(values, text)
    if hit is None:
        return None
    return sep > -1 and hit["index"] > sep


# ======================================================================
# 1. SEMÁFORO
# ======================================================================

@pytest.mark.parametrize("clase,dias,esperado", [
    ("A", 0, "#00FF00"),
    ("A", 1, "#00FF00"),
    ("A", 2, "#FFFF00"),
    ("A", 4, "#FF0000"),
    ("AA", 11, "#00FF00"),
    ("AA", 13, "#FFFF00"),
    ("AA", 15, "#FF0000"),
    ("AA", 16, "#FF0000"),
    ("AAA", 24, "#00FF00"),
    ("AAA", 27, "#FFFF00"),
    ("AAA", 32, "#FF0000"),
])
def test_semaforo_por_clasificacion(clase, dias, esperado):
    assert traffic_light_color(clase, dias) == esperado


def test_semaforo_ignora_clasificaciones_desconocidas():
    assert traffic_light_color("", 10) is None
    assert traffic_light_color("B", 10) is None


# ======================================================================
# 2. RUTEO PROTEGIDO DE VENTAS ("LA LEY DE ANTONIA")
# ======================================================================

def test_antonia_puede_mandar_a_hoja_de_ventas_del_vendedor():
    res = resolve_tracker_target("EDUARDO MANZANARES (VENTAS)", "ANTONIA_VENTAS")
    assert res["sheet"] == "EDUARDO MANZANARES (VENTAS)"
    assert res["redirected"] is False


def test_otro_usuario_no_escribe_en_tabla_de_ventas_ajena():
    res = resolve_tracker_target("EDUARDO MANZANARES (VENTAS)", "LUIS_CARLOS")
    assert res["sheet"] == "EDUARDO MANZANARES"
    assert res["redirected"] is True
    assert res["reason"] == "SUFIJO_VENTAS_PURGADO"


def test_el_titular_si_escribe_en_su_propia_tabla_de_ventas():
    res = resolve_tracker_target("ANGEL SALINAS (VENTAS)", "ANGEL_SALINAS")
    assert res["sheet"] == "ANGEL SALINAS (VENTAS)"
    assert res["redirected"] is False


def test_core_de_ventas_protegido_para_usuarios_ajenos():
    res = resolve_tracker_target("ANTONIA_VENTAS", "EDUARDO_MANZANARES")
    assert res["sheet"] == "ANTONIA PINEDA LOPEZ"
    assert res["redirected"] is True
    assert res["reason"] == "CORE_VENTAS_PROTEGIDO"


def test_tarea_redirigida_usa_prefijo_ap():
    target = resolve_tracker_target("ANTONIA_VENTAS", "EDUARDO_MANZANARES")["sheet"]
    result = apply_batch_update(tracker(), [{"CONCEPTO": "TAREA GENERAL", "FECHA": "03/07/26"}], target)
    hit = find_row(result.values, "TAREA GENERAL")
    assert hit is not None
    assert str(hit["obj"]["ID"]).startswith("AP-")


# ======================================================================
# 3. FOLIOS Y PREFIJOS
# ======================================================================

@pytest.mark.parametrize("nombre,prefijo", [
    ("JAIME OLIVO", "JO-"),
    ("JESUS CANTU", "JC-"),
    ("LUIS CARLOS", "LC-"),
    ("ADMINISTRADOR", "LC-"),
    ("ANTONIA_VENTAS", "AV-"),
    ("ANTONIA PINEDA LOPEZ", "AP-"),
    ("RAMIRO RODRIGUEZ", "RR-"),
    ("SEBASTIAN PADILLA", "SP-"),
    ("TERESA GARZA", "TG-"),
    ("MIGUEL GALLARDO", "MG-"),          # fallback dinámico por iniciales
    ("EDUARDO MANZANARES (VENTAS)", "EM-"),
])
def test_prefijos_de_folio(nombre, prefijo):
    assert generate_prefix(nombre) == prefijo


@pytest.mark.parametrize("valor", ["", None, "   ", 0])
def test_prefijo_fallback_seguro(valor):
    assert generate_prefix(valor) == "PPC-"


def test_folio_se_asigna_al_crear_fila():
    result = apply_batch_update(tracker(), [{"CONCEPTO": "TAREA NUEVA", "FECHA": "05/07/26"}], "JAIME OLIVO")
    hit = find_row(result.values, "TAREA NUEVA")
    assert str(hit["obj"]["ID"]).startswith("JO-")
    assert result.data[0]["FOLIO"] == hit["obj"]["ID"]


# ======================================================================
# 4. GATEKEEPER, DUPLICIDAD Y AUTO-ARCHIVADO
# ======================================================================

def test_gatekeeper_bloquea_peticiones_duplicadas_con_mismo_tempid():
    gk = Gatekeeper()
    values = tracker()
    payload = {"CONCEPTO": "TAREA DOBLE CLICK", "FECHA": "06/07/26", "_tempId": "tmp_123"}
    for _ in range(5):
        result = apply_batch_update(values, [dict(payload)], "JAIME OLIVO", gatekeeper=gk)
        values = result.values
    assert count_rows(values, "TAREA DOBLE CLICK") == 1


def test_fallback_por_concepto_fecha_responsable():
    values = tracker([
        {"ID": "", "CONCEPTO": "REVISION DE PLANOS", "FECHA": "10/07/26",
         "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "PENDIENTE"}
    ])
    result = apply_batch_update(values, [{
        "CONCEPTO": "REVISION DE PLANOS", "FECHA": "10/07/26",
        "RESPONSABLE": "JAIME OLIVO", "COMENTARIOS": "COMENTARIO NUEVO",
    }], "JAIME OLIVO")

    assert count_rows(result.values, "REVISION DE PLANOS") == 1
    hit = find_row(result.values, "REVISION DE PLANOS")
    assert hit["obj"]["COMENTARIOS"] == "COMENTARIO NUEVO"
    assert hit["obj"]["ESTATUS"] == "PENDIENTE"          # no se pisó la fila original
    assert str(hit["obj"]["ID"]).startswith("JO-")        # fila reparada con folio nuevo


@pytest.mark.parametrize("valor,completo", [
    (1, True),          # número nativo de una celda con formato porcentaje
    (1.0, True),
    (100, True),
    ("100", True),
    ("100%", True),
    ("100,0", True),
    ("1", False),       # AGENTS.md §4: el string "1" es 1 %, no 100 %
    ("1.0", False),
    (0.5, False),
    ("40", False),
    ("", False),
    (None, False),
])
def test_evaluacion_de_avance(valor, completo):
    assert is_progress_complete(valor) is completo


@pytest.mark.parametrize("estatus,terminal", [
    ("HECHO", True),
    ("DONE", True),
    ("PERDIDA X PRECIO", True),
    ("GANADA", True),
    ("EN PROCESO", False),
    ("PENDIENTE", False),
    ("", False),
])
def test_estatus_terminales(estatus, terminal):
    assert is_terminal_status(estatus) is terminal


def test_auto_archivado_por_avance_estatus_y_cumplimiento():
    values = tracker([
        {"ID": "T-100", "CONCEPTO": "AVANCE NATIVO UNO", "FECHA": "01/07/26", "AVANCE": 1, "ESTATUS": "EN PROCESO"},
        {"ID": "T-101", "CONCEPTO": "AVANCE STRING CIEN", "FECHA": "01/07/26", "AVANCE": "100%", "ESTATUS": "EN PROCESO"},
        {"ID": "T-102", "CONCEPTO": "ESTATUS HECHO", "FECHA": "01/07/26", "AVANCE": "", "ESTATUS": "HECHO"},
        {"ID": "T-103", "CONCEPTO": "CUMPLIMIENTO SI", "FECHA": "01/07/26", "ESTATUS": "EN PROCESO", "CUMPLIMIENTO": "SI"},
        {"ID": "T-104", "CONCEPTO": "AVANCE UNO POR CIENTO", "FECHA": "01/07/26", "AVANCE": "1", "ESTATUS": "EN PROCESO"},
        {"ID": "T-105", "CONCEPTO": "TAREA ACTIVA CONTROL", "FECHA": "01/07/26", "AVANCE": "40", "ESTATUS": "EN PROCESO"},
    ])
    result = apply_batch_update(values, [{"ID": "T-105", "COMENTARIOS": "PING"}], "JAIME OLIVO")

    assert is_archived(result.values, "AVANCE NATIVO UNO") is True
    assert is_archived(result.values, "AVANCE STRING CIEN") is True
    assert is_archived(result.values, "ESTATUS HECHO") is True
    assert is_archived(result.values, "CUMPLIMIENTO SI") is True
    assert is_archived(result.values, "AVANCE UNO POR CIENTO") is False
    assert is_archived(result.values, "TAREA ACTIVA CONTROL") is False


# ======================================================================
# 5. PAPA CALIENTE Y REVERSE SYNC
# ======================================================================

def test_delegacion_papa_caliente_marca_fase_y_crea_fila():
    task = {"FOLIO": "AV-2025", "PROCESO": "CD", "INVOLUCRADOS": "ANGEL SALINAS"}
    master = {"CONCEPTO": "COTIZACION PLANTA", "CLIENTE": "ACME", "PROCESO_LOG": "[]", "MAP COT": "⚪ CD"}

    res = apply_hot_potato("ANTONIA_VENTAS", task, master, username="ANTONIA_VENTAS")

    assert res is not None
    assert res["step"] == "CD"
    assert res["workers"] == ["ANGEL SALINAS"]
    assert res["rows"][0]["CONCEPTO"] == "COTIZACION PLANTA [Calculo y Diseño]"
    assert res["rows"][0]["FOLIO"] == "AV-2025"
    assert "🔴 CD" in task["MAP COT"]
    assert json.loads(task["PROCESO_LOG"])[0]["status"] == "IN_PROGRESS"


def test_delegacion_con_contrato_del_frontend():
    task = {"FOLIO": "AV-2025", "_assignToWorker": ["ANGEL SALINAS"], "_assignStep": "CD"}
    res = apply_hot_potato("ANTONIA_VENTAS", task, {"CONCEPTO": "COTIZACION PLANTA"}, "ANTONIA_VENTAS")
    assert res["step"] == "CD"
    assert "[Calculo y Diseño]" in res["rows"][0]["CONCEPTO"]


def test_extraccion_de_fase_desde_concepto():
    assert extract_phase_from_concepto("COTIZACION PLANTA [Calculo y Diseño]") == "CD"
    assert extract_phase_from_concepto("COTIZACION PLANTA") == ""


def test_reverse_sync_cierra_la_fase_en_el_timeline():
    task = {"FOLIO": "AV-2025", "COTIZACION": "https://drive/cot.pdf", "AVANCE": "100", "ESTATUS": "DONE"}
    worker_row = {"CONCEPTO": "COTIZACION PLANTA [Calculo y Diseño]", "AVANCE": "100", "ESTATUS": "DONE"}
    master_row = {"PROCESO_LOG": "[]", "ESTATUS": "EN PROCESO", "AVANCE": "40"}

    payload = build_reverse_sync_payload("ANGEL SALINAS (VENTAS)", task, worker_row, master_row)

    assert payload["COTIZACION"] == "https://drive/cot.pdf"
    assert "DONE" in payload["PROCESO_LOG"]
    assert "🟢 CD" in payload["MAP COT"]


def test_el_cierre_de_una_fase_no_manda_estatus_ni_avance_a_la_maestra():
    """
    Regla vigente (decisión del dueño, 2026-08): una microtarea de papa caliente
    al 100 % **no** cierra la cotización.

    Esta prueba afirmaba lo contrario. No se borró ni se relajó: se actualizó
    porque la regla de negocio cambió, y el comentario de
    `REVERSE_SYNC_BLOCKED_KEYS` ya decía exactamente qué había que tocar el día
    que pasara. Lo que cierra la venta es que **todas** las fases estén verdes,
    no la primera que reporte.
    """
    task = {"FOLIO": "AV-2025", "COTIZACION": "https://drive/cot.pdf",
            "AVANCE": "100", "ESTATUS": "DONE", "estatus": "DONE", "Avance": "100"}
    worker_row = {"CONCEPTO": "COTIZACION PLANTA [Calculo y Diseño]", "AVANCE": "100", "ESTATUS": "DONE"}

    payload = build_reverse_sync_payload("ANGEL SALINAS (VENTAS)", task, worker_row, {"PROCESO_LOG": "[]"})

    claves = {k.upper() for k in payload}
    assert "ESTATUS" not in claves
    assert "AVANCE" not in claves
    # Lo que sí llega: el archivo que subió el trabajador y el timeline.
    assert payload["COTIZACION"] == "https://drive/cot.pdf"
    assert "🟢 CD" in payload["MAP COT"]


def test_reverse_sync_no_pisa_el_concepto_maestro():
    task = {"FOLIO": "AV-2025", "CONCEPTO": "COTIZACION PLANTA [Calculo y Diseño]"}
    payload = build_reverse_sync_payload("ANGEL SALINAS (VENTAS)", task, {}, {})
    assert "CONCEPTO" not in payload


def test_la_venta_maestra_sigue_activa_aunque_el_trabajador_cierre_su_fase():
    """
    El reverso de la prueba anterior, visto desde la tabla de Toñita.

    Antes esta prueba exigía que la venta pasara a TAREAS REALIZADAS en cuanto
    un trabajador reportara el 100 % de su fase. La regla nueva es que la venta
    se queda **activa**: su avance sigue en 40 % y lo único que cambia es el
    timeline, donde CD ya aparece en verde. Así Toñita puede seguir delegando
    las fases que faltan sobre una fila que sigue viva.
    """
    master_values = sales([{
        "FOLIO": "AV-2025", "CLIENTE": "ACME", "CONCEPTO": "COTIZACION PLANTA",
        "FECHA": "01/07/26", "ESTATUS": "EN PROCESO", "AVANCE": "40", "PROCESO_LOG": "[]",
    }])
    task = {"FOLIO": "AV-2025", "COTIZACION": "https://drive/cot.pdf", "AVANCE": "100", "ESTATUS": "DONE"}
    worker_row = {"CONCEPTO": "COTIZACION PLANTA [Calculo y Diseño]", "AVANCE": "100", "ESTATUS": "DONE"}

    payload = build_reverse_sync_payload("ANGEL SALINAS (VENTAS)", task, worker_row, {"PROCESO_LOG": "[]"})
    result = apply_batch_update(master_values, [payload], "ANTONIA_VENTAS", skip_notify=True)

    activas, historial, _ = rows_to_dicts(result.values)
    assert any(r.get("FOLIO") == "AV-2025" for r in activas), "la venta sigue abierta"
    assert not any(r.get("FOLIO") == "AV-2025" for r in historial)

    fila = next(r for r in activas if r.get("FOLIO") == "AV-2025")
    assert fila["AVANCE"] == "40", "el avance de la venta no lo fija una sola fase"
    assert fila["ESTATUS"] == "EN PROCESO"
    # Lo que sí se actualiza: el entregable del trabajador y el timeline.
    assert fila["COTIZACION"] == "https://drive/cot.pdf"
    assert "🟢 CD" in fila["MAP COT"]


def test_map_cot_marca_etapas_previas_como_terminadas():
    mapa = build_map_cot([], "EP")
    assert "🟢 L" in mapa and "🟢 CD" in mapa and "🔴 EP" in mapa and "⚪ CI" in mapa


# ======================================================================
# 6. MÉTRICAS, GEMINI Y WEBHOOK
# ======================================================================

def test_metricas_contabilizan_cotizaciones_cerradas_del_historial():
    filas = [
        {"FOLIO": "AV-1", "CLIENTE": "ACME", "VENDEDOR": "ANGEL SALINAS", "FECHA": "05/07/26",
         "ESTATUS": "GANADA", "CLASIFICACION": "A", "FECHA_TERMINO": "06/07/26"},
        {"FOLIO": "AV-2", "CLIENTE": "ACME", "VENDEDOR": "ANGEL SALINAS", "FECHA": "05/07/26",
         "ESTATUS": "PERDIDA X PRECIO", "CLASIFICACION": "AA", "FECHA_TERMINO": "25/07/26"},
        {"FOLIO": "AV-3", "CLIENTE": "BETA", "VENDEDOR": "TERESA GARZA", "FECHA": "05/07/26",
         "ESTATUS": "EN PROCESO", "CLASIFICACION": "AAA", "FECHA_TERMINO": "10/07/26"},
    ]
    m = compute_quote_metrics(filas, month=7, year=2026)

    assert m["totalCount"] == 3
    assert m["winLoss"]["ganada"] == 1
    assert m["winLoss"]["perdida"] == 1
    assert m["winLoss"]["enProceso"] == 1
    assert m["closeRate"] == 50.0
    assert m["slaSummary"]["A"]["ok"] == 1
    assert m["slaSummary"]["AA"]["fail"] == 1      # 20 días contra SLA de 14
    assert any(a["folio"] == "AV-2" for a in m["alerts"])


def test_metricas_respetan_el_filtro_de_periodo():
    filas = [
        {"FOLIO": "AV-1", "FECHA": "05/07/26", "ESTATUS": "GANADA"},
        {"FOLIO": "AV-2", "FECHA": "05/06/26", "ESTATUS": "GANADA"},
    ]
    assert compute_quote_metrics(filas, month=7, year=2026)["totalCount"] == 1


def test_prompt_de_gemini_pide_recomendacion_operativa():
    prompt = build_quote_metrics_prompt(compute_quote_metrics([], month=7, year=2026))
    assert "recomendación operativa" in prompt
    assert "180 palabras" in prompt


def test_payload_del_webhook_usa_iso_8601_con_z():
    payload = build_notification_payload("JEHU MARTINEZ", {
        "CONCEPTO": "NUEVA ASIGNACION", "FECHA": "07/07/26", "RESPONSABLE": "JEHU MARTINEZ",
    })
    assert payload["fechaInicio"] == "2026-07-07T00:00:00.000Z"
    assert payload["fechaInicio"].endswith("Z")
    assert datetime.strptime(payload["fechaInicio"], "%Y-%m-%dT%H:%M:%S.%fZ")
    assert payload["origen"] == "tracker general"
    assert payload["email"] == "jehu.martinez@holtmont.com"


def test_payload_distingue_tabla_de_ventas():
    payload = build_notification_payload("ANGEL SALINAS (VENTAS)", {"CONCEPTO": "COT", "FECHA": "07/07/26"})
    assert payload["origen"] == "tabla de ventas"
    assert payload["esVenta"] is True


@pytest.mark.parametrize("nombre,correo", [
    ("LUIS_CARLOS", "luis.carlos@holtmont.com"),
    ("ANTONIA_VENTAS", "antonia.pineda@holtmont.com"),
    ("JEHU MARTINEZ", "jehu.martinez@holtmont.com"),
])
def test_correos_corporativos(nombre, correo):
    assert resolve_user_email(nombre) == correo


def test_notificacion_solo_en_hojas_operativas():
    result = apply_batch_update(tracker(), [{"CONCEPTO": "X", "FECHA": "07/07/26",
                                             "RESPONSABLE": "JEHU MARTINEZ"}], "JEHU MARTINEZ")
    assert len(result.notifications) == 1

    espejo = apply_batch_update(tracker(), [{"CONCEPTO": "X", "FECHA": "07/07/26",
                                             "RESPONSABLE": "JEHU MARTINEZ"}], "ADMINISTRADOR")
    assert espejo.notifications == []
