"""
El módulo del Agente de Consultas, recorrido como lo recorre una persona.

`tests/test_agente_sql.py` cubre el backend: guardarraíles, grafo y lista blanca
de destinatarios. `tests/test_rbac_config.py` cubre quién ve el módulo según
`/api/config`. Aquí se comprueba lo único que ninguna de las dos puede: que el
mosaico **abre algo** al pulsarlo y que el panel **muestra el SQL** que se
ejecutó.

Las dos fallan en silencio:

- Un módulo que el backend publica pero cuya rama falta en `openModule` no da
  error de consola: la cadena de `else if` se agota y el clic no hace nada. Ya
  pasó con `work_order_form`, y `PROSPECCION_GEO` lleva su propia prueba por lo
  mismo.
- Si el SQL no llega a la pantalla, una cifra que el modelo se inventó se ve
  exactamente igual que una que contó la base. Ese es el fallo que convierte a
  este módulo en peligroso en vez de útil, y no lanza ningún error.

El agente no se ejecuta de verdad: no hay `GROQ_API_KEY` en la suite y no la va
a haber. La respuesta se inyecta con un doble de `fetch` en el navegador, que es
la frontera correcta —lo que se prueba aquí es la vista, no el modelo—.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"

ETIQUETA = "Agente de Consultas"

VE_EL_MODULO = [
    ("ADMIN", "LUIS_CARLOS"),
    ("STAFF_USER", "ANTONIO_SALAZAR"),   # entra por la bandera, no por el rol
]

# ADMIN_CONTROL va aquí a propósito: ve Prospección y ve los tickets, así que
# "también ve el agente" es la conclusión que uno sacaría sin leer el código.
NO_VE_EL_MODULO = [
    ("ADMIN_CONTROL", "JAIME_OLIVO"),
    ("PPC_ADMIN", "JESUS_CANTU"),
    ("TONITA", "ANTONIA_VENTAS"),
    ("STAFF_USER", "TERESA_GARZA"),
    ("WORKORDER_USER", "PREWORK_ORDER"),
]


def _entrar(page, role: str, username: str) -> None:
    """Entra con la configuración real de esa cuenta, sin pasar por credenciales."""
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


def _doblar_respuesta_del_agente(page, cuerpo: dict) -> None:
    """
    Sustituye la respuesta de `/api/agente/consulta` sin tocar el resto de la red.

    El doble va en `fetch` —la frontera— y no en la función de Vue: así lo que
    se ejerce es el mismo camino que corre en producción, incluido el manejo de
    `success: false`.
    """
    page.route(
        "**/api/agente/consulta",
        lambda ruta: ruta.fulfill(
            status=200, content_type="application/json", body=__import__("json").dumps(cuerpo)
        ),
    )


def _doblar_diagnostico(page, cuerpo: dict) -> None:
    """Igual que el anterior, para `GET /api/agente/diagnostico`."""
    page.route(
        "**/api/agente/diagnostico",
        lambda ruta: ruta.fulfill(
            status=200, content_type="application/json", body=__import__("json").dumps(cuerpo)
        ),
    )


def test_el_modulo_aparece_para_quien_debe_y_no_para_los_demas():
    """
    Las dos mitades de la regla en la misma prueba.

    La segunda es la que se rompe callada: el agente lee `tasks` y `quotes`
    enteras, así que un módulo de más no lanza error, no aparece en ningún log
    y nadie lo reporta — solo alguien acaba viendo el trabajo de todos los
    departamentos.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            for role, username in VE_EL_MODULO:
                _entrar(page, role, username)
                assert page.locator(f".nav-item:has-text('{ETIQUETA}')").count() == 1, (
                    f"{role}/{username} debería ver el módulo del agente")

            for role, username in NO_VE_EL_MODULO:
                _entrar(page, role, username)
                assert page.locator(f".nav-item:has-text('{ETIQUETA}')").count() == 0, (
                    f"{role}/{username} NO debería ver el módulo del agente")
        finally:
            navegador.close()


