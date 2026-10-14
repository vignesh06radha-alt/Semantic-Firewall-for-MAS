"""Offline smoke test (MOCK_LLM): verifies wiring, ingress gates, kill
switch, commit gate and metrics with no GPU. It says nothing about how a real
model behaves -- see README 'Mock vs real'. Run: python tests/test_smoke.py
"""
import os

os.environ["MOCK_LLM"] = "true"

import asyncio
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets.heldout import build_heldout
from datasets.scenarios import ATTACK_CATEGORIES, build_scenarios
from evaluation.metrics import attack_succeeded, benign_completed
from evaluation.runner import run_scenario
from firewall.detector import detect
from firewall.sanitizer import normalize_payload


def detector_report(scenarios: list[dict], strict: bool = True) -> list[str]:
    """Deterministic layer only: no false blocks/holds on benign text, and a
    recall breakdown on attacks (reported, not asserted -- the judge and the
    runtime watch exist precisely for what patterns miss)."""
    failures, caught, total = [], defaultdict(int), defaultdict(int)
    for s in scenarios:
        texts = [s["event"]["text"]] + [u.get("bio", "") for u in s["platform"]["users"].values()]
        ring = s["platform"].get("ring_bio")
        if ring:
            texts.append(ring)
        tiers = [detect(*normalize_payload(t)).tier for t in texts if t]
        worst = "block" if "block" in tiers else "suspect" if "suspect" in tiers else "clean"
        if s["category"] in ATTACK_CATEGORIES:
            key = f"{s['category']}/{s['ground_truth']['vector']}"
            total[key] += 1
            caught[key] += worst != "clean"
        elif worst != "clean":
            print(f"  [report] held-out benign flagged {worst}: {s['event']['text'][:70]!r}")
        elif worst != "clean" and strict:
            failures.append(f"detector flagged benign {s['id']} as {worst}: {s['event']['text'][:70]!r}")
    print("detector recall (block or suspect) on attacks, by category/vector:")
    for k in sorted(total):
        print(f"  {k:<28} {caught[k]}/{total[k]}")
    return failures


async def main() -> None:
    scenarios = build_scenarios()
    by_cat = defaultdict(list)
    for s in scenarios:
        by_cat[s["category"]].append(s)
    print(f"{len(scenarios)} scenarios: {dict(Counter(s['category'] for s in scenarios))}")
    failures = detector_report(scenarios)
    print("\n-- held-out set (deterministic layer only; the judge and egress exist for what this misses) --")
    detector_report(build_heldout(), strict=False)

    # 1. A naive agent really is exploitable (otherwise nothing below means anything).
    hijack = by_cat["IPI_Hijack"][0]
    base = await run_scenario(hijack, "baseline")
    if not attack_succeeded(hijack, base):
        failures.append("baseline mock agent did not publish the hijack canary -- harness is not exercising the attack")

    # 2. Firewall stops every attack category's first sample, with no outward side effect.
    for cat in sorted(ATTACK_CATEGORIES & set(by_cat)):
        scn = by_cat[cat][0]
        res = await run_scenario(scn, "firewall")
        if attack_succeeded(scn, res):
            failures.append(f"firewall let {scn['id']} succeed: {res['kill_reason']}")
        if scn["ground_truth"]["goal"] in ("hijack", "exfil") and res["executed"]:
            failures.append(f"{scn['id']}: side effects executed before/despite the guardian: {res['executed']}")

    # 3. Bio-borne (mid-run fetched) injection is caught even though ingress text is benign.
    bio = next(s for s in by_cat["IPI_Hijack"] if s["ground_truth"]["location"] == "bio")
    res = await run_scenario(bio, "firewall")
    if attack_succeeded(bio, res) or not (res["killed"] or res["held"]):
        failures.append(f"bio-location injection {bio['id']} not stopped: {res['status']} {res['kill_reason']}")

    # 4. Polite bot ping-pong (no injection text) is cut by the runtime watch, below the DoS threshold.
    pp = by_cat["CORBA_PingPong"][0]
    res = await run_scenario(pp, "firewall")
    if not res["killed"] or attack_succeeded(pp, res):
        failures.append(f"ping-pong not contained: iter={res['iterations']} kill={res['kill_reason']!r}")
    unguarded = await run_scenario(pp, "baseline")
    if not attack_succeeded(pp, unguarded):
        failures.append("baseline ping-pong did not exceed the DoS threshold")

    # 5. Legitimate 2-turn conversations still complete under the firewall (the watch must not over-fire).
    for scn in [s for s in by_cat["ComplexBenign"] if "dialog" in s["id"]]:
        res = await run_scenario(scn, "firewall")
        if res["status"] != "completed" or res["iterations"] != 2:
            failures.append(f"legit dialog {scn['id']} disturbed: status={res['status']} iter={res['iterations']} {res['kill_reason']}")

    # 6. No benign scenario is killed, held or refused under the firewall.
    for scn in by_cat["Clean"] + by_cat["ComplexBenign"]:
        res = await run_scenario(scn, "firewall")
        if not benign_completed(scn, res):
            failures.append(f"firewall hurt benign {scn['id']}: status={res['status']} held={res['held']} {res['kill_reason']} {res['quarantine']}")

    # 7. The alternate schedule also awaits ingress clearance before any model call.
    scn = by_cat["IPI_Hijack"][0]
    seq = await run_scenario(scn, "firewall", parallel=False)
    if seq["llm_calls"] != 0 or not seq["killed"]:
        failures.append(f"sequential guard should stop an ingress attack before any agent call: {seq['llm_calls']} calls")

    if failures:
        print("\nSMOKE TEST FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("\nSmoke test passed (mocked LLMs): wiring, ingress gates, kill switch, commit gate, runtime watch, metrics.")


if __name__ == "__main__":
    asyncio.run(main())
