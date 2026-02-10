from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:3000")

        # Login
        page.fill("input[placeholder='Usuario']", "PREWORK_ORDER")
        page.fill("input[placeholder='Contraseña...']", "workorder2026")
        page.click("button:has-text('INICIAR SESIÓN')")

        # Wait for button
        btn = page.locator("button:has-text('INICIAR DICTADO')")
        btn.wait_for(state="visible", timeout=10000)

        # Click button
        print("Clicking AI Button...")
        btn.click()

        time.sleep(1)

        # Check for Modal
        try:
            modal = page.locator(".modal-title:has-text('Asistente de Cotización IA')")
            modal.wait_for(state="visible", timeout=5000)
            print("Modal OPENED successfully!")
            page.screenshot(path="verification/modal_success.png")
        except Exception as e:
            print("Modal DID NOT OPEN:", e)
            page.screenshot(path="verification/modal_failure.png")

        browser.close()

if __name__ == "__main__":
    run()
