"""Offline, exact counterexample memory. Never trains on a model's own verdict."""
import json
from pathlib import Path
import re

from evaluation.metrics import adaptive_succeeded


class VerifiedMemory:
    def __init__(self, entries=()):
        self.entries = list(entries)
        self.digests = {e["payload_sha256"] for e in entries}

    @classmethod
    def load(cls, path):
        if not path:
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != "verified_counterexamples_v1":
            raise ValueError("Unknown memory version")
        entries = data["entries"]
        for e in entries:
            if (not re.fullmatch(r"[0-9a-f]{64}", e.get("payload_sha256", ""))
                    or e.get("split") != "development"
                    or not re.fullmatch(r"[0-9a-f]{64}", e.get("evidence_sha256", ""))):
                raise ValueError("Unverified memory entry")
        return cls(entries)

    def admit(self, scenario, row, *, evidence_sha256, forbidden_benign_digests=()):
        if scenario.get("dataset", {}).get("split") != "development":
            raise ValueError("Learning is restricted to development evidence")
        if scenario["ground_truth"]["goal"] == "none":
            raise ValueError("A clean task cannot become an attack training label")
        if (row.get("mock_llm") is not False or row.get("id") != scenario["id"]
                or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256)
                or not adaptive_succeeded(scenario, row)):
            raise ValueError("A verified live forbidden effect is required")
        source = "ingress" if scenario["ground_truth"]["location"] == "comment" else "tool:pass1"
        added = 0
        for event in row.get("guard_events", []):
            digest = event.get("payload_sha256", "")
            if event.get("source") != source or not re.fullmatch(r"[0-9a-f]{64}", digest):
                continue
            if digest in forbidden_benign_digests:
                raise ValueError("Counterexample collides with a benign control")
            if digest not in self.digests:
                self.entries.append({"payload_sha256": digest, "split": "development",
                                     "scenario": scenario["id"], "evidence_sha256": evidence_sha256})
                self.digests.add(digest)
                added += 1
        return added

    def save(self, path):
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps({"version": "verified_counterexamples_v1", "entries": self.entries}, indent=2), encoding="utf-8")
        temporary.replace(path)
