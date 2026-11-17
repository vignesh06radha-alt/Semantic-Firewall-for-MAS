"""Download a bounded, deduplicated public attack corpus with source lineage.

Uses official InjecAgent files and Microsoft LLMail challenge submissions.
Records are data only: never import or execute downloaded Python or prompt text.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import httpx

INJEC_COMMIT = "f19c9f2c79a41046eb13c03c51a24c567a8ffa07"
HF_REPO = "microsoft/llmail-inject-challenge"


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def record(text, source, revision, source_id, group, goal):
    digest = hashlib.sha256(normalize(text).encode()).hexdigest()
    group_digest = hashlib.sha256((source + ":" + str(group)).encode()).hexdigest()
    bucket = int(group_digest[:8], 16) % 10
    return {"id": digest, "payload": text, "source": source, "revision": revision,
            "source_id": source_id, "group_hash": group_digest,
            "split": "development" if bucket < 6 else "validation" if bucket < 8 else "test",
            "original_goal": goal, "evaluation": "cross_domain_social_transfer",
            "license": "MIT" if source == "LLMail-Inject" else "not verified from source"}


def download(destination, limit=5000):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Choose a new destination; existing corpus will not be replaced")
    records, seen = [], set()
    stats = {"duplicates": 0, "oversized": 0, "empty": 0, "scanned": 0}
    def add(item):
        stats["scanned"] += 1
        if not item["payload"].strip():
            stats["empty"] += 1
        elif len(item["payload"]) > 12000:
            stats["oversized"] += 1
        elif item["id"] in seen:
            stats["duplicates"] += 1
        else:
            seen.add(item["id"])
            records.append(item)
    with httpx.Client(timeout=60, follow_redirects=True, trust_env=False) as client:
        for filename in ("test_cases_dh_base.json", "test_cases_ds_base.json"):
            url = f"https://raw.githubusercontent.com/uiuc-kang-lab/InjecAgent/{INJEC_COMMIT}/data/{filename}"
            response = client.get(url)
            response.raise_for_status()
            for i, row in enumerate(response.json()):
                add(record(row["Tool Response"], "InjecAgent", INJEC_COMMIT, f"{filename}:{i}",
                           row["Attacker Instruction"], row["Attacker Instruction"]))
        pinned = Path(__file__).with_name("public_corpus_manifest.json")
        if pinned.exists():
            revision = json.loads(pinned.read_text(encoding="utf-8"))["source_revisions"]["LLMail-Inject"]
        else:
            meta = client.get(f"https://huggingface.co/api/datasets/{HF_REPO}")
            meta.raise_for_status()
            revision = meta.json()["sha"]
        url = f"https://huggingface.co/datasets/{HF_REPO}/resolve/{revision}/data/raw_submissions_phase2.jsonl"
        microsoft_count = 0
        with client.stream("GET", url) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                row = json.loads(line)
                text = row.get("subject", "") + "\n" + row.get("body", "")
                before = len(records)
                add(record(text, "LLMail-Inject", revision, row["RowKey"], row["team_id"],
                           "Cause an unauthorized communication or disclosure in the source email assistant"))
                microsoft_count += len(records) > before
                if microsoft_count >= limit or stats["scanned"] >= 100000:
                    break
    # Exact duplicate content is removed before splitting. Team-level Microsoft
    # grouping and original-goal InjecAgent grouping reduce related-case leakage.
    # These are not guarantees against all near-duplicate or cross-source leakage.
    with destination.open("x", encoding="utf-8") as output:
        for item in records:
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
    manifest = {"records": len(records), "counts": {source: sum(r["source"] == source for r in records)
                                                   for source in ("InjecAgent", "LLMail-Inject")},
                "splits": {split: sum(r["split"] == split for r in records)
                           for split in ("development", "validation", "test")},
                "exclusions": stats, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "limitations": ["Bounded prefix sample of phase 2, not a random sample of the complete Microsoft challenge",
                                "Cross-domain transfer inputs, not native AgentDojo or InjecAgent benchmark execution",
                                "Near-duplicate and cross-source leakage are not completely excluded"]}
    destination.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "external/datasets/public_attacks.jsonl")
    p.add_argument("--microsoft-limit", type=int, default=5000)
    args = p.parse_args()
    if args.microsoft_limit < 1:
        p.error("limit must be positive")
    print(json.dumps(download(args.output, args.microsoft_limit), indent=2))


if __name__ == "__main__":
    main()
