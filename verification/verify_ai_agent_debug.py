from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("http://localhost:3000")

        print("Page title:", page.title())

        # Login
        try:
            page.fill("input[placeholder='Usuario']", "PREWORK_ORDER")
            page.fill("input[placeholder='Contraseña...']", "workorder2026")
            print("Filled credentials")
            page.click("button:has-text('INICIAR SESIÓN')")
            print("Clicked login")
        except Exception as e:
            print("Login interaction failed:", e)
            page.screenshot(path="verification/debug_login_error.png")
            return

        time.sleep(5)

        # Check if login overlay is still there
        if page.locator(".login-overlay").is_visible():
            print("Login overlay still visible. Login might have failed.")
            # Check for error message
            if page.locator("text=Usuario o contraseña incorrectos").is_visible():
                print("Incorrect credentials error.")
            page.screenshot(path="verification/debug_login_failed.png")
        else:
            print("Login overlay gone. Logged in?")

        # Check if redirected to PRE WORK ORDER
        # Look for "PRE WORK ORDER" text in the header
        try:
            # The header has "PRE WORK ORDER" in small tag
            if page.locator("small:has-text('PRE WORK ORDER')").is_visible():
                print("Redirected to PRE WORK ORDER successfully.")
            else:
                print("Not on PRE WORK ORDER view. Current view might be dashboard.")
                page.screenshot(path="verification/debug_not_on_view.png")
        except:
            pass

        # Look for AI Agent Bar
        try:
            bar = page.locator("h6:has-text('AGENTE IA DE PRE-INGENIERÍA')")
            bar.wait_for(state="visible", timeout=5000)
            print("AI Agent Bar FOUND!")
            bar.scroll_into_view_if_needed()
            page.screenshot(path="verification/ai_agent_success.png")
        except Exception as e:
            print("AI Agent Bar NOT found:", e)
            page.screenshot(path="verification/debug_final_state.png")

        browser.close()

if __name__ == "__main__":
    run()
