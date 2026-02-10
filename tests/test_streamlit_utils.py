import sys
import os
import io
import unittest
from unittest.mock import MagicMock, patch

# Add the repo root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from streamlit_cotizador.utils import ExtractionSchema, ItemMaterial, ItemPersonal, ItemActividad, llenar_pdf

class TestStreamlitUtils(unittest.TestCase):

    def test_models(self):
        """Test Pydantic models instantiation."""
        mat = ItemMaterial(cantidad="5", unidad="pza", descripcion="Test Material", costo="10.0", total="50.0")
        self.assertEqual(mat.cantidad, "5")

        pers = ItemPersonal(cantidad_personas="2", categoria="Obrero", salario_semanal="1000", semanas_cotizadas="2", salario_neto="4000")
        self.assertEqual(pers.categoria, "Obrero")

        schema = ExtractionSchema(
            folio="123",
            lista_materiales=[mat],
            lista_personal=[pers]
        )
        self.assertEqual(schema.folio, "123")
        self.assertEqual(len(schema.lista_materiales), 1)

    @patch('streamlit_cotizador.utils.PdfWriter')
    @patch('streamlit_cotizador.utils.PdfReader')
    def test_llenar_pdf_mock(self, MockReader, MockWriter):
        """Test PDF filling logic using mocks."""

        # Setup mocks
        mock_reader = MockReader.return_value
        mock_writer = MockWriter.return_value

        # Simulate pages in reader and writer
        mock_page = MagicMock()
        mock_reader.pages = [mock_page]
        mock_writer.pages = [mock_page]
        mock_writer.root_object = {} # For AcroForm check

        # Data
        datos = ExtractionSchema(
            folio="TEST-FOLIO-999",
            lista_materiales=[],
            lista_personal=[],
            lista_herramientas=[],
            lista_equipo_ligero=[],
            lista_equipo_proteccion=[],
            programa_del_proyecto=[]
        )

        template_buffer = io.BytesIO(b"fake pdf content")
        output_buffer = io.BytesIO()

        # Run function
        result = llenar_pdf(datos, template_buffer, output_buffer)

        self.assertTrue(result)

        # Verify update_page_form_field_values was called
        mock_writer.update_page_form_field_values.assert_called()

        # Get the arguments of the call
        args, _ = mock_writer.update_page_form_field_values.call_args
        page_arg, fields_arg = args

        self.assertEqual(page_arg, mock_page)
        self.assertEqual(fields_arg.get("Text-zMv1pANbT6"), "TEST-FOLIO-999")

if __name__ == '__main__':
    unittest.main()
