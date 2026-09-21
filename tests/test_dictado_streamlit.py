"""
El dictado de la Pre Work Order de Streamlit, pulsando el botón de verdad.

`tests/test_transcripcion_prework.py` cubre `procesar_audio_de_dictado()`, que
es la decisión; aquí se recorre la pantalla entera con `AppTest`, el arnés
oficial de Streamlit, para comprobar lo que aquella no puede: que al pulsar
"Procesar Audio" el texto **aparece** y que un fallo de la estructuración **no
se lleva el dictado por delante**.

Es el mismo fallo que tenía el micrófono de `index.html`, en la otra pantalla
que lleva el mismo nombre: transcribir y estructurar son dos llamadas a dos
modelos distintos, y la vista trataba la caída de la segunda como si la primera
tampoco hubiera pasado. Quien acababa de dictar cinco minutos veía un error
rojo y ni una palabra de su propio texto.

Groq no se ejecuta: no hay clave en la suite. Se doblan `transcribir_audio` y
`extraer_informacion` —la frontera con el proveedor— desde dentro del guion que
`AppTest` ejecuta, que es el único punto donde se puede alcanzar el módulo
antes de que la vista corra.
"""

from __future__ import annotations

import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DICTADO = "Cambiar el tablero de la nave dos. Error del operador al medir, se repite."


def _guion(transcripcion: str, extraccion: str) -> str:
    """El guion que `AppTest` ejecuta: la vista real con el proveedor doblado.

    `st.audio_input` se sustituye por un archivo en memoria porque `AppTest` no
    sabe inyectar audio en ese widget; todo lo demás de Streamlit es el de
    verdad. El resto de la pantalla —los editores de materiales, el botón de
    guardar— se monta tal cual, así que si esta rama rompiera algo más, se vería
    aquí como una excepción.
    """
    return f"""
import io, sys
sys.path.insert(0, {RAIZ!r})
import streamlit as st
from streamlit_cotizador import work_order_view

work_order_view.transcribir_audio = lambda *a, **k: {transcripcion!r}
work_order_view.extraer_informacion = lambda *a, **k: {extraccion}


class _StreamlitConAudio:
    \"\"\"El módulo `st` real, salvo el micrófono, que siempre trae una grabación.\"\"\"

    def __getattr__(self, nombre):
        return getattr(st, nombre)

    def audio_input(self, *a, **k):
        return io.BytesIO(b"audio-de-prueba")

    @property
    def session_state(self):
        return st.session_state

    @property
    def secrets(self):
        class _SinSecretos:
            def get(self, *a, **k):
                return None
        return _SinSecretos()


work_order_view.st = _StreamlitConAudio()
work_order_view.render_work_order_view()
"""


def _correr(guion, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("BACKEND_ENGINE", "memoria")
    if RAIZ not in sys.path:
        sys.path.insert(0, RAIZ)

    app = AppTest.from_string(guion, default_timeout=90)
    app.run()
    assert not app.exception, f"La vista reventó al montar: {[str(e.value) for e in app.exception]}"

    procesar = [b for b in app.button if "Procesar" in b.label]
    assert procesar, f"No apareció el botón de procesar audio: {[b.label for b in app.button]}"
    procesar[0].click().run()
    assert not app.exception, f"La vista reventó al procesar: {[str(e.value) for e in app.exception]}"
    return app


def test_el_dictado_se_enseña_aunque_la_estructuracion_se_caiga(monkeypatch):
    app = _correr(
        _guion(DICTADO, '{"extraction": None, "error": "modelo saturado"}'), monkeypatch)

    textos = " ".join(m.value for m in app.markdown)
    assert DICTADO in textos, (
        "Se perdió el dictado porque falló el segundo modelo. En pantalla solo "
        f"quedó: {textos!r}")
    assert "modelo saturado" in [e.value for e in app.error], (
        "El fallo de la estructuración tiene que seguir viéndose.")


def test_un_dictado_con_la_palabra_error_llena_el_formulario(monkeypatch):
    """La palabra es vocabulario del oficio, no un código del proveedor."""
    extraccion = ('{"extraction": {"cliente": "MB", '
                  '"descripcion_generica": "Cambio de tablero en nave dos"}, "error": ""}')
    app = _correr(_guion(DICTADO, extraccion), monkeypatch)

    assert not [e.value for e in app.error], (
        f"El dictado se tomó por un fallo: {[e.value for e in app.error]}")
    assert app.session_state["wo_data"]["cliente"] == "MB"
    assert app.session_state["wo_data"]["conceptoDesc"] == "Cambio de tablero en nave dos"


@pytest.mark.parametrize(
    ("transcripcion", "aviso"),
    [("Error en transcripción: se cayó la red", "se cayó la red"),
     ("   ", "micrófono")],
)
def test_sin_texto_utilizable_la_pantalla_dice_por_que(monkeypatch, transcripcion, aviso):
    app = _correr(
        _guion(transcripcion, '{"extraction": {}, "error": ""}'), monkeypatch)

    avisos = " ".join(e.value for e in app.error)
    assert aviso in avisos, f"La pantalla no explica qué pasó: {avisos!r}"


def test_lo_dictado_se_reparte_en_materiales_personal_y_herramienta(monkeypatch):
    """El volcado al formulario, con los importes ya limpios de `$` y comas.

    El modelo devuelve los costos como los diría una persona ("$1,250.00") y el
    editor de la tabla espera números. La limpieza estaba escrita pero nunca se
    había ejercido: es la parte del dictado que termina en el precio de una
    cotización.
    """
    extraccion = (
        '{"extraction": {'
        '"lista_materiales": [{"cantidad": "4", "unidad": "pza", '
        '"descripcion": "Contactor 3 polos", "costo": "$1,250.00", "total": "$5,000.00"}], '
        '"lista_personal": [{"categoria": "Oficial Electricista", '
        '"salario_semanal": "$3,500.00", "cantidad_personas": "2", '
        '"semanas_cotizadas": "3", "salario_neto": "$21,000.00"}], '
        '"lista_herramientas": ["Multímetro", "Pinza de corte"], '
        '"restricciones_seguridad": "Trabajo con permiso de alto riesgo"'
        '}, "error": ""}')

    app = _correr(_guion(DICTADO, extraccion), monkeypatch)
    wo = app.session_state["wo_data"]

    assert wo["materiales"] == [{"quantity": "4", "unit": "pza",
                                 "description": "Contactor 3 polos",
                                 "cost": "1250.00", "total": "5000.00"}]
    assert wo["manoObra"] == [{"category": "Oficial Electricista", "salary": "3500.00",
                               "personnel": "2", "weeks": "3", "total": "21000.00"}]
    assert wo["herramientas"] == [
        {"description": "Multímetro", "quantity": "1", "unit": "pza"},
        {"description": "Pinza de corte", "quantity": "1", "unit": "pza"},
    ]
    assert wo["restricciones"]["seguridad"] == "Trabajo con permiso de alto riesgo"