def test_el_clic_en_el_mosaico_abre_el_panel():
    """
    Que `agente_sql_view` tenga su rama en `openModule`.

    Sin ella el clic no hace absolutamente nada y no se registra ningún error:
    es el fallo exacto que tuvo `work_order_form` y por el que existe esta
    prueba en los otros dos módulos.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.wait_for_selector("#agentePregunta", timeout=15000)
            assert page.locator("#agenteConsultarBtn").count() == 1
        finally:
            navegador.close()


def test_la_respuesta_se_pinta_junto_al_sql_que_la_produjo():
    """
    El SQL tiene que llegar a la pantalla, a un clic de distancia.

    Es la única forma que tiene quien lee la respuesta de comprobar de dónde
    salió el número. Sin él, una cifra inventada por el modelo y una contada
    por la base se ven idénticas.

    Va dentro de un `<details>` para no llenar el panel de SQL en cada consulta,
    así que la prueba lo despliega igual que lo desplegaría una persona. Basta
    con `text_content()` para leerlo cerrado, pero eso probaría que el texto
    está en el DOM, no que alguien puede llegar a verlo — que es lo que importa.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _doblar_respuesta_del_agente(page, {
                "success": True,
                "respuesta": "HVAC tiene 12 actividades abiertas.",
                "sql": "SELECT departamento, COUNT(*) FROM tasks GROUP BY 1",
                "filas": [{"departamento": "HVAC", "count": 12}],
                "intentos": 1,
            })

            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.fill("#agentePregunta", "¿cuántas actividades abiertas hay por área?")
            page.click("#agenteConsultarBtn")

            page.wait_for_selector("#agenteRespuesta", timeout=15000)
            assert "12 actividades abiertas" in page.inner_text("#agenteRespuesta")

            page.click("#agenteRespuesta summary")
            page.wait_for_selector("#agenteSql", state="visible", timeout=5000)
            assert "SELECT departamento" in page.inner_text("#agenteSql")
        finally:
            navegador.close()


def test_un_fallo_del_backend_se_dice_en_pantalla_y_no_se_finge_una_respuesta():
    """
    Sin `GROQ_API_KEY` el backend devuelve `success: false` con el motivo. La
    vista tiene que enseñarlo: un panel vacío se interpreta como "no hay datos",
    que es una respuesta — y falsa.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _doblar_respuesta_del_agente(page, {
                "success": False,
                "message": "El agente de IA no está disponible en este despliegue "
                           "(falta GROQ_API_KEY).",
            })

            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.fill("#agentePregunta", "lo que sea")
            page.click("#agenteConsultarBtn")

            page.wait_for_selector("#agenteAviso", timeout=15000)
            assert "GROQ_API_KEY" in page.inner_text("#agenteAviso")
            assert page.locator("#agenteRespuesta").count() == 0
        finally:
            navegador.close()


def test_desde_el_error_se_llega_al_diagnostico_y_dice_que_pieza_falta():
    """
    El botón que convierte «la consulta falló» en «falta esto».

    `GET /api/agente/diagnostico` existía desde antes y comprueba las cuatro
    piezas por separado, pero solo lo alcanzaba quien supiera escribir la ruta a
    mano. La persona que ve el aviso es exactamente la que necesita esa
    respuesta, y no tenía forma de pedirla: releía un mensaje que dice "ejecuta
    el DDL" con el DDL ya ejecutado, y ahí se acababa el camino.

    La prueba ejerce el recorrido entero —error, botón, diagnóstico— porque cada
    mitad por separado pasa sin que la otra exista: el backend puede responder
    perfecto y el botón no estar en pantalla, que es justo lo que pasaba.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _doblar_respuesta_del_agente(page, {
                "success": False,
                "message": "La consulta falló en la base: PostgREST no encuentra "
                           "la función agente_sql_consulta.",
            })
            _doblar_diagnostico(page, {
                "success": True,
                "listo": False,
                "modelo": {"ok": True, "detalle": "GROQ_API_KEY configurada"},
                "base": {"ok": True, "motor": "postgrest",
                         "detalle": "Motor de la aplicación: postgrest."},
                "consulta": {"ok": False,
                             "detalle": "PostgREST no encuentra la función."},
                "tablas": {"ok": False, "detalle": "El canal no responde.",
                           "por_esquema": {}},
            })

            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.fill("#agentePregunta", "lo que sea")
            page.click("#agenteConsultarBtn")

            page.wait_for_selector("#agenteDiagnosticoBtn", timeout=15000)
            page.click("#agenteDiagnosticoBtn")

            page.wait_for_selector("#agenteDiagnostico", timeout=15000)
            panel = page.inner_text("#agenteDiagnostico")
            # Las piezas que SÍ funcionan también se enseñan: media respuesta
            # ("algo falla") es lo que ya se tenía.
            assert "GROQ_API_KEY configurada" in panel
            assert "postgrest" in panel
            assert "PostgREST no encuentra la función" in panel
            assert "falta algo" in panel
        finally:
            navegador.close()


