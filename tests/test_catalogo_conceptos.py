import pytest
from playwright.sync_api import sync_playwright, expect
import os
import subprocess
import time

PORT = 8000
BASE_URL = f"http://localhost:{PORT}"

@pytest.fixture(scope="module", autouse=True)
def start_server():
    server = subprocess.Popen(
        ["python", "api/main.py"],
        env=dict(os.environ, PYTHONPATH=".", PORT=str(PORT))
    )
    time.sleep(2)  # Wait for server to start
    yield
    server.terminate()
    server.wait()

def test_catalogo_conceptos_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)

        # Bypass login since we're testing the UI locally
        page.wait_for_selector(".login-card", state="visible")
        page.evaluate("""() => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            app.isLoggedIn = true;
            app.currentView = 'WORKORDER_FORM';
        }""")

        # Wait for the "4. Catálogo de Conceptos ( Paso 4 )" section to be visible
        header_text = page.locator("text='4. Catálogo de Conceptos ( Paso 4 )'")
        header_text.scroll_into_view_if_needed()
        expect(header_text).to_be_visible()

        # Find the Add button for 'cotTrabajo' and click it
        add_btn = header_text.locator("xpath=..").locator("button")
        add_btn.click()

        # Verify a new row is added and the 'Pop Up' text is visible
        pop_up_label = page.locator("text='Pop Up'").first
        expect(pop_up_label).to_be_visible()

        # Verify duration dropdown options are updated
        # The modal button acts as a great anchor since it's inside the same row
        mo_btn = page.locator("button:has-text('MO')").last
        row = mo_btn.locator("xpath=../../..")
        dropdown = row.locator("select").first

        expect(dropdown).to_be_visible()
        expect(dropdown.locator("option[value='dias']")).to_have_text("días")
        expect(dropdown.locator("option[value='horas']")).to_have_text("hrs")

        # Open the modal by clicking 'MO' resource button
        mo_btn.click()

        # Wait for modal to appear
        modal = page.locator(".custom-modal").first
        expect(modal).to_be_visible()

        # Verify "Detalle de Actividad" title
        modal_title = modal.locator("span.fw-bold:has-text('Detalle de Actividad')")
        expect(modal_title).to_be_visible()

        # Edit description
        desc_input = modal.locator("input[placeholder='Ej: Construccion de Pared de Block 10 x 3 m altura...']")
        desc_input.fill("Actividad de Prueba")

        # Edit dictation textarea
        dictado_textarea = modal.locator("textarea[placeholder='Dicta los detalles aquí...']")
        dictado_textarea.fill("Dictado de prueba para validar que se guarda en el estado.")

        # Close the modal
        close_btn = modal.locator("button.btn-close")
        close_btn.click()

        # Verify state was updated by checking if concept string contains the dictation
        # We can trigger the serialization by inspecting the Vue instance
        conceptoStr = page.evaluate("""() => {
            const app = document.querySelector('#app').__vue_app__._instance.proxy;
            let str = "";
            app.projectProgram.cotTrabajo.forEach((t, i) => {
                if (t.dictado) str += `[DICTADO CONCEPTO ${i+1}: ${t.description}] ${t.dictado}`;
            });
            return str;
        }""")

        assert "Actividad de Prueba" in conceptoStr
        assert "Dictado de prueba para validar que se guarda en el estado." in conceptoStr

        browser.close()
