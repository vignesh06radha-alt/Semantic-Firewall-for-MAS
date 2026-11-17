"""Matched security-tax study over local simulated effects; no paid APIs."""
import argparse
import asyncio
from collections import Counter
import json
import hashlib
from pathlib import Path
from statistics import mean, median
import time

from config.settings import settings
from datasets.agentdojo_social import build_agentdojo_social
from datasets.heldout import build_heldout
from datasets.scenarios import build_scenarios
from datasets.public_social import build_public_social
from datasets.workflow_security import build_workflow_security
from evaluation.metrics import adaptive_succeeded, benign_completed, security_violations
from evaluation.report import wilson
from evaluation.runner import MODES, run_scenario

BOUNDARY_MODE = "secure_boundary"


def summarize_study(rows, scenarios):
    summary = {}
    for mode in dict.fromkeys(r["mode"] for r in rows):
        group = [r for r in rows if r["mode"] == mode]
        clean = [r for r in group if scenarios[r["id"]]["ground_truth"]["goal"] == "none"]
        attacked = [r for r in group if scenarios[r["id"]]["ground_truth"]["goal"] != "none"]
        successes = sum(adaptive_succeeded(scenarios[r["id"]], r) for r in attacked)
        safe_completed = sum(benign_completed(scenarios[r["id"]], r)
                             and not adaptive_succeeded(scenarios[r["id"]], r)
                             for r in attacked)
        times = sorted(r["wall_ms"] for r in clean)
        summary[mode] = {
            "clean_n": len(clean), "attack_n": len(attacked), "attack_successes": successes,
            "attack_success_rate": successes / len(attacked) if attacked else None,
            "safe_completed_under_attack": safe_completed,
            "utility_under_attack": safe_completed / len(attacked) if attacked else None,
            "cooperation": mean(benign_completed(scenarios[r["id"]], r) for r in clean) if clean else None,
            "robustness": (sum(not adaptive_succeeded(scenarios[r["id"]], r)
                               and r["status"] in {"completed", "denied", "held", "killed"}
                               for r in attacked) / len(attacked)) if attacked else None,
            "attack_success_wilson_95": list(wilson(successes, len(attacked))) if attacked else None,
            "clean_completion": mean(benign_completed(scenarios[r["id"]], r) for r in clean) if clean else None,
            "completion_under_attack": mean(benign_completed(scenarios[r["id"]], r) for r in attacked) if attacked else None,
            "clean_intervention_rate": mean(r["status"] in {"held", "killed", "denied"} for r in clean) if clean else None,
            "clean_latency_median_ms": median(times) if times else None,
            "clean_latency_mean_ms": mean(times) if times else None,
            "clean_latency_p95_ms": times[max(0, (95 * len(times) + 99) // 100 - 1)] if times else None,
            "clean_total_tokens_mean": mean(r["tokens"] + r["guard_tokens"] for r in clean) if clean else None,
            "clean_model_calls_mean": mean(r["llm_calls"] + r["guard_llm_calls"] for r in clean) if clean else None,
            "statuses": dict(Counter(r["status"] for r in group)),
            "effect_violations": dict(Counter(v for r in group for v in security_violations(scenarios[r["id"]], r))),
            "clean_inventory": sorted(r["id"] for r in clean),
        }
    base = summary.get("task_only")
    susceptible = {r["id"] for r in rows if r["mode"] == "task_only"
                   and scenarios[r["id"]]["ground_truth"]["goal"] != "none"
                   and adaptive_succeeded(scenarios[r["id"]], r)}
    for result in summary.values():
        matched = base is not None and result["clean_inventory"] == base["clean_inventory"]
        result["clean_completion_loss_pp"] = ((base["clean_completion"] - result["clean_completion"]) * 100
                                               if matched and base["clean_n"] else None)
        result["latency_change_pct"] = ((result["clean_latency_median_ms"] / base["clean_latency_median_ms"] - 1) * 100
                                         if matched and base["clean_latency_median_ms"] else None)
        result["security_tax"] = ((base["cooperation"] - result["cooperation"]) / base["cooperation"] * 100
                                   if matched and base["cooperation"] else None)
        result["latency_tax"] = ((result["clean_latency_mean_ms"] / base["clean_latency_mean_ms"] - 1) * 100
                                  if matched and base["clean_latency_mean_ms"] else None)
    for mode, result in summary.items():
        cohort = [r for r in rows if r["mode"] == mode and r["id"] in susceptible]
        result["baseline_susceptible_n"] = len(cohort)
        result["attack_success_on_baseline_susceptible"] = (
            mean(adaptive_succeeded(scenarios[r["id"]], r) for r in cohort) if cohort else None)
    return summary


async def run_study(args):
    pool = {"main": build_scenarios, "heldout": build_heldout, "agentdojo": build_agentdojo_social,
            "public": lambda: build_public_social(split=getattr(args, "split", "test")),
            "workflow": lambda: build_workflow_security(getattr(args, "split", "test"))}[args.dataset]()
    if args.limit:
        clean = [s for s in pool if s["ground_truth"]["goal"] == "none"][:args.limit]
        attacks = [s for s in pool if s["ground_truth"]["goal"] != "none"][:args.limit]
        pool = clean + attacks
    by_id = {s["id"]: s for s in pool}
    modes = args.modes.split(",")
    if len(set(modes)) != len(modes) or any(m not in (*MODES, BOUNDARY_MODE) for m in modes):
        raise ValueError("Choose distinct known modes")
    if set(modes) & {"baseline", "in_context", "firewall"} and set(modes) & {"task_only", "prompt_guard", "secure", BOUNDARY_MODE}:
        raise ValueError("Do not mix legacy private-context and public-context conditions in a matched study")
    if BOUNDARY_MODE in modes and (args.no_semantic or "judge" not in settings.layers):
        raise ValueError("Boundary screening requires the semantic judge")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as f:
        f.write("{}")
    rows = []
    root = Path(__file__).resolve().parents[1]
    source_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for folder in ("agents", "core", "security", "firewall", "graph", "llm", "socialapi", "datasets", "evaluation")
                     for p in (root / folder).glob("*.py")}
    result = {"protocol": "matched_social_tax_v2", "evidence": "mock" if settings.MOCK_LLM else "live",
              "source_hashes": source_hashes,
              "agent_model": settings.AGENT_MODEL, "guard_model": settings.GUARD_MODEL,
              "metric_units": {"attack_success_rate": "fraction", "cooperation": "fraction", "robustness": "fraction",
                               "utility_under_attack": "fraction",
                               "security_tax": "percent relative cooperation loss", "latency_tax": "percent relative mean clean latency increase"},
              "dataset": args.dataset, "split": args.split, "limit_per_group": args.limit,
              "semantics_disabled": args.no_semantic,
              "scenarios": pool, "rows": rows,
              "limitations": ["Static cases; adaptive campaigns are separate", "Small samples do not establish universal robustness",
                              "Reply utility checks destination and completion, not all factual or content quality"]}
    def save():
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(output)
    for i, scn in enumerate(pool):
        for mode in modes[i % len(modes):] + modes[:i % len(modes)]:
            if any(hashlib.sha256((root / name).read_bytes()).hexdigest() != digest
                   for name, digest in source_hashes.items()):
                result["invalidated"] = "source_changed"
                save()
                raise RuntimeError("Source changed during the study")
            if mode == BOUNDARY_MODE:
                row = await run_scenario(scn, "secure", handoff_judge=False)
                row["mode"] = mode
            else:
                row = await run_scenario(scn, mode, layers=set() if args.no_semantic and mode == "secure" else None,
                                         handoff_judge=True if mode == "secure" and BOUNDARY_MODE in modes else None)
            rows.append(row)
            save()
            print(f"{scn['id']} {mode}: {row['status']}", flush=True)
    result["summary"] = summarize_study(rows, by_id)
    result["completed"] = True
    save()
    def percent(value):
        return "—" if value is None else f"{value * 100:.1f}%"

    report = ["# Matched social security study", "",
              f"{result['evidence'].title()} evidence on the {args.dataset} dataset ({args.split}).", "",
              "| Mode | Harmful outcomes | Wilson 95% upper bound | Clean completion | Clean intervention | Safe completion under attack | Median clean latency change | Errors |",
              "|---|---|---|---|---|---|---|---|"]
    for mode, item in result["summary"].items():
        interval = item["attack_success_wilson_95"]
        latency = item["latency_change_pct"]
        report.append(f"| {mode} | {item['attack_successes']}/{item['attack_n']} | "
                      f"{percent(interval[1] if interval else None)} | {percent(item['cooperation'])} | "
                      f"{percent(item['clean_intervention_rate'])} | "
                      f"{item['safe_completed_under_attack']}/{item['attack_n']} | "
                      f"{'—' if latency is None else f'{latency:+.1f}%'} | {item['statuses'].get('error', 0)} |")
    report += ["", *result["limitations"]]
    output.with_suffix(".md").write_text("\n".join(report), encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", choices=["main", "heldout", "agentdojo", "public", "workflow"], default="agentdojo")
    p.add_argument("--split", choices=["development", "validation", "test"], default="test")
    p.add_argument("--modes", default="task_only,prompt_guard,secure",
                   help="comma-separated modes, including secure_boundary for the handoff-judge ablation")
    p.add_argument("--limit", type=int, default=0, help="cap clean and attacked cases separately; zero means all")
    p.add_argument("--no-semantic", action="store_true", help="secure-mode structural ablation")
    p.add_argument("--output", default=f"results/study_{time.time_ns()}.json")
    args = p.parse_args()
    if args.limit < 0:
        p.error("limit cannot be negative")
    asyncio.run(run_study(args))


if __name__ == "__main__":
    main()
