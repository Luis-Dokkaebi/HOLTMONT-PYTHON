from playwright.sync_api import sync_playwright
import os

def run_cuj(page):
    page.goto("http://localhost:8000/index.html")
    page.wait_for_timeout(1000)

    # Try logging in
    try:
        page.evaluate("() => { const app = document.querySelector('#app').__vue_app__._instance.proxy; app.isLoggedIn = true; app.currentView = 'WORKORDER_FORM'; app.currentUser = { username: 'COTIZADOR', role: 'COTIZADOR' }; app.showLogic = {}; }")
        page.wait_for_timeout(1000)
    except Exception as e:
        print("Could not eval", e)

    os.makedirs("verification/screenshots", exist_ok=True)
    page.screenshot(path="verification/screenshots/verification3.png")
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
