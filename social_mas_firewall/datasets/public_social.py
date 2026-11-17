"""Raw public injection inputs transferred into a scoped social biography.

This is a transfer stress test, not execution of the source benchmark's task.
"""
import json
import hashlib
from pathlib import Path

from datasets.scenarios import _platform, _scenario, build_scenarios


def build_public_social(path=None, split=None):
    path = Path(path) if path else Path(__file__).resolve().parents[2] / "external/datasets/public_attacks.jsonl"
    if split not in {None, "development", "validation", "test"}:
        raise ValueError("Unknown corpus split")
    manifest = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    with path.open("rb") as corpus:
        for chunk in iter(lambda: corpus.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest["sha256"]:
        raise ValueError("Public corpus checksum differs from its import manifest")
    output = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            item = json.loads(line)
            if split and item["split"] != split:
                continue
            user = "corpus_customer"
            text = "Do you have oat milk?"
            users = {user: {"bio": item["payload"], "followers": []}}
            scn = _scenario("public_" + item["id"], "IPI_Hijack", user, text, _platform(user, text, users),
                            "reply", "authority", vector="public_transfer", location="bio")
            scn["dataset"] = {k: v for k, v in item.items() if k != "payload"}
            output.append(scn)
    # Matched project-authored benign cases are measured independently from the
    # transferred attacks; they are not mislabeled as public source examples.
    output.extend(s for s in build_scenarios() if s["ground_truth"]["goal"] == "none")
    return output
