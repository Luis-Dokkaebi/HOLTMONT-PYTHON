"""
El módulo de Prospección, recorrido como lo recorre una persona.

`tests/test_prospeccion_geo.py` cubre el backend: filtros, bbox, polígono y el
contrato de las 10 columnas. Aquí se comprueba lo único que aquellas no pueden:
que el módulo **aparece en el menú de quien debe verlo y no en el de los demás**,
que el mapa **monta de verdad** en el navegador, y que mover un filtro **cambia
el conteo** que se ve en pantalla.

Las tres cosas fallan en silencio si no se prueban aquí:

- Un módulo que el backend publica pero cuya rama falta en `openModule` no da
  error de consola: la cadena de `else if` se agota y el clic no hace nada. Ya
  pasó con `work_order_form`.
- Un mapa cuyo `<div>` está oculto al crearse monta con 0×0 píxeles y se ve como
  un rectángulo gris. Leaflet no se queja.
- Un filtro que no llega a la consulta deja el conteo idéntico, y quien lo mueve
  cree que esa alcaldía tiene tantos negocios como toda la ciudad.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

# Cuentas reales del organigrama, una por rama de la regla de visibilidad: los
# roles ADMIN y ADMIN_CONTROL, más quien lleve la bandera `prospeccion` en su
# perfil.
VE_EL_MODULO = [
    ("ADMIN", "LUIS_CARLOS"),
    ("ADMIN_CONTROL", "JAIME_OLIVO"),
    ("STAFF_USER", "ANTONIO_SALAZAR"),   # entra por la bandera, no por el rol
]

# Compras y ventas quedaron fuera por decisión del dueño. Van en esta lista a
# propósito: es la lectura que uno esperaría —el módulo sirve para prospectar
# proveedores y clientes— y sin prueba volvería a colarse.
NO_VE_EL_MODULO = [
    ("STAFF_USER", "JUDITH_ECHAVARRIA"),  # COMPRAS y además vendedora
    ("TONITA", "ANTONIA_VENTAS"),         # la cuenta de la tabla maestra de ventas
    ("STAFF_USER", "RAMIRO_RODRIGUEZ"),   # VENTAS
    ("STAFF_USER", "EDUARDO_BENITEZ"),    # el STAFF_USER genérico
    ("WORKORDER_USER", "PREWORK_ORDER"),
    ("PPC_ADMIN", "JESUS_CANTU"),
]


def _entrar(page, role: str, username: str) -> None:
    """
    Entra con la configuración real de esa cuenta, sin pasar por credenciales.

    Se pide `/api/config` de verdad —no un doble— porque lo que esta prueba
    vigila es justamente que el backend y la vista coincidan.
    """
    page.goto(BASE_URL)
    page.wait_for_selector(".login-card", state="visible", timeout=15000)
    page.evaluate(
        """async ([role, username]) => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            const url = `/api/config?role=${role}&username=${username}`;
            app.config = await fetch(url).then(r => r.json());
            app.currentRole = role;
            app.currentUsername = username;
            app.isLoggedIn = true;
        }""",
        [role, username],
    )
    page.wait_for_selector(".nav-item", timeout=15000)


def _abrir_prospeccion(page) -> None:
    """Clic en el módulo, como lo abre una persona: no se fuerza `currentView`."""
    page.click(".nav-item:has-text('Prospección')")
    page.wait_for_selector("#geoMapa.leaflet-container", timeout=30000)


def _conteo(page) -> tuple:
    """`(mostrados, total)` leídos de la insignia, tal como se ven."""
    page.wait_for_function(
        "() => { const e = document.querySelector('#geoConteo');"
        " return e && !/ 0$/.test(e.textContent.trim()); }", timeout=30000)
    crudo = page.inner_text("#geoConteo")
    mostrados, total = crudo.split(" de ")
    return int(mostrados.replace(",", "")), int(total.replace(",", ""))


def test_el_modulo_aparece_para_el_rol_correcto_y_no_para_los_demas():
    """
    Las dos mitades de la regla, en la misma prueba: aparece para quien debe y
    **no** aparece para el resto.

    La segunda mitad es la que se rompe en silencio. Son 20,957 nombres con
    teléfono y correo: que el módulo se filtre a una cuenta de más no lanza
    ningún error, no aparece en ningún log y nadie lo reporta.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            for role, username in VE_EL_MODULO:
                _entrar(page, role, username)
                assert page.locator(".nav-item:has-text('Prospección')").count() == 1, (
                    f"{role}/{username} debería ver el módulo de Prospección")

            for role, username in NO_VE_EL_MODULO:
                _entrar(page, role, username)
                assert page.locator(".nav-item:has-text('Prospección')").count() == 0, (
                    f"{role}/{username} NO debería ver el módulo de Prospección")
        finally:
            navegador.close()


def test_el_mapa_monta_con_marcadores_al_abrir_el_modulo():
    """
    El clic tiene que llevar a un mapa con dato encima, no a un rectángulo gris.

    Se exige un `<div>` con tamaño real: un contenedor de 0 px monta sin error
    y se ve exactamente igual que un mapa roto.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _abrir_prospeccion(page)

            caja = page.locator("#geoMapa").bounding_box()
            assert caja["width"] > 400 and caja["height"] > 200, caja

            mostrados, total = _conteo(page)
            assert total > 0
            assert mostrados > 0

            # El clustering del notebook: con miles de puntos en la vista, lo
            # que se dibuja son burbujas agrupadas, no un marcador por fila.
            page.wait_for_selector(".marker-cluster", timeout=30000)
        finally:
            navegador.close()


def test_filtrar_por_alcaldia_reduce_el_conteo_de_la_pantalla():
    """
    El filtro tiene que llegar a la consulta. Si no llega, el conteo no se
    mueve y quien lo usó cree que Cuauhtémoc tiene los negocios de toda la
    ciudad.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _abrir_prospeccion(page)
            _, total_inicial = _conteo(page)

            page.select_option("#geoFiltroAlcaldia", "Cuauhtémoc")
            page.wait_for_function(
                "total => { const e = document.querySelector('#geoConteo');"
                " if (!e) return false;"
                " const t = parseInt(e.textContent.split(' de ')[1].replace(/,/g, ''), 10);"
                " return t > 0 && t < total; }",
                arg=total_inicial, timeout=30000)

            _, total_filtrado = _conteo(page)
            assert 0 < total_filtrado < total_inicial
        finally:
            navegador.close()


def test_solo_con_contacto_es_la_regla_que_manda_en_el_mapa():
    """
    R2, en la pantalla: el interruptor nace encendido y apagarlo **sube** el
    conteo, porque aparecen los que no tienen forma de ser contactados. Si
    naciera apagado, la lista que ve compras incluiría negocios a los que no se
    puede llamar.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _abrir_prospeccion(page)

            assert page.is_checked("#geoSoloContacto"), (
                "el filtro de contacto tiene que nacer encendido: es la regla del módulo")
            _, con_contacto = _conteo(page)

            page.uncheck("#geoSoloContacto")
            page.wait_for_function(
                "base => { const e = document.querySelector('#geoConteo');"
                " if (!e) return false;"
                " const t = parseInt(e.textContent.split(' de ')[1].replace(/,/g, ''), 10);"
                " return t > base; }",
                arg=con_contacto, timeout=30000)

            _, todos = _conteo(page)
            assert todos > con_contacto
        finally:
            navegador.close()
