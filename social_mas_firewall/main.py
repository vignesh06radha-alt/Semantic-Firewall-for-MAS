import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config.settings import settings
from datasets.heldout import build_heldout
from datasets.scenarios import build_scenarios
from evaluation.metrics import summarize
from evaluation.runner import MODES, run_scenario
from llm.client import chat_json

console = Console(width=120)
RESULTS = Path(__file__).parent / "results"


def _select(scenarios: list[dict], per_category: int | None, categories: set[str] | None) -> list[dict]:
    if categories:
        scenarios = [s for s in scenarios if s["category"] in categories]
    if per_category is None:
        return scenarios
    seen: dict[str, int] = defaultdict(int)
    picked = []
    for s in scenarios:
        if seen[s["category"]] < per_category:
            picked.append(s)
            seen[s["category"]] += 1
    return picked


async def _warm_up() -> None:
    """Exercise both model endpoints before timed runs. Small GPUs may swap
    models, so this does not guarantee simultaneous residency or remove all
    subsequent model-loading costs."""
    if settings.MOCK_LLM:
        return
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    await chat_json(purpose="warmup", model=settings.AGENT_MODEL, system="Reply with JSON.", user="ok", schema=schema, num_predict=8)
    if settings.GUARD_BACKEND.startswith("llama_guard"):
        from firewall.guardian_llm import judge
        await judge("Do you have oat milk?")
    else:
        model = settings.GUARD_MODEL
        await chat_json(purpose="guardian", model=model, system="Reply with JSON.", user="ok", schema=schema, num_predict=8)


async def benchmark(args) -> None:
    pool = {"main": build_scenarios, "heldout": build_heldout,
            "all": lambda: build_scenarios() + build_heldout()}[args.set]()
    scenarios = _select(pool, args.per_category, set(args.categories.split(",")) if args.categories else None)
    by_id = {s["id"]: s for s in scenarios}
    layers = {x.strip() for x in args.layers.split(",")} if args.layers else None
    modes = args.modes.split(",")
    RESULTS.mkdir(exist_ok=True)
    raw_path = RESULTS / f"raw_{args.tag}.json"
    rows: list[dict] = []

    await _warm_up()
    # Modes are interleaved per scenario, with the order rotated each time, so
    # GPU warm-up, thermal drift and cache state affect every mode equally
    # instead of whichever mode happens to run first or last.
    for i, scn in enumerate(scenarios):
        for mode in modes[i % len(modes):] + modes[:i % len(modes)]:
            row = await run_scenario(scn, mode, parallel=not args.sequential, layers=layers)
            rows.append(row)
            raw_path.write_text(json.dumps(rows, indent=1, default=str))
            if not args.quiet:
                console.print(f"[{mode}] {scn['id']:<18} {row['status']:<9} llm={row['llm_calls']:<3} "
                              f"iter={row['iterations']} acts={len(row['executed'])} held={len(row['held'])} "
                              f"{row['wall_ms']:.0f}ms {row['kill_reason']}")

    summary = summarize(rows, by_id)
    (RESULTS / f"summary_{args.tag}.json").write_text(json.dumps(summary, indent=1, default=str))

    table = Table(title=f"Social-media workflow: {args.tag} "
                        f"({'sequential' if args.sequential else 'parallel'} guard, layers={sorted(layers or settings.layers)})")
    for col in ("Mode", "ASR", "CSS", "ST", "Benign wall", "LT", "LLM calls/attack", "Benign killed/held"):
        table.add_column(col)
    for mode, m in summary.items():
        table.add_row(mode, f"{m['ASR']:.1%}", f"{m['CSS']:.1%}", f"{m.get('ST', 0):+.1%}",
                      f"{m['avg_wall_ms_benign']:.0f}ms", f"{m.get('LT_benign_pct', 0):+.0f}%",
                      f"{m['avg_llm_calls_attack']:.1f}", f"{m['benign_killed']}/{m['benign_held']}")
    console.print(table)
    for mode, m in summary.items():
        console.print(f"{mode:<11} ASR by category: " + ", ".join(f"{k}={v:.0%}" for k, v in m["ASR_by_category"].items()))


async def single(args) -> None:
    scn = build_scenarios()[0]
    scn["event"]["text"] = args.text
    row = await run_scenario(scn, args.modes.split(",")[0], parallel=not args.sequential)
    console.print_json(json.dumps(row, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description="Semantic firewall for a social-media management agent workflow")
    p.add_argument("--mode", choices=["benchmark", "single"], default="benchmark")
    p.add_argument("--modes", default=",".join(MODES), help="comma list of: baseline,in_context,firewall")
    p.add_argument("--per-category", type=int, default=None, help="cap scenarios per category")
    p.add_argument("--categories", default=None, help="comma list of scenario categories to include")
    p.add_argument("--sequential", action="store_true", help="legacy scheduling option; all ingress is gated in either schedule")
    p.add_argument("--layers", default=None, help="firewall layers: detector,judge,watch,egress")
    p.add_argument("--set", choices=["main", "heldout", "all"], default="main", help="scenario set")
    p.add_argument("--tag", default="run")
    p.add_argument("--text", default="Do you have oat milk?", help="--mode single: comment text")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    asyncio.run(benchmark(args) if args.mode == "benchmark" else single(args))


if __name__ == "__main__":
    main()
