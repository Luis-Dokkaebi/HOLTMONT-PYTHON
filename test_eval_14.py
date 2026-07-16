from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:8000/index.html")

    page.wait_for_selector('input[placeholder="Usuario"]')

    page.fill('input[placeholder="Usuario"]', 'ANTONIA_VENTAS')
    page.fill('input[placeholder="Contraseña..."]', 'tonita2025')

    # We will log google.script.run definition
    res = page.evaluate("""() => {
        return window.google && window.google.script && window.google.script.run ? true : false;
    }""")
    print("Has google.script.run initially:", res)

    page.click('button:has-text("INICIAR SESIÓN")')

    page.wait_for_timeout(3000)

    # Check what state loggingIn is
    res = page.evaluate("""() => {
        return document.querySelector('#app').outerHTML.includes('Conectando...');
    }""")
    print("Has Conectando:", res)

    browser.close()
