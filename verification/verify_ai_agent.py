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

        # Wait for redirection or module load
        # Since WORKORDER_USER is auto-redirected to WORKORDER_FORM, we wait for a specific element
        # We look for the AI Agent Bar text
        try:
            page.wait_for_selector("h6:has-text('AGENTE IA DE PRE-INGENIERÍA')", timeout=10000)
            print("AI Agent Bar found!")
        except:
            print("AI Agent Bar not found immediately, checking if we need to click menu...")
            # If not auto redirected, we might need to click module
            # But memory says it is auto redirected.

        # Scroll to the element to ensure it's in view
        element = page.locator("h6:has-text('AGENTE IA DE PRE-INGENIERÍA')")
        if element.is_visible():
            element.scroll_into_view_if_needed()

        time.sleep(2) # Allow animations to settle

        page.screenshot(path="verification/ai_agent_verification.png")
        browser.close()

if __name__ == "__main__":
    run()
