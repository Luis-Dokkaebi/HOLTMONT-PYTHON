"""
La Pre Work Order vuelve a ser alcanzable, con su IA y su editor 3D.

Qué se rompió y por qué esto existe
-----------------------------------
La migración a FastAPI (commit 714fdcc) reescribió `index.html` y en el camino
perdió cuatro cosas que el frontend anterior sí tenía. El backend nunca fue el
problema: `/api/config` siempre publicó el módulo con `type: "work_order_form"`,
que es justo lo que la versión previa consumía.

1. `openModule()` dejó de tener la rama `work_order_form`, así que el mosaico
   "Pre Work Order" no abría nada. Sin error en consola: la cadena de `else if`
   simplemente se agota.
2. `loadConfig()` dejó de abrir el formulario al entrar con `WORKORDER_USER`,
   que era la única puerta real de esa cuenta.
3. Los botones de la Agencia Paperclip y del Plano 2D desaparecieron del marcado.
   El JavaScript que los atiende sobrevivió entero: quedó código huérfano.
4. El editor 3D Pascal perdió su vista y su `<iframe>`. El pegamento de
   `postMessage` sobrevivió, pero apuntando a un id que no existe en ningún
   archivo (`pascalIframe`) y con una forma de mensaje distinta a la que el fork
   de Pascal entiende (`PARCHE_PASCAL_EDITOR.md`).

Todas las comprobaciones son sobre el marcado porque ahí fue la pérdida. El
comportamiento de los agentes ya lo cubren `test_architect_pascal.py` y
`test_text_agents.py`.
"""

import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BaseIndexHtml(unittest.TestCase):
    """Carga `index.html` una sola vez por clase: son 700 KB."""

    @classmethod
    def setUpClass(cls):
        ruta = os.path.join(RAIZ, "index.html")
        if not os.path.exists(ruta):
            raise AssertionError(f"{ruta} no encontrado.")
        with open(ruta, "r", encoding="utf-8") as f:
            cls.contenido = f.read()

    # `assertRegex` imprime el texto donde buscó cuando falla. Aquí ese texto son
    # 700 KB de HTML por cada aserción rota, que sepultan el mensaje útil en la
    # salida de pytest. Estos dos ayudantes afirman lo mismo y solo dicen qué
    # falta.
    def _presente(self, patron: str, mensaje: str) -> None:
        self.assertTrue(re.search(patron, self.contenido), mensaje)

    def _ausente(self, patron: str, mensaje: str) -> None:
        self.assertFalse(re.search(patron, self.contenido), mensaje)


