"""Builds a markdown results report from results/raw_<tag>.json files.

Run: python -m evaluation.report main_full heldout_full [abl_...] > results_report.md

Beyond the headline table it reports (a) Wilson 95% confidence intervals,
because the sets are small; (b) which firewall layer actually stopped each
attack; and (c) the split between 'the firewall stopped it' and 'the attack
failed on its own' -- an ASR of 0% is not impressive when the baseline agent
would not have fallen for it anyway.
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from datasets.heldout import build_heldout
from datasets.scenarios import ATTACK_CATEGORIES, BENIGN_CATEGORIES, build_scenarios
from evaluation.metrics import attack_succeeded, benign_completed, format_metric, summarize

RESULTS = Path(__file__).parent.parent / "results"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k / n:.0%} ({k}/{n}, CI {lo:.0%}-{hi:.0%})"


def layer_of(row: dict) -> str:
    reason = row["kill_reason"]
    if row["killed"]:
        return reason.split(":")[0] or "killed"
    if row["held"] or row["status"] == "held":
        return "held"
    if row["status"] in ("error", "route_denied"):
        return row["status"]
    return "none"


def load(tag: str) -> list[dict]:
    return json.loads((RESULTS / f"raw_{tag}.json").read_text())


def report(tag: str, scen: dict[str, dict]) -> str:
    rows = load(tag)
    out = [f"### `{tag}`\n"]
    modes = list(dict.fromkeys(r["mode"] for r in rows))
    summary = summarize(rows, scen)
    out.append("Evidence: " + ", ".join(f"{mode}={m['evidence']}" for mode, m in summary.items()) +
               ". Mock runs measure controlled workflow behavior, not live classifier quality or latency.\n")
    out.append("| Mode | R: neutralized / valid-route attacks | C: completed / all benign | Delta t: mean boundary delay (ms) | Delta c: cooperation loss (pp) |")
    out.append("|---|---|---|---|---|")
    for mode, m in summary.items():
        out.append(f"| {mode} | {pct(m['n_neutralized'], m['n_valid_route_attacks'])} | "
                   f"{pct(m['n_benign_completed'], m['n_benign'])} | "
                   f"{format_metric(m['delta_t_ms'])} (n={m['n_delivered_messages']}) | "
                   f"{format_metric(m['delta_c_pp'])} |")
    out.append("\nR counts confirmed kills before the attack goal succeeds; holds, errors, and natural failures receive no credit. "
               "Denied routes are excluded from its attack denominator. C includes clean and difficult benign cases. "
               "Delta t measures receipt-to-release at delivered message boundaries; it excludes blocked messages and is not total task latency. "
               "Delta c is baseline C minus defended C on matching benign scenario inventories; otherwise n/a.\n")
    out.append("The firewall's intended advantage is fewer successful attacks with high cooperation and acceptable delay. "
               "Compare all four metrics and ASR; these results do not automatically establish superiority.\n")

    out.append("| Mode | ASR | CSS (tricky benign) | CSS clean | benign killed/held | spurious publish/DM | LLM calls / attack | benign wall (median) |")
    out.append("|---|---|---|---|---|---|---|---|")
    for m in modes:
        rs = [r for r in rows if r["mode"] == m]
        att = [r for r in rs if r["category"] in ATTACK_CATEGORIES]
        tricky = [r for r in rs if r["category"] in ("ComplexBenign", "Held_Benign")]
        clean = [r for r in rs if r["category"] == "Clean"]
        benign = tricky + clean
        succ = sum(attack_succeeded(scen[r["id"]], r) for r in att)
        css = sum(benign_completed(scen[r["id"]], r) for r in tricky)
        cln = sum(benign_completed(scen[r["id"]], r) for r in clean)
        spurious = sum(1 for r in benign for a in r["executed"] if a["type"] in ("publish", "dm"))
        out.append(
            f"| {m} | {pct(succ, len(att))} | {pct(css, len(tricky))} | {pct(cln, len(clean)) if clean else 'n/a'} | "
            f"{sum(r['killed'] for r in benign)}/{sum(bool(r['held']) or r['status'] == 'held' for r in benign)} | {spurious} | "
            f"{mean(r['llm_calls'] for r in att):.1f} | {median(r['wall_ms'] for r in benign):.0f} ms |"
            if att and benign else f"| {m} | n/a | | | | | | |")

    fw = [r for r in rows if r["mode"] == "firewall" and r["category"] in ATTACK_CATEGORIES]
    if fw:
        out.append("\n**What stopped each attack (firewall mode).** 'attack failed on its own' = nothing intervened and the attack still did not succeed.\n")
        out.append("| Category | detector | judge | watch | egress | other kill | held only | error | route denied | failed on its own | **succeeded** |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        by_cat = defaultdict(list)
        for r in fw:
            by_cat[r["category"]].append(r)
        for cat, rs in sorted(by_cat.items()):
            c = Counter()
            for r in rs:
                layer = layer_of(r)
                if attack_succeeded(scen[r["id"]], r):
                    c["succeeded"] += 1
                elif layer in ("detector", "judge", "watch", "egress"):
                    c[layer] += 1
                elif layer == "held":
                    c["held"] += 1
                elif layer in ("error", "route_denied", "killed"):
                    c[layer] += 1
                elif r["killed"]:
                    c["killed"] += 1
                else:
                    c["own"] += 1
            out.append(f"| {cat} (n={len(rs)}) | {c['detector']} | {c['judge']} | {c['watch']} | {c['egress']} | "
                       f"{c['killed']} | {c['held']} | {c['error']} | {c['route_denied']} | {c['own']} | {c['succeeded']} |")
        tk = [r["t_kill_ms"] for r in fw if r["t_kill_ms"] is not None]
        if tk:
            out.append(f"\nTime to kill: median {median(tk):.0f} ms, max {max(tk):.0f} ms over {len(tk)} kills.")
    return "\n".join(out) + "\n"


def ablation_table(tags: list[str], scen: dict[str, dict]) -> str:
    out = ["| Run | ASR (all attacks) | benign killed/held | LLM calls / attack | benign wall (median) |", "|---|---|---|---|---|"]
    for tag in tags:
        try:
            rows = load(tag)
        except FileNotFoundError:
            continue
        att = [r for r in rows if r["category"] in ATTACK_CATEGORIES]
        ben = [r for r in rows if r["category"] in BENIGN_CATEGORIES]
        succ = sum(attack_succeeded(scen[r["id"]], r) for r in att)
        out.append(f"| `{tag}` | {pct(succ, len(att))} | {sum(r['killed'] for r in ben)}/{sum(bool(r['held']) or r['status'] == 'held' for r in ben)} | "
                   f"{mean(r['llm_calls'] for r in att):.1f} | {median(r['wall_ms'] for r in ben):.0f} ms |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    scen = {s["id"]: s for s in build_scenarios() + build_heldout()}
    tags = sys.argv[1:] or ["main_full", "heldout_full"]
    head = [t for t in tags if not t.startswith("abl_")]
    abl = [t for t in tags if t.startswith("abl_")]
    for t in head:
        print(report(t, scen))
    if abl:
        print("### Ablations (firewall mode, main + held-out sets together)\n")
        print(ablation_table(abl, scen))
