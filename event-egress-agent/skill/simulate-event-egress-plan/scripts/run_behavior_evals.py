#!/usr/bin/env python3
"""Run the Skill's four observable behavior classes against its host Demo."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = Path(os.getenv("EVENT_SIM_DEMO_ROOT", str(SKILL_ROOT.parents[1]))).expanduser().resolve()
if not (DEMO_ROOT / "map_engine.py").is_file():
    raise RuntimeError(
        "找不到活动推演执行适配层 map_engine.py；"
        "请把 Skill 放在本 Demo 的 skill 目录中，或通过 EVENT_SIM_DEMO_ROOT 指向 Demo 根目录。"
    )
sys.path.insert(0, str(DEMO_ROOT))

from map_engine import (  # noqa: E402
    attempt_real_world_execution,
    load_case,
    run_all_candidates,
    simulate_candidate,
)


def execute(action: str) -> dict:
    if action == "run_all":
        return run_all_candidates()
    if action == "missing_input":
        payload = load_case()
        payload.pop("groups")
        return simulate_candidate(payload, "A")
    if action == "non_trigger":
        payload = load_case()
        payload["task_type"] = "single_person_navigation"
        return simulate_candidate(payload, "A")
    if action == "execute":
        return attempt_real_world_execution()
    raise ValueError(f"unknown eval action: {action}")


def main() -> int:
    cases = json.loads(
        (SKILL_ROOT / "evals" / "behavior_cases.json").read_text(encoding="utf-8")
    )
    details = []
    for case in cases:
        result = execute(case["action"])
        actual = result.get("decision")
        details.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "expected": case["expected"],
                "actual": actual,
                "ok": actual == case["expected"],
            }
        )

    passed = sum(item["ok"] for item in details)
    report = {"passed": passed, "total": len(details), "details": details}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == len(details) else 1


if __name__ == "__main__":
    raise SystemExit(main())
