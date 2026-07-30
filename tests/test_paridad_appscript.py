"""
Paridad con Apps Script: la prueba que guarda el resultado de la migración.

Cruza las funciones que `index.html` invoca de verdad contra el adaptador y
contra las rutas que la app registra, y exige que **ninguna quede sin atender**.
Es la versión ejecutable de "todo se puede usar igual que en el de AppScript":
si alguien añade una llamada al frontend sin su endpoint, o convierte un método
en stub, esto falla en vez de descubrirse en producción.

Se apoya en `REAL-HOLTMONT/CODIGO.js` para saber qué nombres son funciones del
backend original y no métodos del DOM. Si ese repo no está al lado, la prueba se
salta en vez de dar un falso verde.
"""

import os
import re
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

CODIGO_REAL = os.path.join(os.path.dirname(RAIZ), "REAL-HOLTMONT", "CODIGO.js")

# Stubs tolerados. Debe quedar vacío: es la lista de deuda declarada, y tenerla
# a la vista es mejor que un umbral numérico que nadie revisa.
STUBS_ACEPTADOS: set = set()


def _leer(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def superficie():
    if not os.path.exists(CODIGO_REAL):
        pytest.skip("REAL-HOLTMONT/CODIGO.js no está disponible para comparar.")

    codigo = _leer(CODIGO_REAL)
    index = _leer(os.path.join(RAIZ, "index.html"))
    adaptador = _leer(os.path.join(RAIZ, "api_service.js"))

    # Un nombre cuenta como RPC si `index.html` lo invoca como método Y
    # `CODIGO.js` lo define como función. Cruzar las dos fuentes evita tanto los
    # falsos positivos del DOM (`getElementById`) como los falsos negativos de
    # filtrar por prefijo, que fue lo que dejó `internalUpdateTask` y
    # `transcribirConGemini` sin verificar durante toda la migración.
    definidas = set(re.findall(r"^function\s+([A-Za-z0-9_]+)\s*\(", codigo, re.M))
    invocadas = sorted({n for n in re.findall(r"\.\s*([A-Za-z0-9_]+)\s*\(", index)
                        if n in definidas})
    return {"invocadas": invocadas, "adaptador": adaptador}


def _cuerpo_del_metodo(adaptador, nombre):
    m = re.search(r"^    " + nombre + r"\(.*?(?=\n    [a-zA-Z_/*]|\n\})",
                  adaptador, re.S | re.M)
    return m.group(0) if m else None


def test_el_frontend_no_invoca_nada_que_el_adaptador_no_defina(superficie):
    ausentes = [n for n in superficie["invocadas"]
                if _cuerpo_del_metodo(superficie["adaptador"], n) is None]
    assert not ausentes, (
        "Métodos que el frontend llama y el adaptador no define: "
        f"{ausentes}. Un método inexistente lanza TypeError sincrónico, que "
        "withFailureHandler no captura."
    )


def test_no_quedan_stubs(superficie):
    stubs = []
    for nombre in superficie["invocadas"]:
        cuerpo = _cuerpo_del_metodo(superficie["adaptador"], nombre) or ""
        if "_noPortado" in cuerpo or "_lecturaVacia" in cuerpo:
            stubs.append(nombre)

    pendientes = sorted(set(stubs) - STUBS_ACEPTADOS)
    assert not pendientes, f"Funciones que siguen siendo stub: {pendientes}"

    resueltos = sorted(STUBS_ACEPTADOS - set(stubs))
    assert not resueltos, (
        f"Estos ya no son stubs: {resueltos}. Quítalos de STUBS_ACEPTADOS."
    )


def test_cada_endpoint_que_el_adaptador_llama_existe_en_la_app(superficie):
    """
    Comprueba las rutas, no solo que el método tenga código.

    Un `fetch` a una ruta mal escrita devuelve 404 y el adaptador lo entrega al
    handler de éxito como si fuera una respuesta: el frontend vería
    `{detail: "Not Found"}` sin `success`, que es exactamente el tipo de fallo
    silencioso que la migración viene arrastrando.
    """
    from api.main import app

    registradas = {r.path for r in app.routes if hasattr(r, "path")}

    invalidas = []
    for nombre in superficie["invocadas"]:
        cuerpo = _cuerpo_del_metodo(superficie["adaptador"], nombre) or ""
        for ruta in re.findall(r"['\"`](/api/[^'\"`?]*)", cuerpo):
            # Las plantillas con interpolación quedan cortadas en el `${`.
            limpia = ruta.split("${")[0].rstrip("/")
            if limpia and limpia not in registradas:
                invalidas.append(f"{nombre} -> {ruta}")

    assert not invalidas, f"Rutas que el adaptador llama y la app no registra: {invalidas}"


def test_todas_las_funciones_vivas_estan_conectadas(superficie):
    """El resumen: cuántas de las funciones del original responden de verdad."""
    total = len(superficie["invocadas"])
    conectadas = 0
    for nombre in superficie["invocadas"]:
        cuerpo = _cuerpo_del_metodo(superficie["adaptador"], nombre) or ""
        if cuerpo and "_noPortado" not in cuerpo and "_lecturaVacia" not in cuerpo:
            conectadas += 1

    assert total > 30, f"Se detectaron solo {total} funciones: el cruce falló"
    assert conectadas == total, f"Conectadas {conectadas} de {total}"
