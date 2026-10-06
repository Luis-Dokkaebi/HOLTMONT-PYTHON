"""La Fase 2 del pipeline del dashboard: la app servida y recorrida en Chromium.

Nada simulado: `streamlit run` de verdad en un puerto libre y Playwright
pulsando los controles. Es la prueba que habría atrapado el hueco de `gs3.py`:
buscaba `st.error` con selectores (`stAlertErrorIcon`, `.alert-danger`) que la
versión actual de Streamlit ya no pinta, así que un error en pantalla pasaba la
auditoría y se publicaba.

Si Chromium no está instalado, `tests/conftest.py` salta este módulo con el
motivo a la vista (mismo criterio que el resto de las pruebas de UI).
"""

from __future__ import annotations

import base64
import signal
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

from agente_full import pipeline_dashboard as pipeline

APP_CON_TODOS_LOS_CONTROLES = '''
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Mezanine", layout="wide")
datos = pd.DataFrame({"partida": ["Acero", "Losa", "Pintura"], "monto": [1200, 800, 300]})
partidas = st.sidebar.multiselect("Partidas", datos["partida"].tolist(), default=datos["partida"].tolist())
minimo = st.sidebar.slider("Monto mínimo", 0, 1000, 0)
orden = st.radio("Orden", ["Mayor a menor", "Menor a mayor"])
vista = st.selectbox("Vista", ["Tabla", "Gráfica"])
filtrado = datos[datos["partida"].isin(partidas) & (datos["monto"] >= minimo)]
if filtrado.empty:
    st.warning("Sin partidas con ese filtro.")
    st.stop()
tabla, grafica = st.tabs(["Tabla", "Gráfica"])
with tabla:
    st.dataframe(filtrado, width="stretch")
with grafica:
    st.bar_chart(filtrado, x="partida", y="monto")
st.button("Recalcular")
st.metric("Total", f"{filtrado['monto'].sum():,}")
'''


def test_una_app_sana_pasa_el_recorrido_completo():
    ok, mensaje, captura = pipeline.validar_en_navegador(APP_CON_TODOS_LOS_CONTROLES)

    assert ok is True, mensaje
    assert captura is None


def test_una_excepcion_al_cargar_se_reporta_con_captura():
    ok, mensaje, captura = pipeline.validar_en_navegador("import streamlit as st\nst.title('x')\nvalor = 1 / 0\n")

    assert ok is False
    assert "[la carga inicial del dashboard]" in mensaje
    assert "Excepción en UI" in mensaje
    assert "ZeroDivisionError" in mensaje
    assert base64.b64decode(captura).startswith(b"\x89PNG")


def test_un_st_error_que_aparece_al_pulsar_el_boton_se_detecta():
    app = 'import streamlit as st\nif st.button("Calcular"):\n    st.error("El total no cuadra")\n'

    ok, mensaje, _ = pipeline.validar_en_navegador(app)

    assert ok is False
    assert "[el clic en botón interactivo]" in mensaje
    assert "El total no cuadra" in mensaje


def test_un_error_en_la_consola_del_navegador_se_reporta():
    app = ("import streamlit as st\nimport streamlit.components.v1 as components\n"
           "components.html(\"<script>console.error('fallo del componente')</script>\")\n")

    ok, mensaje, _ = pipeline.validar_en_navegador(app)

    assert ok is False
    assert "[Fallo crítico en consola del navegador]" in mensaje
    assert "fallo del componente" in mensaje


def test_un_aviso_o_un_exito_no_se_confunden_con_un_error(tmp_path):
    ruta = tmp_path / "app.py"
    ruta.write_text('import streamlit as st\nst.warning("Ojo")\nst.info("Dato")\nst.success("Listo")\n',
                    encoding="utf-8")
    puerto = pipeline.puerto_libre()
    with open(tmp_path / "streamlit.log", "w", encoding="utf-8") as bitacora:
        proceso = pipeline.arrancar_streamlit(ruta, puerto, bitacora)
        try:
            assert pipeline.esperar_servidor(proceso, puerto)[0] is True
            with sync_playwright() as playwright:
                navegador = playwright.chromium.launch(headless=True)
                pagina = navegador.new_page()
                pagina.goto(f"http://localhost:{puerto}")
                pagina.wait_for_selector('[data-testid="stAlertContentSuccess"]', timeout=20000)
                errores = pipeline.escanear_errores(pagina)
                navegador.close()
        finally:
            pipeline.detener(proceso)

    assert errores == []


def test_si_la_auditoria_truena_se_reporta_y_el_servidor_se_detiene(monkeypatch):
    def auditoria_que_truena(url):
        raise RuntimeError("Chromium se cerró")

    monkeypatch.setattr(pipeline, "auditar_pagina", auditoria_que_truena)

    ok, mensaje, captura = pipeline.validar_en_navegador("import streamlit as st\nst.write('ok')\n")

    assert ok is False
    assert "Error durante la inspección de Playwright: Chromium se cerró" in mensaje
    assert captura is None


def test_un_servidor_que_muere_al_arrancar_se_reporta():
    proceso = subprocess.Popen([sys.executable, "-c", "pass"])
    proceso.wait()

    assert pipeline.esperar_servidor(proceso, pipeline.puerto_libre()) == (
        False, "El servidor Streamlit falló al iniciar en subproceso.")


def test_un_servidor_que_no_contesta_se_corta_por_tiempo():
    proceso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        ok, mensaje = pipeline.esperar_servidor(proceso, pipeline.puerto_libre(), intentos=2, pausa=0.01)
    finally:
        pipeline.detener(proceso)

    assert ok is False
    assert mensaje.startswith("Timeout")
    assert proceso.poll() is not None


def test_un_servidor_que_ignora_la_senal_de_salida_se_mata():
    proceso = subprocess.Popen([sys.executable, "-c",
                                "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                                "print('listo', flush=True); time.sleep(60)"], stdout=subprocess.PIPE)
    proceso.stdout.readline()
    inicio = time.monotonic()

    pipeline.detener(proceso)

    assert proceso.returncode == -signal.SIGKILL
    assert time.monotonic() - inicio < 10


def test_detener_un_proceso_ya_terminado_no_hace_nada():
    proceso = subprocess.Popen([sys.executable, "-c", "pass"])
    proceso.wait()

    pipeline.detener(proceso)

    assert proceso.returncode == 0


def test_la_app_servida_no_ve_las_claves(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY_AGENT_3", "clave-secreta")
    app = ("import os\nimport streamlit as st\n"
           "if any('GEMINI' in k for k in os.environ):\n    st.error('FUGA')\nst.write('ok')\n")

    ok, mensaje, _ = pipeline.validar_en_navegador(app)

    assert ok is True, mensaje
