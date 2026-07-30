import re
import os
import unittest

class TestPreDisenos(unittest.TestCase):
    def setUp(self):
        self.filepath = 'index.html'
        if not os.path.exists(self.filepath):
            self.fail(f"{self.filepath} no encontrado.")

        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.content = f.read()

    def test_header_text_and_style(self):
        """Verifica que el título de la sección y los estilos sean exactos"""
        expected_title = r'2\. Requerimiento Pre-Diseños , Pre-Analisis de Riesgos y Precios Unitarios\( Paso 2 \)'
        self.assertRegex(self.content, expected_title, "El título de la sección de Pre-Diseños no coincide")

        # Verifica estilo oscuro para el contenedor del título
        dark_bg = r'background:\s*#000000;'
        self.assertRegex(self.content, dark_bg, "Falta el fondo negro para el encabezado de Pre-Diseños")

    def test_columns_and_v_models(self):
        """Verifica la existencia de los nuevos campos en la fila del template"""
        # Chequea v-models requeridos y placeholders
        expected_models = [
            r'v-model="item\.fechaInicio"',
            r'v-model="item\.fechaEntrega"',
            r'v-model="item\.duration"',
            r'v-model="item\.fechaInicio2"',
            r'v-model="item\.fileUrl"',
            r'v-model="item\.total"'
        ]

        for model in expected_models:
            self.assertRegex(self.content, model, f"No se encontró el v-model {model}")

        expected_placeholders = [
            r'placeholder="Fecha inicio"',
            r'placeholder="Fecha Entrega"',
            r'placeholder="Hrs o Días de Trabajo"',
            r'placeholder="Archivo Adjunto"',
            r'placeholder="Costo \$"'
        ]

        for placeholder in expected_placeholders:
            self.assertRegex(self.content, placeholder, f"No se encontró el placeholder {placeholder}")

    def test_default_data_structure(self):
        """
        El paso 2 abre en blanco: `defaultReqCotizacion` tiene que estar vacío.

        Esto es una **divergencia deliberada** con REAL-HOLTMONT, que precarga 8
        actividades estándar de pre-diseño en esta misma sección
        (`REAL-HOLTMONT/index.html:6451`). Decisión del dueño, reconfirmada el
        2026-07-30 cuando se planteó el conflicto entre este test y la paridad:
        gana el formulario en blanco, junto con el rediseño del paso 2 que vive
        aquí (las filas se agregan con el botón `+`).

        Se deja escrito para que la próxima revisión de paridad no lo lea como
        una regresión y lo "arregle". Ver COMPARATIVA_REAL_VS_PYTHON.md §0.bis.
        """
        # Busca el bloque de defaultReqCotizacion y verifica que esté vacío
        default_data_block_match = re.search(r'const defaultReqCotizacion = \[(.*?)\];', self.content, re.DOTALL)
        self.assertIsNotNone(default_data_block_match, "No se encontró el bloque defaultReqCotizacion")

        default_data = default_data_block_match.group(1).strip()
        self.assertEqual(
            default_data, "",
            "El bloque defaultReqCotizacion no está vacío. Si es un intento de "
            "igualar a REAL-HOLTMONT, es a propósito que no coincida: ver "
            "COMPARATIVA_REAL_VS_PYTHON.md §0.bis.")

    def test_add_remove_buttons(self):
        """Verifica que el botón de añadir y remover fila están presentes con la sintaxis correcta"""
        add_btn = r"@click=\"addProjectItem\('reqCotizacion'\)\""
        remove_btn = r"@click=\"removeProjectItem\('reqCotizacion', idx\)\""

        self.assertRegex(self.content, add_btn, "No se encontró el botón para agregar item en reqCotizacion")
        self.assertRegex(self.content, remove_btn, "No se encontró el botón para remover item en reqCotizacion")

if __name__ == '__main__':
    unittest.main()
