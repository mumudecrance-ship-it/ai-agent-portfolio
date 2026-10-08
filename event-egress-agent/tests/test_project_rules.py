from __future__ import annotations

import json
from pathlib import Path
import unittest

from live_agent import LiveAgentError
import project_rules


ROOT = Path(__file__).resolve().parents[1]
PROJECT = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
VENUE = PROJECT["live"]["default_venue"]


def ready_result() -> dict:
    return {
        "interpretation_status": "READY",
        "summary": "北门雨天降容，东门接驳暂停。",
        "changes": [
            {"kind": "RAIN", "target": "E4", "start_step": 3, "end_step": 12, "effect": "CAPACITY_MULTIPLIER", "value": 0.5, "description": "北门雨天降容"},
            {"kind": "TRANSIT_CLOSED", "target": "E1", "start_step": 5, "end_step": 7, "effect": "CAPACITY_MULTIPLIER", "value": 0, "description": "东门接驳暂停"},
        ],
        "local_intents": [{"group_id": "G1", "target_exit": "E2", "goal": "局部改向", "reason": "东门暂停"}],
        "handoff_boundary": {"current_status": "DRAFT", "next_owner": "HUMAN", "external_boundary": "NO_EXECUTION"},
    }


class ProjectRuleTests(unittest.TestCase):
    def test_preflight_rejects_bad_venue_before_api(self) -> None:
        with self.assertRaises(LiveAgentError) as caught:
            project_rules.preflight_live({"venue_config": {}, "event_description": "这是一段足够长的事件描述"})
        self.assertEqual(caught.exception.code, "VENUE_PROFILE_REJECTED")

    def test_preflight_accepts_free_natural_language(self) -> None:
        project_rules.preflight_live({"venue_config": VENUE, "event_description": "第五轮左右东门暂停，其他出口先保持原样。"})

    def test_ready_draft_runs_abc_and_returns_trace(self) -> None:
        result = project_rules.validate_live(ready_result(), {"venue_config": VENUE}, PROJECT)
        self.assertEqual(result["source"], "LIVE_API_PLUS_DETERMINISTIC_ENGINE")
        self.assertEqual(len(result["candidate_results"]), 3)
        self.assertEqual(len(result["recommended_trace"]), 12)
        self.assertFalse(result["rule_checks"]["real_world_execution_allowed"])
        self.assertEqual(result["decision"], "PENDING_HUMAN_CONFIRMATION")

    def test_clarification_status_stops_before_simulation(self) -> None:
        draft = ready_result()
        draft["interpretation_status"] = "NEEDS_CLARIFICATION"
        with self.assertRaises(LiveAgentError) as caught:
            project_rules.validate_live(draft, {"venue_config": VENUE}, PROJECT)
        self.assertEqual(caught.exception.code, "API_NEEDS_CLARIFICATION")

    def test_unknown_exit_is_rejected(self) -> None:
        draft = ready_result()
        draft["changes"][0]["target"] = "E9"
        with self.assertRaises(LiveAgentError) as caught:
            project_rules.validate_live(draft, {"venue_config": VENUE}, PROJECT)
        self.assertEqual(caught.exception.code, "API_SCOPE_REJECTED")

    def test_unknown_local_intent_group_is_rejected(self) -> None:
        draft = ready_result()
        draft["local_intents"][0]["group_id"] = "G9"
        with self.assertRaises(LiveAgentError) as caught:
            project_rules.validate_live(draft, {"venue_config": VENUE}, PROJECT)
        self.assertEqual(caught.exception.code, "API_SCOPE_REJECTED")

    def test_explicit_no_incident_can_run_with_empty_changes(self) -> None:
        draft = ready_result()
        draft["summary"] = "本轮明确无突发事件。"
        draft["changes"] = []
        draft["local_intents"] = []
        result = project_rules.validate_live(draft, {"venue_config": VENUE}, PROJECT)
        self.assertEqual(len(result["candidate_results"]), 3)
        self.assertEqual(len(result["recommended_trace"]), 12)

    def test_fixed_target_keeps_mock_and_deterministic_trace(self) -> None:
        fixed = next(item for item in PROJECT["fixed_case"]["outcomes"] if item["id"] == "target")
        result = project_rules.run_fixed(fixed, PROJECT)
        self.assertEqual(result["source"], "FIXED_REGRESSION_DETERMINISTIC")
        self.assertEqual(len(result["computed"]["trace"]), 12)
        self.assertEqual(len(result["agent_trace"]), 5)

    def test_every_fixed_contract_metric_matches_deterministic_replay(self) -> None:
        for outcome in PROJECT["fixed_case"]["outcomes"]:
            with self.subTest(outcome=outcome["id"]):
                result = project_rules.run_fixed(outcome, PROJECT)
                self.assertEqual(outcome["metrics"], result["computed"]["metrics"])
                self.assertEqual(result["metrics"], result["computed"]["metrics"])


if __name__ == "__main__":
    unittest.main()
