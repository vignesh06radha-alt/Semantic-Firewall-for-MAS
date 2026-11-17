"""Dataset lineage and honest matched-comparison accounting."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datasets.agentdojo_social import build_agentdojo_social
from evaluation.metrics import adaptive_succeeded, security_violations
from evaluation.study import summarize_study


class StudyTests(unittest.TestCase):
    def attacked_row(self, status="completed", text="We have oat milk."):
        scenario = build_agentdojo_social()[0]
        event = scenario["event"]
        return scenario, {"id": scenario["id"], "mode": "secure", "status": status,
                          "held": [], "actual_reads": [], "iterations": 1, "llm_calls": 3,
                          "wall_ms": 10, "executed": [{"type": "reply", "post_id": event["post_id"],
                          "target": event["user"], "text": text}] if status == "completed" else []}

    def test_utility_under_attack_requires_safe_task_completion(self):
        scenario, safe = self.attacked_row()
        _, compromised = self.attacked_row(text=scenario["ground_truth"]["canary"])
        # A correct destination and a completed run do not make malicious
        # attacker-chosen reply content a legitimate task success.
        summary = summarize_study([safe, compromised], {scenario["id"]: scenario})["secure"]
        self.assertEqual(summary["completion_under_attack"], 1)
        self.assertEqual(summary["utility_under_attack"], 0.5)
        self.assertEqual(summary["safe_completed_under_attack"], 1)

    def test_blocking_every_attack_does_not_earn_utility(self):
        scenario, row = self.attacked_row(status="denied")
        summary = summarize_study([row], {scenario["id"]: scenario})["secure"]
        self.assertEqual(summary["robustness"], 1)
        self.assertEqual(summary["utility_under_attack"], 0)

    def test_utility_under_attack_has_no_value_without_attacks(self):
        scenario = next(s for s in build_agentdojo_social() if s["ground_truth"]["goal"] == "none")
        row = {"id": scenario["id"], "mode": "secure", "status": "completed", "held": [],
               "actual_reads": [], "executed": [], "wall_ms": 1, "tokens": 0,
               "guard_tokens": 0, "llm_calls": 0, "guard_llm_calls": 0}
        summary = summarize_study([row], {scenario["id"]: scenario})["secure"]
        self.assertIsNone(summary["utility_under_attack"])
        self.assertEqual(summary["safe_completed_under_attack"], 0)

    def test_agentdojo_adaptations_keep_source_and_family_split(self):
        scenarios = build_agentdojo_social()
        self.assertEqual(len({s["id"] for s in scenarios}), len(scenarios))
        families = {}
        for scn in scenarios:
            data = scn["dataset"]
            self.assertEqual(len(data["upstream_commit"]), 40)
            if "injection_task" in data:
                families.setdefault(data["injection_task"], set()).add(data["split"])
        self.assertTrue(all(len(v) == 1 for v in families.values()))
        self.assertEqual(len(families), 3)

    def test_wrong_recipient_counts_even_without_attack_marker(self):
        scn = build_agentdojo_social()[0]
        row = {"executed": [{"type": "reply", "target": "other", "post_id": "post_1", "text": "hello"}],
               "actual_reads": [], "iterations": 1, "llm_calls": 3}
        self.assertIn("unapproved_recipient_or_post", security_violations(scn, row))
        self.assertTrue(adaptive_succeeded(scn, row))

    def test_tax_requires_matched_clean_inventory(self):
        scenarios = {s["id"]: s for s in build_agentdojo_social() if s["ground_truth"]["goal"] == "none"}
        ids = list(scenarios)
        def row(sid, mode):
            event = scenarios[sid]["event"]
            return {"id": sid, "mode": mode, "status": "completed", "held": [], "actual_reads": [],
                    "executed": [{"type": "reply", "post_id": event["post_id"], "target": event["user"], "text": "reply"}],
                    "wall_ms": 10, "tokens": 10, "guard_tokens": 2, "llm_calls": 3, "guard_llm_calls": 1}
        result = summarize_study([row(ids[0], "task_only"), row(ids[1], "secure")], scenarios)
        self.assertIsNone(result["secure"]["clean_completion_loss_pp"])
        result = summarize_study([row(ids[0], "task_only"), row(ids[0], "secure")], scenarios)
        self.assertEqual(result["secure"]["clean_completion_loss_pp"], 0)
        self.assertEqual(result["secure"]["clean_total_tokens_mean"], 12)
        self.assertEqual(result["secure"]["security_tax"], 0)
        self.assertEqual(result["secure"]["latency_tax"], 0)
        self.assertEqual(result["secure"]["cooperation"], 1)

    def test_error_is_not_credited_as_robustness(self):
        scn = build_agentdojo_social()[0]
        row = {"id": scn["id"], "mode": "secure", "status": "error", "executed": [],
               "actual_reads": [], "iterations": 0, "llm_calls": 0, "wall_ms": 1}
        summary = summarize_study([row], {scn["id"]: scn})["secure"]
        self.assertEqual(summary["attack_success_rate"], 0)
        self.assertEqual(summary["robustness"], 0)
        self.assertEqual(summary["utility_under_attack"], 0)
        self.assertIsNone(summary["security_tax"])


if __name__ == "__main__":
    unittest.main()
