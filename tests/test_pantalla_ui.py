"""
La Pantalla de McDonald's vista como la ve una televisión colgada.

`tests/test_pantalla.py` cubre el preparado de los datos. Aquí se comprueba lo
que esa suite no puede: que la televisión **entre sin login**, que **rote** las
páginas y —lo importante— que **avise cuando deja de recibir datos**.

Los tres fallan callados, que es la razón de que estén:

- Si la pantalla no salta el login, la pared muestra el formulario de acceso
  para siempre. Nadie va a ir a teclear nada en una televisión.
- Si no rota, las filas de la página dos no existen para nadie y la hoja parece
  más corta de lo que es.
- **Si no avisa de datos viejos, una pantalla congelada se ve idéntica a una
  viva.** Alguien lee una tabla de anteayer creyéndola de ahora. Es el único
  fallo de este módulo que hace daño de verdad, y el único que ningún error de
  consola delata.

El reloj del navegador se adelanta con `page.clock` en vez de esperar de verdad:
una prueba que duerme dos minutos para ver el aviso es una prueba que nadie
vuelve a correr (R8).
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

HOJA = "EDUARDO MANZANARES"

COLUMNAS = ["FOLIO", "CONCEPTO", "AVANCE", "FECHA_ESTIMADA_FIN", "PRIORIDAD", "ESTATUS"]


def _fila(folio: str) -> dict:
    return {"FOLIO": folio, "CONCEPTO": f"Trabajo {folio}", "AVANCE": "40",
            "FECHA_ESTIMADA_FIN": "2026-09-20", "PRIORIDAD": "ALTA",
            "ESTATUS": "ASIGNADO"}


def _respuesta(paginas, **extra) -> dict:
    cuerpo = {"success": True, "hoja": HOJA, "columnas": COLUMNAS,
              "paginas": paginas, "filas_por_pagina": 12,
              "total": sum(len(p) for p in paginas),
              "pendientes": sum(len(p) for p in paginas),
              "recortado": False, "generado_en": "2026-09-12T17:30:00"}
    cuerpo.update(extra)
    return cuerpo


def _doblar_pantalla(page, cuerpo: dict, fallar_despues_de: int = None) -> None:
    """
    Sustituye `/api/pantalla`. Con `fallar_despues_de`, las siguientes cortan.

    El corte simula lo que de verdad pasa en una oficina: el wifi de la
    televisión se cae y nadie lo nota porque la tabla sigue ahí.
    """
    llamadas = {"n": 0}

    def responder(ruta):
        llamadas["n"] += 1
        if fallar_despues_de is not None and llamadas["n"] > fallar_despues_de:
            ruta.abort()
            return
        ruta.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    page.route("**/api/pantalla*", responder)


def _abrir(page, hoja: str = HOJA):
    """
    Abre la pantalla y **espera a que la primera respuesta haya llegado**.

    El `#pantallaTv` aparece de inmediato —`activa` se pone antes de pedir los
    datos—, así que esperarlo a él no garantiza nada. Sin esperar al contenido,
    el primer `fetch` sigue en vuelo mientras la prueba adelanta el reloj y
    resuelve después, reiniciando el contador de frescura: la prueba del aviso
    de datos viejos fallaba por eso, y las demás habrían sido intermitentes.
    """
    page.goto(f"{BASE_URL}/?pantalla={hoja.replace(' ', '%20')}")
    page.wait_for_selector("#pantallaTv", timeout=15000)
    page.wait_for_selector("#pantallaTabla, #pantallaVacia, #pantallaError", timeout=15000)


def test_la_television_entra_sin_login_y_titula_con_la_hoja():
    """
    Sin esta rama la pared muestra el formulario de acceso indefinidamente, y
    no hay teclado delante de una televisión colgada.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")]]))
            _abrir(page)
            assert page.locator(".login-overlay").count() == 0
            assert HOJA in page.inner_text("#pantallaTitulo")
            assert "AV-1" in page.inner_text("#pantallaTabla")
        finally:
            navegador.close()


def test_sin_el_parametro_de_la_url_todo_sigue_como_antes():
    """
    La pantalla no puede colarse en la sesión normal de nadie: sin `?pantalla=`
    lo que tiene que salir es el login de siempre.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            page.goto(BASE_URL)
            page.wait_for_selector(".login-card", state="visible", timeout=15000)
            assert page.locator("#pantallaTv").count() == 0
        finally:
            navegador.close()


def test_las_columnas_que_se_pintan_son_las_que_manda_el_backend():
    """
    Seis, no las veintiuna de la hoja. Si el frontend pintara las suyas, cambiar
    la lista en `pantalla.py` no cambiaría nada y nadie sabría por qué.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")]]))
            _abrir(page)
            encabezados = page.locator("#pantallaTabla thead th").all_inner_texts()
            assert [e.strip() for e in encabezados] == COLUMNAS
        finally:
            navegador.close()


