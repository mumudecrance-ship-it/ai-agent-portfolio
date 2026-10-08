from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.project_ui = (ROOT / "project.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "styles.css").read_text(encoding="utf-8")
        cls.project = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))

    def test_port_is_consistently_8927(self) -> None:
        self.assertEqual(self.project["port"], 8927)
        self.assertIn("--port 8927", (ROOT / "启动大型活动推演台.command").read_text(encoding="utf-8"))

    def test_live_editor_supports_two_to_eight_exits(self) -> None:
        for token in ('id="exit-rows"', 'id="add-exit"', 'id="venue-name"', 'id="audience-count"', 'id="zone-notes"'):
            self.assertIn(token, self.html)
        self.assertIn("state.exits.length >= 8", self.js)
        self.assertIn("state.exits.length <= 2", self.js)

    def test_event_input_is_free_natural_language(self) -> None:
        self.assertIn('id="event-description"', self.html)
        self.assertIn("不需要填固定模板", self.html)
        self.assertIn("【自然语言事件】", self.js)

    def test_agent_skill_rule_engine_and_human_are_distinct(self) -> None:
        for role in ("agent", "skill", "rule", "engine", "human"):
            self.assertIn(f'data-flow="{role}"', self.html)
        self.assertIn("replayTrace", self.js)

    def test_interactive_states_and_touch_targets_are_accessible(self) -> None:
        self.assertIn('data-mode="fixed" type="button" aria-pressed="true"', self.html)
        self.assertIn('aria-expanded="false" aria-controls="agent-list"', self.html)
        self.assertIn('button.setAttribute("aria-pressed", active ? "true" : "false")', self.js)
        self.assertIn('setAttribute("aria-expanded", expanded ? "true" : "false")', self.js)
        self.assertIn("button { min-height: 44px; cursor: pointer; }", self.css)
        self.assertIn(".remove-exit { min-width: 44px; min-height: 44px;", self.css)
        self.assertIn('READY_TO_REPLAY: "可以开始固定回放"', self.js)
        self.assertIn("node.dataset.statusCode = status", self.js)
        behavior_runner = (ROOT / "skill" / "simulate-event-egress-plan" / "scripts" / "run_behavior_evals.py").read_text(encoding="utf-8")
        self.assertNotIn('COURSE_ROOT / "02-', behavior_runner)
        self.assertIn("EVENT_SIM_DEMO_ROOT", behavior_runner)
        self.assertIn("from map_engine import", behavior_runner)

    def test_twelve_round_queue_visualization_exists(self) -> None:
        for token in ("tick-track", "queue-ledger", "intent-stream", "sim-map"):
            self.assertIn(token, self.project_ui)
        self.assertIn("repeat(12, 1fr)", self.css)

    def test_live_failure_explicitly_refuses_mock_fallback(self) -> None:
        self.assertIn("不会切回固定案例", self.html)
        self.assertIn("没有切回固定结果", self.js)

    def test_confirmation_and_mode_switch_are_state_gated(self) -> None:
        self.assertIn('id="reviewer" name="reviewer" autocomplete="name" placeholder="先运行可确认候选" disabled', self.html)
        self.assertIn('class="confirm-button" type="submit" disabled', self.html)
        self.assertIn('decision === "PENDING_HUMAN_CONFIRMATION" && Boolean(digest)', self.js)
        self.assertIn('if (state.busy) return;', self.js)
        self.assertIn('payload.result.candidate_digest', self.js)

    def test_no_real_api_key_is_committed(self) -> None:
        pattern = re.compile(r"sk-[A-Za-z0-9]{20,}")
        for path in ROOT.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".js", ".html", ".json", ".md", ".example", ".command"}:
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8", errors="ignore")), str(path))


if __name__ == "__main__":
    unittest.main()