def test_el_diagnostico_nombra_la_tabla_que_no_se_puede_leer():
    """
    La avería que el `SELECT 1` no ve.

    El canal puede responder y el agente no encontrar nada, porque las tablas se
    llaman de otra forma o el rol no tiene SELECT sobre ellas. El backend ya lo
    mide por tabla; si la vista lo resume en un ❌ suelto, vuelve a perderse
    justo el dato que dice qué hacer.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _doblar_respuesta_del_agente(page, {
                "success": False, "message": "La consulta falló en la base.",
            })
            _doblar_diagnostico(page, {
                "success": True,
                "listo": False,
                "modelo": {"ok": True, "detalle": "GROQ_API_KEY configurada"},
                "base": {"ok": True, "motor": "postgrest", "detalle": "postgrest."},
                "consulta": {"ok": True, "detalle": "La base respondió."},
                "tablas": {
                    "ok": False,
                    "detalle": "No se pueden leer: quotes.",
                    "por_esquema": {
                        "tasks": {"tabla": "tasks", "ok": True,
                                  "detalle": "`tasks` se puede leer."},
                        "quotes": {"tabla": "quotes", "ok": False,
                                   "detalle": "No se pudo leer `quotes`: define "
                                              "AGENTE_SQL_TABLA_QUOTES."},
                    },
                },
            })

            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.fill("#agentePregunta", "lo que sea")
            page.click("#agenteConsultarBtn")
            page.wait_for_selector("#agenteDiagnosticoBtn", timeout=15000)
            page.click("#agenteDiagnosticoBtn")

            page.wait_for_selector("#agenteDiagnostico", timeout=15000)
            panel = page.inner_text("#agenteDiagnostico")
            assert "AGENTE_SQL_TABLA_QUOTES" in panel
            assert "`tasks` se puede leer." in panel
        finally:
            navegador.close()


def test_el_panel_enseña_lo_que_postgrest_dice_conocer():
    """
    La pieza que separa "el DDL no se ejecutó aquí" de "la caché está vieja".

    El backend la manda solo cuando el canal falla, así que si la vista no la
    pinta, el dato que resuelve el `PGRST202` se pierde justo en el único caso
    en que se produce.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(viewport={"width": 1500, "height": 950})
        try:
            _entrar(page, "ADMIN", "LUIS_CARLOS")
            _doblar_respuesta_del_agente(page, {
                "success": False, "message": "La consulta falló en la base.",
            })
            _doblar_diagnostico(page, {
                "success": True,
                "listo": False,
                "modelo": {"ok": True, "detalle": "GROQ_API_KEY configurada"},
                "base": {"ok": True, "motor": "postgrest", "detalle": "postgrest."},
                "consulta": {"ok": False, "detalle": "PGRST202."},
                "catalogo": {
                    "ok": False,
                    "tablas": ["quotes", "tasks"],
                    "detalle": "PostgREST NO conoce `/rpc/agente_sql_consulta` … "
                               "lo que falta es la función EN ESTE proyecto.",
                },
                "tablas": {"ok": False, "detalle": "El canal no responde.",
                           "por_esquema": {}},
            })

            page.click(f".nav-item:has-text('{ETIQUETA}')")
            page.fill("#agentePregunta", "lo que sea")
            page.click("#agenteConsultarBtn")
            page.wait_for_selector("#agenteDiagnosticoBtn", timeout=15000)
            page.click("#agenteDiagnosticoBtn")

            page.wait_for_selector("#agenteDiagnostico", timeout=15000)
            panel = page.inner_text("#agenteDiagnostico")
            assert "EN ESTE proyecto" in panel
            # Las tablas que PostgREST ve responden "¿se llaman así en mi base?"
            # sin abrir el panel de Supabase.
            assert "Tablas que ve PostgREST" in panel
            assert "quotes, tasks" in panel
        finally:
            navegador.close()