def test_la_pantalla_rota_de_pagina_sola():
    """
    Nadie hace clic en una televisión. Sin rotación, las filas de la segunda
    página no las ve nunca nadie y la hoja parece más corta de lo que es.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            page.clock.install()
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")], [_fila("AV-2")]]))
            _abrir(page)
            assert "AV-1" in page.inner_text("#pantallaTabla")
            assert "Página 1 de 2" in page.inner_text("#pantallaPagina")

            page.clock.fast_forward("00:16")
            assert "AV-2" in page.inner_text("#pantallaTabla")
            assert "Página 2 de 2" in page.inner_text("#pantallaPagina")
        finally:
            navegador.close()


def test_una_sola_pagina_no_parpadea():
    """Rotar sobre una única página redibujaría la tabla cada 15 s sin motivo."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            page.clock.install()
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")]]))
            _abrir(page)
            page.clock.fast_forward("00:40")
            assert "Página 1 de 1" in page.inner_text("#pantallaPagina")
        finally:
            navegador.close()


def test_cuando_deja_de_llegar_informacion_la_pantalla_lo_grita():
    """
    **La prueba que justifica todo el módulo.**

    Con la red caída la tabla se queda como estaba y se ve perfectamente
    normal. Lo único que distingue esa pantalla de una al día es el contador,
    así que el contador tiene que seguir corriendo aunque las peticiones
    fallen, y ponerse en rojo solo.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            page.clock.install()
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")]]), fallar_despues_de=1)
            _abrir(page)
            assert "actualizado hace" in page.inner_text("#pantallaFrescura")

            # Dos minutos y pico sin que ninguna petición vuelva.
            page.clock.fast_forward("02:10")
            page.wait_for_selector("#pantallaFrescura.rancio", timeout=15000)
            assert "SIN ACTUALIZAR" in page.inner_text("#pantallaFrescura")
            # Los datos viejos siguen ahí: borrarlos dejaría la pared en blanco
            # por un corte de un segundo. Lo que no se hace es fingir que son
            # de ahora.
            assert "AV-1" in page.inner_text("#pantallaTabla")
        finally:
            navegador.close()


def test_al_volver_la_red_el_aviso_se_apaga():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            page.clock.install()
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")]]), fallar_despues_de=1)
            _abrir(page)
            page.clock.fast_forward("02:10")
            page.wait_for_selector("#pantallaFrescura.rancio", timeout=15000)

            # Vuelve la red: se reemplaza la ruta por una que sí responde.
            _doblar_pantalla(page, _respuesta([[_fila("AV-9")]]))
            page.clock.fast_forward("00:31")
            page.wait_for_function(
                "() => document.querySelector('#pantallaTabla')"
                "       .innerText.includes('AV-9')", timeout=15000)
            assert "actualizado hace" in page.inner_text("#pantallaFrescura")
        finally:
            navegador.close()


def test_una_hoja_sin_pendientes_lo_dice_en_vez_de_quedarse_en_blanco():
    """
    Ir al día no es un error. Una pared en negro se lee como "esto se rompió".
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            _doblar_pantalla(page, _respuesta([[]]))
            _abrir(page)
            assert "Sin pendientes" in page.inner_text("#pantallaVacia")
        finally:
            navegador.close()


def test_si_la_hoja_recorto_filas_la_pantalla_dice_cuantas_faltan():
    """Mostrar 200 de 340 sin decirlo esconde 140 tareas de alguien."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            _doblar_pantalla(page, _respuesta([[_fila("AV-1")]], recortado=True, total=340))
            _abrir(page)
            assert "de 340" in page.inner_text("#pantallaPagina")
        finally:
            navegador.close()


def test_si_la_primera_lectura_falla_se_dice_y_no_se_deja_la_pared_muda():
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1920, "height": 1080})
        try:
            page.route("**/api/pantalla*", lambda ruta: ruta.abort())
            _abrir(page)
            page.wait_for_selector("#pantallaError", timeout=15000)
            assert HOJA in page.inner_text("#pantallaError")
        finally:
            navegador.close()
