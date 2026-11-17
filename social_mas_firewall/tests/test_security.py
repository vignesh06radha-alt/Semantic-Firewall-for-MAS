"""Security boundaries must hold even when every semantic verdict allows."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security.runtime import Action, Permission, PolicyDenied, SecurityRuntime, TaskPolicy


class RuntimeTests(unittest.TestCase):
    def runtime(self, **kwargs):
        return SecurityRuntime(TaskPolicy("task", (
            Permission("read", frozenset({"record"})),
            Permission("reply", frozenset({"post"}), frozenset({"customer"}), write=True),
        ), **kwargs))

    def test_wrong_recipient_and_tool_never_execute(self):
        runtime = self.runtime()
        calls = []
        for action in (Action("reply", "post", "attacker", "hello", write=True),
                       Action("publish", "post", text="hello", write=True)):
            with self.assertRaises(PolicyDenied):
                runtime.execute(action, lambda: calls.append(action))
        self.assertEqual(calls, [])

    def test_read_scope_checked_before_fetch(self):
        runtime = self.runtime()
        with self.assertRaises(PolicyDenied):
            runtime.execute(Action("read", "other"), lambda: self.fail("unauthorized fetch"))

    def test_repeated_write_and_failed_write_still_spend_budget(self):
        runtime = self.runtime(max_writes=1)
        action = Action("reply", "post", "customer", "hello", write=True)
        with self.assertRaises(RuntimeError):
            runtime.execute(action, lambda: (_ for _ in ()).throw(RuntimeError("uncertain outcome")))
        with self.assertRaises(PolicyDenied):
            runtime.execute(action, lambda: self.fail("retry must not repeat write"))

    def test_summary_retains_restricted_input(self):
        runtime = self.runtime()
        source = runtime.record("private", "value", confidentiality="restricted")
        summary = runtime.record("summary", "paraphrase", parents=(source,))
        with self.assertRaises(PolicyDenied):
            runtime.execute(Action("reply", "post", "customer", "paraphrase", write=True),
                            lambda: self.fail("disclosure"), sources=(summary,))
        self.assertEqual(runtime.sources[summary].confidentiality, "restricted")

    def test_unknown_source_and_cross_task_reference_fail_closed(self):
        runtime = self.runtime()
        with self.assertRaises(PolicyDenied):
            runtime.record("summary", "text", parents=("other-task:1",))
        with self.assertRaises(PolicyDenied):
            runtime.check(Action("reply", "post", "customer", "text", write=True), ("unknown",))

    def test_revoke_and_model_budget(self):
        runtime = self.runtime(max_model_calls=1)
        runtime.before_model()
        with self.assertRaises(PolicyDenied):
            runtime.before_model()
        runtime.revoke()
        with self.assertRaises(PolicyDenied):
            runtime.execute(Action("read", "record"), lambda: None)

    def test_whole_batch_checked_before_first_write(self):
        runtime = self.runtime(max_writes=1)
        action = Action("reply", "post", "customer", "text", write=True)
        with self.assertRaises(PolicyDenied):
            runtime.check_batch([action, action])
        self.assertEqual(runtime.writes, 0)

    def test_public_untrusted_data_can_support_authorized_reply(self):
        runtime = self.runtime()
        source = runtime.record("comment", "Do you have oat milk?")
        self.assertEqual(runtime.execute(Action("reply", "post", "customer", "Yes", write=True),
                                        lambda: "sent", sources=(source,)), "sent")

    def test_omitting_restricted_citations_cannot_declassify(self):
        runtime = self.runtime()
        runtime.record("private", "secret", confidentiality="restricted")
        with self.assertRaises(PolicyDenied):
            runtime.check(Action("reply", "post", "customer", "paraphrase", write=True), ())

    def test_delegation_shares_budget_and_cannot_expand(self):
        runtime = self.runtime(max_writes=1)
        child = runtime.delegate((runtime.policy.permissions[1],))
        child.execute(Action("reply", "post", "customer", "one", write=True), lambda: None)
        with self.assertRaises(PolicyDenied):
            runtime.execute(Action("reply", "post", "customer", "two", write=True), lambda: None)
        with self.assertRaises(PolicyDenied):
            runtime.delegate((Permission("publish", frozenset({"post"}), write=True),))


if __name__ == "__main__":
    unittest.main()
