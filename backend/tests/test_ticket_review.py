import unittest
from unittest.mock import patch
from sqlalchemy.orm import Session
import test_auth
from app.models import Ticket
from app.schemas.ticket import TicketUpdate
from app.security import Operator
from app.services import ticket as service


class TicketReviewTests(unittest.TestCase):
    setUp = test_auth.AuthenticationTests.setUp
    tearDown = test_auth.AuthenticationTests.tearDown
    account = test_auth.AuthenticationTests.account
    login = test_auth.AuthenticationTests.login
    headers = test_auth.AuthenticationTests.headers
    ticket = test_auth.AuthenticationTests.ticket

    def create(self):
        tokens = self.login()
        ticket_id = self.ticket(self.owner, tokens)
        return ticket_id, self.headers(tokens)

    def test_owner_edits_title_and_description_before_review(self):
        ticket_id, owner = self.create()
        initial = self.client.get(f"/tickets/{ticket_id}", headers=owner).json()
        self.assertTrue(initial["employee_can_edit"])
        self.assertIsNone(initial["reviewed_at"])
        changed = self.client.patch(f"/tickets/{ticket_id}", json={"title": "Updated title", "description": "Updated issue details"}, headers=owner)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["description"], "Updated issue details")
        self.assertTrue(changed.json()["employee_can_edit"])
        events = self.client.get(f"/tickets/{ticket_id}/history", headers=owner).json()
        self.assertEqual(len(events), 1)

    def test_queue_does_not_review_but_admin_open_locks_permanently(self):
        ticket_id, owner = self.create()
        admin = self.headers(self.login(self.admin_user))
        rows = self.client.get("/admin/tickets", headers=admin).json()["items"]
        self.assertIsNone(next(row for row in rows if row["id"] == ticket_id)["reviewed_at"])
        self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"description": "Still editable after queue listing"}, headers=owner).status_code, 200)
        opened = self.client.get(f"/tickets/{ticket_id}", headers=admin)
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.headers["cache-control"], "no-store")
        first = opened.json()
        self.assertIsNotNone(first["reviewed_at"])
        self.assertEqual(first["reviewed_by_employee_id"], self.admin_user["employee_id"])
        self.assertFalse(first["employee_can_edit"])
        again = self.client.get(f"/tickets/{ticket_id}", headers=self.admin).json()
        self.assertEqual(again["reviewed_at"], first["reviewed_at"])
        self.assertEqual(again["reviewed_by_employee_id"], first["reviewed_by_employee_id"])
        blocked = self.client.patch(f"/tickets/{ticket_id}", json={"description": "Should not be saved"}, headers=owner)
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("Create a new ticket", blocked.json()["detail"])
        self.assertEqual(self.client.get(f"/tickets/{ticket_id}", headers=owner).json()["description"], "Still editable after queue listing")
        self.assertEqual(self.client.post(f"/tickets/{ticket_id}/close", headers=owner).status_code, 200)

    def test_admin_mutation_reviews_even_without_prior_open(self):
        ticket_id, owner = self.create()
        changed = self.client.patch(f"/tickets/{ticket_id}", json={"priority": "high"}, headers=self.headers(self.login(self.admin_user)))
        self.assertEqual(changed.status_code, 200)
        self.assertIsNotNone(changed.json()["reviewed_at"])
        self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"title": "Blocked"}, headers=owner).status_code, 409)
        self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"description": "Admin correction"}, headers=self.admin).status_code, 200)

    def test_other_employee_privileged_fields_and_review_reset_are_rejected(self):
        ticket_id, owner = self.create()
        other = self.headers(self.login(self.other))
        self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"description": "Other employee"}, headers=other).status_code, 404)
        for changes in ({"priority": "urgent"}, {"status": "resolved"}, {"employee_id": self.other["employee_id"]}, {"device_id": None}):
            self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json=changes, headers=owner).status_code, 403)
        for changes in ({"reviewed_at": None}, {"reviewed_by_employee_id": None}):
            self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json=changes, headers=owner).status_code, 422)

    def test_owner_closed_unreviewed_ticket_is_not_editable(self):
        ticket_id, owner = self.create()
        closed = self.client.post(f"/tickets/{ticket_id}/close", headers=owner).json()
        self.assertFalse(closed["employee_can_edit"])
        self.assertIsNone(closed["reviewed_at"])
        self.assertEqual(self.client.patch(f"/tickets/{ticket_id}", json={"title": "Closed edit"}, headers=owner).status_code, 409)

    def test_stale_employee_instance_cannot_bypass_new_review(self):
        ticket_id, _ = self.create()
        with Session(bind=self.connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as session:
            stale = session.get(Ticket, ticket_id)
            self.assertIsNone(stale.reviewed_at)
            self.assertEqual(self.client.get(f"/tickets/{ticket_id}", headers=self.admin).status_code, 200)
            with self.assertRaises(service.WorkflowConflictError):
                service.update_ticket(session, stale, TicketUpdate(description="Stale edit"), Operator(role="employee", employee_id=self.owner["employee_id"]))

    def test_admin_created_ticket_is_already_reviewed(self):
        created = self.client.post("/tickets", json={"title": "Admin-created", "description": "Already seen", "employee_id": self.owner["employee_id"]}, headers=self.admin)
        self.assertEqual(created.status_code, 201)
        self.assertIsNotNone(created.json()["reviewed_at"])
