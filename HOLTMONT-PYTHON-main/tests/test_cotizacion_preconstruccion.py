from playwright.sync_api import sync_playwright
import os
import time

def test_cotizacion_preconstruccion_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # We need the backend to be running to serve the page properly with api_service.js
        # Assuming the backend is running at localhost:8000
        page.goto("http://localhost:8000/")

        # Wait for Vue to mount
        page.wait_for_selector(".login-card", state="visible", timeout=10000)

        # Force login and navigate to the Work Order Form
        page.evaluate("() => { const app = document.querySelector('#app').__vue_app__._instance.proxy; app.isLoggedIn = true; app.currentView = 'WORKORDER_FORM'; }")

        # Wait for the "3. Cotización Preconstrucción" section to be visible
        page.wait_for_selector("text=3. Cotización Preconstrucción")

        # 1. Verify "Junta Interdisciplinaria" is present (instead of Junta Preoperativa)
        content = page.content()
        assert "Junta Interdisciplinaria" in content, "Junta Interdisciplinaria not found in the DOM"

        # 2. Verify we can add a new item
        initial_cards = page.locator("text=3. Cotización Preconstrucción").locator("..").locator("..").locator("..").locator(".card").count()

        # Find the Add button inside the section header
        add_btn = page.locator("text=3. Cotización Preconstrucción").locator("..").locator("button[title='Agregar Fila']")
        add_btn.first.click()

        # The number of cards should have increased
        new_cards = page.locator("text=3. Cotización Preconstrucción").locator("..").locator("..").locator("..").locator(".card").count()
        assert new_cards > initial_cards, f"Failed to add a new row. Expected {initial_cards + 1}, got {new_cards}"

        # 3. Verify total calculation works for the first item
        # We need to make the first item active first
        first_card = page.locator("text=3. Cotización Preconstrucción").locator("..").locator("..").locator("..").locator(".card").first

        # Click the APPLY button (check-square)
        first_card.locator("i.fa-check-square").click()

        # Now fill in duration and price
        duration_input = first_card.locator("input[placeholder='Dias Hrs Trabajo']")
        price_input = first_card.locator("input[placeholder='Costo $']")

        duration_input.fill("5")
        duration_input.press("Tab") # trigger update
        price_input.fill("100")
        price_input.press("Tab") # trigger update

        # Wait for Vue reactivity
        time.sleep(1)

        # Check the total calculation - should be 500
        # The total is rendered in a span inside the last div
        total_span = first_card.locator("span").last
        total_text = total_span.inner_text()
        assert "500" in total_text, f"Total calculation failed. Expected to see 500, got {total_text}"

        browser.close()
        print("All Cotizacion Preconstruccion tests passed!")

if __name__ == "__main__":
    test_cotizacion_preconstruccion_ui()