class TestElMosaicoAbreElFormulario(BaseIndexHtml):
    def test_open_module_rutea_el_tipo_work_order_form(self):
        """
        El tipo que publica `/api/config` tiene que tener rama en `openModule()`.

        Es la regresión de fondo: sin esta rama el clic en el mosaico no hace
        absolutamente nada, ni siquiera falla.
        """
        self._presente(
            r"m\.type\s*===\s*'work_order_form'",
            "`openModule()` no rutea el tipo `work_order_form` que manda el backend",
        )

    def test_el_formulario_se_abre_al_entrar_con_workorder_user(self):
        """
        `loadConfig()` abre la Pre Work Order sola, como antes de la migración.

        `PREWORK_ORDER` no tiene departamentos ni tracker: si el formulario no se
        abre al entrar, la cuenta aterriza en una pantalla vacía.
        """
        self._presente(
            r"WORKORDER_USER",
            "`index.html` ya no menciona el rol WORKORDER_USER",
        )
        self._presente(
            r"find\(\s*m\s*=>\s*m\.type\s*===\s*'work_order_form'\s*\)",
            "`loadConfig()` no busca el módulo de Pre Work Order para abrirlo solo",
        )

    def test_open_module_delega_en_vez_de_copiar_la_inicializacion(self):
        """
        El formulario se arma en `abrirPreWorkOrder()`, no dentro de `openModule()`.

        Son dos entradas —el mosaico y el arranque de sesión— y el bloque que
        deja `workorderData` en blanco son 15 líneas. Copiado en los dos sitios,
        diverge; por eso se comprueba que `openModule()` solo delegue.
        """
        self._presente(
            r"const\s+abrirPreWorkOrder\s*=",
            "Falta la función `abrirPreWorkOrder()`",
        )
        cuerpo = self._cuerpo_de_open_module()
        self.assertNotIn(
            "cliente: '', planta: ''", cuerpo,
            "`openModule()` volvió a copiar la inicialización de `workorderData`",
        )
        self.assertIn(
            "abrirPreWorkOrder()", cuerpo,
            "`openModule()` no delega en `abrirPreWorkOrder()`",
        )

    def _cuerpo_de_open_module(self) -> str:
        """El texto de `openModule()`, de su declaración a la siguiente `const`."""
        inicio = self.contenido.index("const openModule = (m) => {")
        fin = self.contenido.index("const openPpcForm", inicio)
        return self.contenido[inicio:fin]

    def test_cotizador_siempre_se_reinicia_como_arreglo(self):
        """
        `cotizador` es una lista de personas, nunca una cadena.

        `addCotizador()` hace push, `removeCotizador()` splice, el guardado hace
        join y la validación mira `.length`. Un reset a `''` no falla en el acto:
        rompe al siguiente clic, ya lejos de donde se causó.
        """
        resets = re.findall(r"cotizador:\s*('' |''|\[\])", self.contenido)
        self.assertTrue(resets, "No se encontró ninguna inicialización de `cotizador`")
        for bloque in re.finditer(r"workorderData\.value\s*=\s*\{[\s\S]{0,900}?\n\s*\};", self.contenido):
            self.assertRegex(
                bloque.group(0),
                r"cotizador:\s*\[\]",
                "Un reset de `workorderData` deja `cotizador` como cadena, no como arreglo",
            )


class TestBotonesDeIA(BaseIndexHtml):
    def test_boton_de_la_agencia_paperclip(self):
        """El botón que dispara el presupuesto con IA sobre la descripción."""
        self._presente(
            r'@click="runPaperclipAgents"',
            "Falta el botón de la Agencia Paperclip en la descripción del trabajo",
        )
        self._presente(
            r'v-if="isPaperclipRunning"',
            "El botón de Paperclip no muestra estado de carga",
        )

    def test_boton_y_modal_del_plano_2d(self):
        """El Plano 2D por IA: botón, función y modal donde se ve el resultado."""
        self._presente(
            r'@click="generateBlueprintFromDescription"',
            "Falta el botón de Plano 2D (IA)",
        )
        self._presente(
            r"const\s+generateBlueprintFromDescription\s*=",
            "Falta la función `generateBlueprintFromDescription()`",
        )
        self._presente(
            r'v-if="showBlueprintModal"',
            "Falta el modal donde se muestra el plano generado",
        )

    def test_los_estados_del_plano_se_exponen_a_la_plantilla(self):
        """
        Vue solo ve lo que `setup()` devuelve.

        Una ref declarada pero no devuelta hace que el `v-if` la lea como
        `undefined`: el modal nunca abre y no hay error en consola.
        """
        for nombre in ("showBlueprintModal", "isGeneratingBlueprint", "blueprintImageUrl",
                       "generateBlueprintFromDescription"):
            self._presente(
                r"return\s*\{[^}]*\b" + nombre + r"\b",
                f"`{nombre}` no se devuelve desde setup()",
            )


