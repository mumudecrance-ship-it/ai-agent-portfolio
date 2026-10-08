from __future__ import annotations

import unittest

from live_agent import LiveAgentError
import server


class ServerStateTests(unittest.TestCase):
    def setUp(self) -> None:
        with server.LOCK:
            server.STATE.update({
                "fixed": None,
                "live": None,
                "confirmation": None,
                "error": None,
                "generations": {"fixed": 0, "live": 0},
            })

    def test_replan_result_cannot_be_confirmed(self) -> None:
        candidate = {"decision": "REPLAN_REQUIRED", "candidate_digest": "fixed-a"}
        with self.assertRaises(LiveAgentError) as caught:
            server._confirmation_candidate("fixed", candidate)
        self.assertEqual(caught.exception.code, "RESULT_NOT_CONFIRMABLE")

    def test_pending_fixed_result_returns_bound_digest(self) -> None:
        candidate = {"decision": "PENDING_HUMAN_CONFIRMATION", "candidate_digest": "fixed-b"}
        result, digest = server._confirmation_candidate("fixed", candidate)
        self.assertIs(result, candidate)
        self.assertEqual(digest, "fixed-b")

    def test_pending_live_result_uses_nested_decision(self) -> None:
        candidate = {"result": {"decision": "PENDING_HUMAN_CONFIRMATION"}, "candidate_digest": "live-b"}
        result, digest = server._confirmation_candidate("live", candidate)
        self.assertEqual(result["decision"], "PENDING_HUMAN_CONFIRMATION")
        self.assertEqual(digest, "live-b")

    def test_confirmable_result_without_version_is_rejected(self) -> None:
        with self.assertRaises(LiveAgentError) as caught:
            server._confirmation_candidate("fixed", {"decision": "PENDING_HUMAN_CONFIRMATION"})
        self.assertEqual(caught.exception.code, "VERSION_REQUIRED")

    def test_newer_run_cancels_older_commit(self) -> None:
        first = server._start_operation("fixed")
        second = server._start_operation("fixed")
        self.assertFalse(server._finish_operation("fixed", first, {"id": "old"}))
        self.assertTrue(server._finish_operation("fixed", second, {"id": "new"}))
        self.assertEqual(server.STATE["fixed"], {"id": "new"})

    def test_reset_invalidates_inflight_commit(self) -> None:
        generation = server._start_operation("live")
        server._reset_scopes("live")
        self.assertFalse(server._finish_operation("live", generation, {"result": {}}))
        self.assertIsNone(server.STATE["live"])


if __name__ == "__main__":
    unittest.main()
