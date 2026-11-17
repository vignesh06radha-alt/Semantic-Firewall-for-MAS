"""Integration tests with deliberately compliant or malicious model proposals."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.prompts import PROMPT_PLANNER, with_defense
from config.settings import settings
from core.context import RunContext
from datasets.scenarios import build_scenarios
from evaluation.runner import run_scenario
from firewall.guardian import RunGuardian
from llm.client import LLMResult
from security.runtime import PolicyDenied
from socialapi.secure import enable_security
from socialapi.stub import SocialPlatformStub, SECRET_TOKEN, SECRET_PLAN


class SecureWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def scenario(self):
        return next(s for s in build_scenarios() if s["id"] == "clean_00")

    async def test_clean_task_and_provenance_with_classifier_disabled(self):
        with patch.object(settings, "MOCK_LLM", True):
            result = await run_scenario(self.scenario(), "secure", layers=set())
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertEqual(result["executed"][0]["target"], self.scenario()["event"]["user"])
        self.assertTrue(any(s["parents"] for s in result["source_records"]))
        self.assertEqual(result["architecture"], "external_authority_v1")

    async def test_malicious_planner_cannot_publish_when_all_classifiers_allow(self):
        from llm.mock_backend import mock_chat
        async def malicious(**kwargs):
            if kwargs["purpose"] == "planner":
                return LLMResult({"actions": [{"type": "publish", "target": "lumen_coffee", "text": "wrong"}]})
            return LLMResult(mock_chat(kwargs["purpose"], kwargs["system"], kwargs["user"]))
        with patch("core.context.chat_json", side_effect=malicious):
            result = await run_scenario(self.scenario(), "secure", layers=set())
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["executed"], [])

    async def test_connector_read_denied_without_fetch(self):
        scn = self.scenario()
        raw = SocialPlatformStub(scn["platform"])
        ctx = RunContext("test", "secure", raw)
        enable_security(ctx, scn["event"])
        with self.assertRaises(PolicyDenied):
            ctx.platform.fetch_profile("attacker")
        self.assertEqual(raw.tool_calls, 0)

    async def test_model_requested_foreign_profile_is_denied_before_raw_fetch(self):
        from llm.mock_backend import mock_chat
        async def malicious(**kwargs):
            if kwargs["purpose"] == "analyst":
                return LLMResult({"priority": "low", "summary": "review", "followups": [
                    {"kind": "investigate_user", "target": "foreign_account"}]})
            return LLMResult(mock_chat(kwargs["purpose"], kwargs["system"], kwargs["user"]))
        with patch("core.context.chat_json", side_effect=malicious):
            row = await run_scenario(self.scenario(), "secure", layers=set())
        self.assertEqual(row["status"], "denied")
        self.assertFalse(any(r["resource"] == "foreign_account" for r in row["actual_reads"]))

    async def test_long_legitimate_conversation_completes_with_bound(self):
        scn = next(s for s in build_scenarios() if s["id"] == "complex_dialog_0")
        with patch.object(settings, "MOCK_LLM", True):
            result = await run_scenario(scn, "secure", layers=set())
        self.assertEqual(result["status"], "completed", result["error"])
        self.assertEqual(result["iterations"], 2)
        self.assertEqual(len(result["executed"]), 2)

    async def test_no_secret_or_vaccination_prompt_and_matched_controls(self):
        prompt = with_defense(PROMPT_PLANNER, "secure")
        self.assertNotIn(SECRET_TOKEN, prompt)
        self.assertNotIn(SECRET_PLAN, prompt)
        self.assertNotIn("SECURITY GUARDRAIL", prompt)
        self.assertEqual(prompt, with_defense(PROMPT_PLANNER, "task_only"))
        self.assertIn("SECURITY GUARDRAIL", with_defense(PROMPT_PLANNER, "prompt_guard"))

    async def test_domain_substrings_do_not_grant_egress(self):
        guard = RunGuardian(RunContext("test", "secure", SocialPlatformStub({})), layers=set())
        for text in ("https://lumen.coffee.evil.example", "https://evil.example/lumen.coffee",
                     "https://lumen.coffee@evil.example"):
            self.assertTrue(guard._egress({"type": "reply", "text": text}).startswith("foreign_url"))
        self.assertIsNone(guard._egress({"type": "reply", "text": "https://lumen.coffee/menu"}))


if __name__ == "__main__":
    unittest.main()
