import time
from typing import Literal, Optional

import httpx

from app import create_app

CONFIGS: list[Literal["baseline_a", "baseline_b", "proposed"]] = ["baseline_a", "baseline_b", "proposed"]


async def run_item(client: httpx.AsyncClient, item: dict, config_label: str) -> dict:
    start = time.time()
    resp = await client.post("/moderate", json=item)
    latency_ms = (time.time() - start) * 1000

    if resp.status_code == 403:
        detail = resp.json().get("error", {}).get("details", "")
        return {
            "post_id": item["post_id"], "category": item["category"], "config_label": config_label,
            "ground_truth": item["ground_truth"], "final_action": "BLOCKED_AT_INGRESS",
            "iteration_count": 0, "latency_ms": latency_ms, "detail": detail,
        }

    data = resp.json()
    return {
        "post_id": item["post_id"], "category": item["category"], "config_label": config_label,
        "ground_truth": item["ground_truth"], "final_action": data.get("final_action"),
        "iteration_count": data.get("iteration_count", 1), "latency_ms": latency_ms,
        "detail": data.get("policy_rationale", ""),
    }


async def run_all(dataset: list[dict], limit: Optional[int] = None, verbose: bool = True) -> list[dict]:
    items = dataset if limit is None else dataset[:limit]
    results = []
    for config_label in CONFIGS:
        fastapi_app = create_app(config_label)
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://firewall-bench", timeout=180.0) as client:
            for item in items:
                result = await run_item(client, item, config_label)
                results.append(result)
                if verbose:
                    print(f"[{config_label}] {item['post_id']} ({item['category']}) -> "
                          f"{result['final_action']} ({result['latency_ms']:.0f}ms, iter={result['iteration_count']})")
    return results
