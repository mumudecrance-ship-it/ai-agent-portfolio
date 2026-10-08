from __future__ import annotations

import json
from pathlib import Path
import unittest

import live_agent


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "live-output-schema.json").read_text(encoding="utf-8"))


class LiveAgentTests(unittest.TestCase):
    def tearDown(self) -> None:
        live_agent.clear_session()

    def test_deepseek_root_normalizes_to_chat_completions(self) -> None:
        self.assertEqual(live_agent._clean_base_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")
        self.assertEqual(live_agent._clean_base_url("https://api.deepseek.com/v1"), "https://api.deepseek.com/v1/chat/completions")

    def test_key_status_only_returns_mask(self) -> None:
        status = live_agent.configure_session({"api_key": "test-only-key-123456", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"})
        self.assertTrue(status["configured"])
        self.assertEqual(status["key_mask"], "••••3456")
        self.assertNotIn("sk-test-only", json.dumps(status))
        self.assertEqual(status["key_persistence"], "PROCESS_MEMORY_ONLY")

    def test_deepseek_uses_json_object_and_schema_instruction(self) -> None:
        live_agent.configure_session({"api_key": "test-only-key-123456", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"})
        captured = {}
        output_body = {
            "interpretation_status": "READY", "summary": "无突发事件", "changes": [], "local_intents": [],
            "handoff_boundary": {"current_status": "DRAFT", "next_owner": "HUMAN", "external_boundary": "NO_EXECUTION"},
        }

        def fake_request(config, payload):
            captured.update(payload)
            return {"id": "deepseek-test", "choices": [{"message": {"content": json.dumps(output_body, ensure_ascii=False)}}]}

        result = live_agent.run_structured(system_prompt="只整理变化", user_text="本轮明确没有突发事件", schema_name="test_schema", schema=SCHEMA, request_fn=fake_request)
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertIn("JSON Schema", captured["messages"][0]["content"])
        self.assertEqual(result["metadata"]["transport"], "CHAT_COMPLETIONS")
        self.assertTrue(result["metadata"]["no_silent_fallback"])


if __name__ == "__main__":
    unittest.main()
