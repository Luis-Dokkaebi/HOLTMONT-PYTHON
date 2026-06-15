from playwright.sync_api import sync_playwright
import os

def run_cuj(page):
    page.on("console", lambda msg: print(f"Browser Console: {msg.type}: {msg.text}"))
    page.on("pageerror", lambda err: print(f"Browser Error: {err}"))

    page.goto("http://localhost:8000/index.html")
    page.wait_for_timeout(2000)

    login_btn = page.locator("button:has-text('INICIAR SESIÓN')")
    if login_btn.is_visible():
        page.locator("input[placeholder='Usuario']").fill("admin")
        page.locator("input[placeholder='Contraseña...']").fill("testpass")
        page.wait_for_timeout(500)
        login_btn.click(force=True)
        page.wait_for_timeout(2000)
        print("Login done")

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
