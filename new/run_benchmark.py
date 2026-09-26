import argparse
import asyncio
import json
from pathlib import Path

from benchmark.harness import run_all
from benchmark.metrics import compute_metrics
from dataset.build_dataset import DATASET_PATH, generate_dataset

RESULTS_DIR = Path(__file__).parent / "results"


async def main(limit, regenerate, quiet):
    if regenerate or not DATASET_PATH.exists():
        generate_dataset()
    dataset = json.loads(DATASET_PATH.read_text())

    RESULTS_DIR.mkdir(exist_ok=True)
    run_tag = f"n{limit or len(dataset)}"
    raw_path = RESULTS_DIR / f"raw_results_{run_tag}.json"

    # Flushed to disk after every single item (not just at the end) -- a real
    # sweep against local models can run for hours, and a crash partway
    # through must not lose already-completed results.
    accumulated: list[dict] = []

    def _flush(result: dict) -> None:
        accumulated.append(result)
        raw_path.write_text(json.dumps(accumulated, indent=2))

    results = await run_all(dataset, limit=limit, verbose=not quiet, on_result=_flush)

    metrics = compute_metrics(results)
    (RESULTS_DIR / f"metrics_{run_tag}.json").write_text(json.dumps(metrics, indent=2))

    print("\n=== Metrics ===")
    for label in ("baseline_a", "baseline_b", "proposed"):
        m = metrics.get(label)
        if not m:
            continue
        print(f"{label:12s}  ASR={m['ASR']:6.1%}  CSS={m['CSS']:6.1%}  "
              f"ST={m.get('ST', 0):+6.1%}  LT={m.get('LT', 0):+7.1f}%  "
              f"avg_latency={m['avg_latency_ms']:8.0f}ms  n={m['n']}")
    print(f"\nWrote results/raw_results_{run_tag}.json and results/metrics_{run_tag}.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Baseline A / B / Proposed benchmark sweep.")
    parser.add_argument("--limit", type=int, default=None, help="Only use the first N dataset items per config (default: all 200).")
    parser.add_argument("--regenerate", action="store_true", help="Rebuild dataset/dataset.json even if it already exists.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-item progress lines.")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.regenerate, args.quiet))