class TestEditorPascal(BaseIndexHtml):
    def test_existe_la_vista_y_el_boton_que_lleva_a_ella(self):
        self._presente(
            r"""@click="currentView\s*=\s*'PASCAL_DESIGNER'""",
            "Ningún botón lleva al editor 3D Pascal",
        )
        self._presente(
            r"""v-if="currentView\s*===\s*'PASCAL_DESIGNER'""",
            "Falta la vista PASCAL_DESIGNER",
        )

    def test_el_iframe_existe_y_su_id_es_el_que_busca_el_javascript(self):
        """
        El id del `<iframe>` y el de `getElementById()` tienen que ser el mismo.

        Tras la migración el JS buscaba `pascalIframe`, un id que no existe en
        ningún archivo del repositorio: `getElementById()` devolvía `null` y el
        diseño nunca se inyectaba.
        """
        self._presente(
            r'id="pascal-editor-iframe"',
            "Falta el <iframe> del editor Pascal",
        )
        self._presente(
            r':src="pascalEditorUrl"',
            "El <iframe> no apunta a `pascalEditorUrl`",
        )
        self._ausente(
            r"getElementById\(\s*'pascalIframe'\s*\)",
            "Sigue buscándose el id fantasma `pascalIframe`",
        )
        for encontrado in re.findall(r"getElementById\(\s*'(pascal[^']*)'\s*\)", self.contenido):
            self.assertEqual(
                encontrado, "pascal-editor-iframe",
                f"`getElementById('{encontrado}')` no coincide con el id del <iframe>",
            )

    def test_el_mensaje_de_ida_usa_la_clave_que_el_fork_lee(self):
        """
        Holtmont → Pascal: el fork lee `event.data.projectData`.

        Está fijado en `PARCHE_PASCAL_EDITOR.md`, que es el parche aplicado al
        fork `holtmont-3d-editor`. Mandar `payload` deja el canvas vacío sin
        ningún síntoma visible de este lado.
        """
        envios = re.findall(
            r"postMessage\(\s*\{\s*type:\s*'HOLTMONT_3D_IMPORT'[^}]*\}", self.contenido
        )
        self.assertTrue(envios, "Ya no se manda el diseño al editor Pascal")
        for envio in envios:
            self.assertIn(
                "projectData:", envio,
                "El mensaje HOLTMONT_3D_IMPORT no usa la clave `projectData`",
            )

    def test_el_diseno_se_desenvuelve_antes_de_mandarlo(self):
        """
        Lo que viaja por `postMessage` tiene que ser un objeto plano.

        `saved3DProjectData` es un `ref`: leerlo devuelve un Proxy reactivo de
        Vue, y el algoritmo de clonado estructurado no sabe copiar un Proxy —
        lanza "could not be cloned" y el diseño no llega. Solo pasa al reabrir el
        editor después de haber exportado desde Pascal, que es el ciclo normal,
        así que no salta en una prueba de humo.

        El mismo `JSON.parse` resuelve el otro caso: cuando el diseño viene del
        agente es una cadena, porque `architect_node` hace `json.dumps(scene)`.
        """
        bloque = re.search(
            r"const\s+enviarDisenoAPascal\s*=[\s\S]{0,2500}?\n      \};", self.contenido
        )
        self.assertIsNotNone(bloque, "Falta `enviarDisenoAPascal()`")
        cuerpo = bloque.group(0)
        self.assertIn(
            "JSON.stringify", cuerpo,
            "El diseño se manda sin desenvolver el Proxy reactivo de Vue",
        )
        self.assertIn(
            "JSON.parse", cuerpo,
            "El diseño no se convierte a objeto cuando llega como cadena del agente",
        )

    def test_el_mensaje_de_vuelta_lee_la_clave_que_el_fork_manda(self):
        """
        Pascal → Holtmont: el fork manda `{ type, data }`, no `{ type, payload }`.

        Leer `payload` guardaba `undefined` y marcaba el diseño como 'SAVED': el
        peor caso, porque la interfaz decía que sí y no había nada.
        """
        bloque = re.search(
            r"HOLTMONT_3D_EXPORT'[\s\S]{0,1200}?design3DStatus\.value\s*=\s*'SAVED'",
            self.contenido,
        )
        self.assertIsNotNone(bloque, "Falta el receptor de HOLTMONT_3D_EXPORT")
        self.assertRegex(
            bloque.group(0),
            r"saved3DProjectData\.value\s*=\s*(event\.)?data\.data\b",
            "El receptor no lee `data.data`, que es lo que manda el fork de Pascal",
        )


if __name__ == "__main__":
    unittest.main()
