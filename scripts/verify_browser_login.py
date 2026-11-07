"""Real Chrome test of browser login, refresh restoration, and logout.

Uses generated fixture users in the running Docker stack. No real passwords are
changed and no browser storage/cookie files are written to disk.
"""
import os
from pathlib import Path
import secrets
from uuid import uuid4
import httpx
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = {**dotenv_values(ROOT / ".env.docker", interpolate=False), **os.environ}
    public = config.get("COPILOT_PUBLIC_URL", "http://localhost:8501").rstrip("/")
    api = "http://localhost:" + config.get("COPILOT_PORT", "8001")
    employees = []
    with httpx.Client(base_url="http://localhost:" + config.get("MERIDIAN_PORT", "8000"), headers={"X-API-Key": config["DOCKER_ADMIN_API_KEY"]}, timeout=30, trust_env=False) as backend:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                try:
                    for role in ("employee", "admin"):
                        email = f"browser-{uuid4().hex}@example.com"
                        password = secrets.token_urlsafe(24)
                        response = backend.post("/employees", json={"full_name": "Browser Login Fixture", "email": email})
                        response.raise_for_status()
                        employee_id = response.json()["id"]
                        employees.append(employee_id)
                        response = backend.post("/auth/users", json={"employee_id": employee_id, "password": password, "role": role})
                        response.raise_for_status()
                        context = browser.new_context()
                        clone = None
                        handles = []
                        try:
                            page = context.new_page()
                            page.goto(public, wait_until="domcontentloaded")
                            page.get_by_role("link", name="Continue to sign in", exact=True).click(timeout=30000)
                            form = page
                            form.get_by_label("Admin login" if role == "admin" else "Employee login", exact=True).check(timeout=30000)
                            form.get_by_label("Work email", exact=True).fill(email)
                            form.get_by_label("Password", exact=True).fill(password)
                            form.get_by_label("Show password", exact=True).check()
                            assert form.get_by_label("Password", exact=True).get_attribute("type") == "text"
                            form.get_by_label("Show password", exact=True).uncheck()
                            with page.expect_response(lambda response: response.request.method == "POST" and "/auth/browser/login" in response.url, timeout=30000) as submitted:
                                with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                                    form.get_by_role("button", name="Sign in", exact=True).click()
                            assert submitted.value.status == 303, f"Browser sign-in returned HTTP {submitted.value.status}; Origin={submitted.value.request.headers.get('origin')}"
                            page.get_by_role("button", name="Sign out", exact=True).wait_for(timeout=30000)
                            cookie = next(row for row in context.cookies() if row["name"] == "meridian_browser_session")
                            handles.append(cookie["value"])
                            assert cookie["httpOnly"] and cookie["sameSite"] == "Lax"
                            assert cookie["value"] not in page.evaluate("document.cookie")
                            for _ in range(2):
                                page.reload(wait_until="domcontentloaded")
                                page.get_by_role("button", name="Sign out", exact=True).wait_for(timeout=30000)
                                assert page.get_by_text(email, exact=True).is_visible()
                            state = context.storage_state()
                            clone = browser.new_context(storage_state=state)
                            other = clone.new_page()
                            other.goto(public, wait_until="domcontentloaded")
                            other.get_by_role("button", name="Sign out", exact=True).wait_for(timeout=30000)
                            assert other.get_by_text(email, exact=True).is_visible()
                            page.get_by_role("button", name="Sign out", exact=True).click()
                            page.get_by_role("link", name="Continue to sign in", exact=True).wait_for(timeout=30000)
                            other.reload(wait_until="domcontentloaded")
                            other.get_by_role("link", name="Continue to sign in", exact=True).wait_for(timeout=30000)
                            assert other.get_by_role("button", name="Sign out", exact=True).count() == 0
                            print(f"PASS: {role} Chrome login, show-password toggle, repeated refresh, fresh browser context, HttpOnly cookie, and cross-context logout", flush=True)
                        finally:
                            with httpx.Client(trust_env=False, timeout=45) as client:
                                for handle in handles:
                                    client.post(api + "/auth/browser/revoke", json={"handle": handle}, headers={"X-UI-Auth-Key": config["DOCKER_BROWSER_UI_AUTH_KEY"]})
                            context.close()
                            if clone:
                                clone.close()
                finally:
                    browser.close()
        finally:
            for employee_id in employees:
                response = backend.delete(f"/employees/{employee_id}")
                assert response.status_code == 204, "Browser fixture cleanup failed"
            print("Temporary browser test accounts cleaned up.", flush=True)


if __name__ == "__main__":
    main()
