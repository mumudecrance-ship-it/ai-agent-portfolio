from __future__ import annotations

from copy import deepcopy
import unittest

import map_engine


def venue(exit_count: int = 4) -> dict:
    directions = ["north", "east", "south", "west", "northeast", "southeast", "southwest", "northwest"]
    return {
        "name": "测试活动中心",
        "audience_count": 4800,
        "zone_notes": "东西分区，仅用于本地预演。",
        "exits": [
            {"id": f"E{index + 1}", "name": f"出口 {index + 1}", "direction": directions[index], "capacity_per_tick": 420 + index * 40}
            for index in range(exit_count)
        ],
    }


class VenueCaseTests(unittest.TestCase):
    def test_builds_editable_two_exit_case(self) -> None:
        case = map_engine.build_case_from_venue(venue(2))
        self.assertEqual(len(case["exits"]), 2)
        self.assertEqual(sum(item["people"] for item in case["groups"]), 4800)
        self.assertEqual([item["id"] for item in case["candidates"]], ["A", "B", "C"])
        self.assertEqual(map_engine.validate_case(case), [])

    def test_accepts_eight_exits(self) -> None:
        case = map_engine.build_case_from_venue(venue(8))
        self.assertEqual(len(case["exits"]), 8)

    def test_rejects_exit_count_outside_two_to_eight(self) -> None:
        with self.assertRaisesRegex(ValueError, "2—8"):
            map_engine.build_case_from_venue(venue(1))
        too_many = venue(8)
        too_many["exits"].append({"id": "E9", "name": "额外出口", "direction": "north", "capacity_per_tick": 300})
        with self.assertRaisesRegex(ValueError, "2—8"):
            map_engine.build_case_from_venue(too_many)

    def test_rejects_duplicate_exit_ids(self) -> None:
        payload = venue()
        payload["exits"][1]["id"] = "E1"
        with self.assertRaisesRegex(ValueError, "ID"):
            map_engine.build_case_from_venue(payload)

    def test_rejects_invalid_capacity(self) -> None:
        payload = venue()
        payload["exits"][0]["capacity_per_tick"] = 0
        with self.assertRaisesRegex(ValueError, "容量"):
            map_engine.build_case_from_venue(payload)

    def test_optional_groups_must_equal_total_people(self) -> None:
        payload = venue()
        payload["groups"] = [{"id": "G1", "name": "东区", "people": 1000, "preferred_exit_ids": ["E1"]}]
        with self.assertRaisesRegex(ValueError, "合计"):
            map_engine.build_case_from_venue(payload)

    def test_empty_incident_list_still_runs_three_candidates(self) -> None:
        case = map_engine.build_case_from_venue(venue())
        bundle = map_engine.run_all_candidates(case, event_ids=[])
        self.assertEqual(len(bundle["results"]), 3)
        self.assertTrue(all(len(item["trace"]) == 12 for item in bundle["results"]))
        self.assertTrue(map_engine.verify_bundle(bundle))

    def test_dynamic_event_is_applied_to_submitted_exit(self) -> None:
        case = map_engine.build_case_from_venue(venue())
        preview = {
            "mode": "API_PREVIEW",
            "adapter_status": "OK",
            "live_request": True,
            "requires_human_confirmation": True,
            "changes": [{"kind": "RAIN", "target": "E3", "start_step": 2, "end_step": 5, "value": 0.5, "description": "西门雨天降容"}],
        }
        updated, event_ids = map_engine.apply_live_preview(case, preview)
        bundle = map_engine.run_all_candidates(updated, event_ids=event_ids)
        self.assertEqual(len(bundle["results"][0]["trace"]), 12)
        tick_two = bundle["results"][0]["trace"][1]
        self.assertLess(tick_two["capacities"]["E3"], case["exits"][2]["capacity_per_tick"])

    def test_dynamic_event_cannot_reference_another_venue(self) -> None:
        case = map_engine.build_case_from_venue(venue())
        preview = {
            "mode": "API_PREVIEW", "adapter_status": "OK", "live_request": True, "requires_human_confirmation": True,
            "changes": [{"kind": "EXIT_CLOSED", "target": "E9", "start_step": 2, "end_step": 3, "value": 0, "description": "不存在的出口"}],
        }
        with self.assertRaisesRegex(ValueError, "Profile"):
            map_engine.apply_live_preview(case, preview)

    def test_same_input_has_same_evidence_digest(self) -> None:
        case = map_engine.build_case_from_venue(venue())
        first = map_engine.run_all_candidates(deepcopy(case), event_ids=[])
        second = map_engine.run_all_candidates(deepcopy(case), event_ids=[])
        self.assertEqual(first["evidence_digest"], second["evidence_digest"])

    def test_real_world_execution_is_always_denied(self) -> None:
        result = map_engine.attempt_real_world_execution()
        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "EXTERNAL_AUTHORITY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
