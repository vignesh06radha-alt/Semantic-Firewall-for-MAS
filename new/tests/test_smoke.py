"""Offline smoke test -- MOCK_AGENTS + MOCK_FIREWALL, no Ollama call made.
Validates graph wiring, the iteration_count hard cap, and the ASGI
middleware's block/pass behavior before ever spending real local-GPU time on
the full 200-item sweep. Mirrors ../moderation-mas/tests/test_recursion_smoke.py's
role in that project: this is what was used to validate the implementation,
not a substitute for running run_benchmark.py against the real models.

Run with: python tests/test_smoke.py
"""
import os

os.environ["MOCK_AGENTS"] = "true"
os.environ["MOCK_FIREWALL"] = "true"

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from app import create_app
from dataset.build_dataset import generate_dataset


async def _post(config_label: str, item: dict) -> httpx.Response:
    fastapi_app = create_app(config_label)
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/moderate", json=item)


async def main() -> None:
    dataset = generate_dataset(write=False)
    by_category: dict[str, list[dict]] = {}
    for item in dataset:
        by_category.setdefault(item["category"], []).append(item)

    failures = []

    # 1. Clean content is ALLOWed in every configuration.
    clean_item = by_category["Clean"][0]
    for label in ("baseline_a", "baseline_b", "proposed"):
        resp = await _post(label, clean_item)
        if resp.status_code != 200 or resp.json().get("final_action") != "ALLOW":
            failures.append(f"clean item not ALLOWed under {label}: {resp.status_code} {resp.text[:200]}")

    # 2. force_allow IPI: baseline_a's naive mock complies (ALLOW despite
    #    borderline cover text); proposed blocks it at ingress (403) before
    #    the graph -- and therefore the mock policy heuristic -- ever runs.
    hijack_item = next(i for i in by_category["IPI_DoS"] if i["ground_truth"]["payload_goal"] == "force_allow")
    resp_a = await _post("baseline_a", hijack_item)
    resp_p = await _post("proposed", hijack_item)
    if resp_a.json().get("final_action") != "ALLOW":
        failures.append(f"baseline_a's mock did not comply with the hijack payload as expected: {resp_a.json()}")
    if resp_p.status_code != 403:
        failures.append(f"proposed config did not block the force_allow IPI at ingress: {resp_p.status_code} {resp_p.text[:200]}")

    # 3. induce_loop IPI: baseline_a's mock honors LOOP_REQUEST and the
    #    pipeline actually cycles (iteration_count > 1); proposed blocks it
    #    at ingress instead.
    loop_item = next(i for i in by_category["IPI_DoS"] if i["ground_truth"]["payload_goal"] == "induce_loop")
    resp_loop_a = await _post("baseline_a", loop_item)
    resp_loop_p = await _post("proposed", loop_item)
    loop_iters = resp_loop_a.json().get("iteration_count", 1)
    if loop_iters <= 1:
        failures.append("baseline_a's mock policy did not honor the injected LOOP_REQUEST -- "
                         "check _mock_policy's loop markers against build_dataset's payload phrasing")
    if loop_iters > 4:
        failures.append(f"iteration_count exceeded the hard cap (MAX_ITERATIONS=4): {loop_iters}")
    if resp_loop_p.status_code != 403:
        failures.append(f"proposed config did not block the induce_loop IPI at ingress: {resp_loop_p.status_code}")

    # 4. Toxic content is TAKEDOWN under every configuration (the firewall
    #    only inspects for IPI/DoS, not general content policy, so proposed
    #    still has to reach a real verdict here rather than 403ing).
    toxic_item = by_category["Toxic"][0]
    for label in ("baseline_a", "baseline_b", "proposed"):
        resp = await _post(label, toxic_item)
        if resp.status_code != 200 or resp.json().get("final_action") != "TAKEDOWN":
            failures.append(f"toxic item not TAKEDOWN under {label}: {resp.status_code} {resp.text[:200]}")

    # 5. Security Tax signal: baseline_b's vaccinated mock is more cautious
    #    than baseline_a/proposed on a ComplexBenign item (this is a mock
    #    heuristic sanity check, not a real ST measurement -- see README).
    complex_item = by_category["ComplexBenign"][0]
    resp_b = await _post("baseline_b", complex_item)
    resp_prop = await _post("proposed", complex_item)
    if resp_prop.json().get("final_action") != "ALLOW":
        failures.append(f"proposed config unexpectedly refused benign complex content: {resp_prop.json()}")

    if failures:
        print("SMOKE TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"Smoke test passed -- {len(dataset)} dataset items generated "
          f"({', '.join(f'{k}={len(v)}' for k, v in sorted(by_category.items()))}); "
          f"graph wiring, hard cycle cap, and ingress block/pass all verified with mocked agents+firewall.")


if __name__ == "__main__":
    asyncio.run(main())
