from playwright.sync_api import sync_playwright
import os

def run_cuj(page):
    page.goto("http://localhost:8000/index.html")
    page.wait_for_timeout(1000)

    # Hide that weird modal via CSS first so we can click
    try:
        page.evaluate("() => { const modals = document.querySelectorAll('.custom-modal-overlay'); modals.forEach(m => m.style.display = 'none'); }")
    except:
        pass

    # Try logging in
    login_btn = page.locator("button:has-text('INICIAR SESIÓN')")
    if login_btn.is_visible():
        page.locator("input[placeholder='Usuario']").fill("admin")
        page.locator("input[placeholder='Contraseña...']").fill("testpass")
        page.wait_for_timeout(500)
        login_btn.click(force=True)
        page.wait_for_timeout(2000)

    os.makedirs("verification/screenshots", exist_ok=True)
    page.screenshot(path="verification/screenshots/verification_dashboard3.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="verification/videos",
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
