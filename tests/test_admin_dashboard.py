import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from pathlib import Path
from app.api.main import app
from test_meridian_api_ui import tokens, reply

SUMMARY = {"employees": {"total": 4, "active": 3, "inactive": 1}, "devices": {"total": 5, "assigned": 3, "unassigned": 2}, "tickets": {"total": 10, "open": 4, "in_progress": 2, "resolved": 1, "closed": 3, "high_priority_active": 2}}


class AdminProxyTests(unittest.TestCase):
    def test_employee_cannot_use_admin_proxy(self):
        with TestClient(app) as client, patch("app.api.admin.backend_request", return_value={"id": 1, "role": "employee"}) as backend:
            self.assertEqual(client.get("/admin/summary").status_code, 401)
            for path in ("/admin/summary", "/admin/tickets", "/admin/employees", "/admin/devices"):
                response = client.get(path, headers={"Authorization": "Bearer employee"})
                self.assertEqual(response.status_code, 403)
            self.assertTrue(all(call.args[0] == "/auth/me" for call in backend.call_args_list))

    def test_verified_admin_can_fetch_summary_and_update_ticket(self):
        with TestClient(app) as client, patch("app.api.admin.backend_request", side_effect=[{"role": "admin"}, SUMMARY]) as backend:
            response = client.get("/admin/summary", headers={"Authorization": "Bearer admin"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json(), SUMMARY)
            self.assertEqual(backend.call_args.args[0], "/admin/summary")
        with TestClient(app) as client, patch("app.api.admin.backend_request", side_effect=[{"role": "admin"}, {"id": 29, "status": "open"}]) as backend:
            response = client.patch("/admin/tickets/29", json={"status": "open", "override": True, "reason": "Issue recurred"}, headers={"Authorization": "Bearer admin"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(backend.call_args.args[0], "/tickets/29/admin")
            self.assertNotIn("override", backend.call_args.kwargs["body"])

    def test_invalid_proxy_resource_and_unexpected_fields_do_not_forward(self):
        with TestClient(app) as client, patch("app.api.admin.backend_request", return_value={"role": "admin"}) as backend:
            self.assertEqual(client.post("/admin/employees", json={"full_name": "A", "password": "must-not-forward"}, headers={"Authorization": "Bearer admin"}).status_code, 422)
            self.assertEqual(backend.call_count, 1)
            self.assertEqual(client.get("/admin/secrets", headers={"Authorization": "Bearer admin"}).status_code, 422)


class AdminUiTests(unittest.TestCase):
    def admin_page(self, section, get):
        page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"), default_timeout=10)
        session = tokens()
        session["user"]["role"] = "admin"
        page.session_state["auth_session"] = session
        page.session_state["workspace"] = "Admin dashboard"
        page.session_state["admin_section"] = section
        with patch("requests.get", side_effect=get):
            page.run()
        self.assertEqual(len(page.exception), 0)
        return page

    def test_ticket_editor_submits_normal_status_change(self):
        row = {"id": 29, "title": "Wi-Fi issue", "description": "Details", "employee_id": 32, "device_id": 19, "status": "open", "priority": "high", "updated_at": "2026-11-06T10:00:00Z"}
        def get(url, **kwargs):
            if url.endswith("/history"):
                return reply([])
            return reply({"items": [dict(row)], "total": 1})
        page = self.admin_page("Tickets", get)
        with patch("requests.get", side_effect=get):
            next(item for item in page.selectbox if item.label == "Open a ticket").set_value(29).run()
        next(item for item in page.selectbox if item.label == "Ticket status").set_value("in_progress")
        page.text_area[0].input("Investigation started")
        def write(method, url, **kwargs):
            self.assertEqual(method, "PATCH")
            self.assertTrue(url.endswith("/admin/tickets/29"))
            self.assertEqual(kwargs["json"], {"status": "in_progress", "reason": "Investigation started", "override": False})
            row["status"] = "in_progress"
            return reply(dict(row))
        with patch("requests.get", side_effect=get), patch("requests.request", side_effect=write) as request:
            next(item for item in page.button if item.label == "Save ticket").click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(row["status"], "in_progress")

    def test_employee_create_form(self):
        def get(url, **kwargs):
            return reply({"items": [], "total": 0})
        page = self.admin_page("Employees", get)
        next(item for item in page.text_input if item.label == "Full name").input("New Employee")
        next(item for item in page.text_input if item.label == "Work email").input("new.employee@example.com")
        with patch("requests.get", side_effect=get), patch("requests.request", return_value=reply({"id": 200}, 201)) as request:
            next(item for item in page.button if item.label == "Create employee").click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertTrue(request.call_args.args[1].endswith("/admin/employees"))
        self.assertEqual(request.call_args.kwargs["json"]["email"], "new.employee@example.com")

    def test_device_can_be_unassigned(self):
        row = {"id": 19, "asset_tag": "LAP-19", "device_type": "laptop", "manufacturer": "HP", "model": "xyz", "serial_number": "HP1", "assigned_employee_id": 32}
        def get(url, **kwargs):
            return reply({"items": [dict(row)], "total": 1})
        page = self.admin_page("Devices", get)
        with patch("requests.get", side_effect=get):
            next(item for item in page.selectbox if item.label == "Edit device").set_value(19).run()
        page.number_input[-1].set_value(0)
        def write(method, url, **kwargs):
            self.assertEqual(kwargs["json"], {"assigned_employee_id": None})
            row["assigned_employee_id"] = None
            return reply(dict(row))
        with patch("requests.get", side_effect=get), patch("requests.request", side_effect=write) as request:
            next(item for item in page.button if item.label == "Save device").click().run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(request.call_count, 1)

    def test_admin_workspace_shows_totals_and_employee_workspace_hides_it(self):
        page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"))
        session = tokens()
        session["user"]["role"] = "admin"
        page.session_state["auth_session"] = session
        with patch("requests.get", return_value=reply({"items": [], "next_offset": None})):
            page.run()
        self.assertEqual(len(page.exception), 0)
        with patch("requests.get", return_value=reply(SUMMARY)) as get:
            page.sidebar.radio[0].set_value("Admin dashboard").run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(len(page.chat_input), 0)
        self.assertTrue(get.call_args.args[0].endswith("/admin/summary"))
        self.assertIn("Employees", [metric.label for metric in page.metric])
        self.assertIn("Active tickets", [metric.label for metric in page.metric])
        employee = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/streamlit_app.py"))
        employee.session_state["auth_session"] = tokens()
        with patch("requests.get", return_value=reply({"items": [], "next_offset": None})):
            employee.run()
        self.assertEqual(len(employee.sidebar.radio), 0)
