import unittest
from unittest.mock import AsyncMock, patch
from app.agent.fallback import insufficient_context_response
from app.agent.meridian import meridian_node


class EvaluationBehaviorTests(unittest.TestCase):
    def test_unknown_policy_asks_for_context_without_inventing_sources(self):
        result = insufficient_context_response({"reason": "No policy document", "missing_information": "Expense rules"})
        self.assertEqual(result["status"], "insufficient_context")
        self.assertEqual(result["sources"], [])
        self.assertIn("Could you share", result["answer"])
        self.assertTrue(result["answer"].endswith("?"))

    def test_mcp_connection_failure_hides_details_and_cannot_reuse_success(self):
        with patch.dict("os.environ", {"MERIDIAN_MCP_ENABLED": "true"}), patch("app.agent.meridian._run", new=AsyncMock(side_effect=ConnectionError("private host and password"))):
            result = meridian_node({"question": "Close my ticket", "answer": "Old success"})
        self.assertEqual(result["status"], "meridian_unavailable")
        self.assertIn("No result is confirmed", result["answer"])
        self.assertNotIn("private", result["answer"])
        self.assertEqual(result["meridian_tools"], [])
