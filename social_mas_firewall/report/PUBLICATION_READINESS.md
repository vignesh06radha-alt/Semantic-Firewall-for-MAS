# Publication readiness assessment

## Research question

Can a task-scoped tool gateway preserve safe task completion while reducing the need for repeated model-based screening in a multi-role workflow? The artifact pairs tool-effect auditing with measurements of clean completion, safe completion under attack, and inference overhead. It evaluates an in-process handoff graph and simulated tools.

Capability-based tool policies and provenance already appear in CaMeL. Multi-CaMeL explicitly preserves the trust distinction across agent boundaries, and SafeFlow studies semantic information flow in team workflows. ARGUS also audits provenance-aware decisions. Treat these as overlapping work. A publishable contribution would require reproducible evidence about when handoff judgments add value over structural controls and what the savings cost in security and utility. [CaMeL](https://arxiv.org/abs/2503.18813) · [Multi-CaMeL](https://arxiv.org/abs/2610.05640) · [SafeFlow](https://arxiv.org/abs/2607.25255) · [ARGUS](https://arxiv.org/abs/2605.03378)

## Threat model and implementation scope

The simulator assumes the workflow process, gateway policy, and simulated connector are trusted. External social text and model-produced proposals are untrusted. The gateway validates the operation, post, and recipient for each effect. It limits model calls and tool use and records runtime-assigned lineage. The public-reply policy derives the allowed post and commenter from the verified fixture event.

An authorized reply can still contain inappropriate text. This is where semantic screening may add protection beyond tool authorization, and why the study measures both effects and safe task completion. The artifact models three roles in one trusted Python process. Generalization to independent agent services, untrusted plugins, real account authorization, and multiple business policies remains open.

## Verified prior evidence

The fixed workflow study comprises 234 scenarios across three conditions and 702 live local runs. In the held-out split, the firewall recorded 0/36 scored harmful outcomes, 4/36 safe task completions under attack, and 2/32 clean interventions. Median clean-task latency was 8.38 seconds versus 4.62 seconds without protection. Across all splits, the firewall recorded 0/114 scored harmful outcomes and 12/114 safe task completions under attack. [Verified results](../results/complete_evaluation_20261110/VERIFIED_RESULTS_20261111.md)

| Desired metric | Held-out observation | Assessment |
|---|---:|---|
| Harmful-effect rate ≤1% | 0/36, nominal two-sided Wilson upper bound 9.6% | Target unestablished |
| Clean intervention rate ≤1% | 2/32 (6.3%) | Exceeds target by 5.3 percentage points |
| Median clean latency overhead ≤10% | +81.2% | Exceeds target by 71.2 percentage points |
| Safe task completion under attack | 4/36 (11.1%) versus 23/36 (63.9%) unprotected | 52.8 percentage points below unprotected |

Prior development evidence used three clean cases per condition. Median clean times were 7.97 s unprotected, 16.65 s under full screening, and 9.47 s under boundary screening. The experimental profile lowered the median versus full screening in that pilot, while remaining above the 10% overhead target. The sample is too small to establish a security or latency improvement on held-out cases. [Evaluation report](../EVALUATION_REPORT.md)

## New matched CUDA smoke run

The RTX 4050 Laptop GPU ran the Q4_K_M `llama3.2:3b` model as both worker and JSON judge. Ollama reported 2.17 GiB of model residency on the GPU. Two clean and two fixed attack scenarios ran in each condition (16 runs). There were no workflow errors. The standalone judge probe missed at least one expected classification.

| Condition | Scored harmful outcomes | Clean completion | Safe completion under attack | Median clean time | Guard calls per clean case |
|---|---:|---:|---:|---:|---:|
| Task only | 1/2 | 2/2 | 1/2 | 4.46 s | 0 |
| Prompt only | 1/2 | 2/2 | 1/2 | 3.38 s | 0 |
| Full firewall | 0/2 | 1/2 | 0/2 | 8.11 s | 6.5 |
| Boundary screening | 0/2 | 1/2 | 0/2 | 4.93 s | 2 |

Boundary screening cut median clean time by 39.2% relative to the full firewall. It still exceeded the task-only median by 10.6%. Both firewall settings denied one clean workflow after it posted a reply and attempted an out-of-scope operation. Both stopped the two attack cases before preserving their legitimate tasks. The next utility experiment should trace optional post-reply operations and evaluate their task necessity while keeping authorization unchanged. The workstation saved the raw smoke run as `results/live_study_1794902669981946500.json`. [Per-run metrics and CUDA evidence](cuda_boundary_pilot.json)

The release checkout then ran 16 additional executions on four validation cases. Boundary screening completed both clean cases and safely completed one of two attacked tasks. Full screening completed both clean cases and neither attacked task safely. Each firewall recorded zero scored harmful effects, as did task-only on this validation sample. Median clean latency was 4.65 s task-only, 8.07 s full firewall, and 5.28 s boundary screening. Boundary screening reduced the full firewall's median by 34.5% and still exceeded task-only by 13.7%. The two validation attack placements share a family. [Validation smoke report](cuda_boundary_validation.md)

## Submission evidence to collect

1. Freeze the code, model digests, quantization, context length, CUDA residency, and split inventory. Compare task-only, prompt-only, full screening, and boundary screening in a paired fixed-case study. Choose the configuration on development and validation. Evaluate on held-out families after choosing the configuration.
2. Report attempted runs, errors, scored harmful effects, safe task completion, clean interventions, median and p95 latency, guard calls, and model tokens. Preserve the raw rows and report clean-task quality beyond destination and completion checks.
3. Cluster intervals by underlying scenario or prompt family, since related placements are correlated. Even with independent trials and zero harmful outcomes, at least 381 trials are needed to place the two-sided 95% Wilson upper bound at or below 1%.
4. Reproduce on a second model family and a shared benchmark under comparable conditions. AgentDojo provides an evaluation protocol and MultiAgentDojo is the closer test for provenance across agent handoffs. Scores from different tasks and threat models cannot support a ranking. [AgentDojo](https://arxiv.org/abs/2406.13352) · [MultiAgentDojo](https://arxiv.org/abs/2610.05640)

The current results support a workshop or artifact discussion about the trade-off. A main-track security or AI submission needs stronger evidence from the matched comparisons above and a threat model whose guarantees follow from the implementation boundaries.
