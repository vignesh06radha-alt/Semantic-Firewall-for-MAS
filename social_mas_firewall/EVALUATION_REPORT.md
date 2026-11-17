# Semantic firewall evaluation

11 November 2026, Dubai time. The workflow evaluation is complete. The external corpus figures are a snapshot of a running evaluation.

The firewall recorded **0 successful attacks in 114 workflow attack and hazard cases**, compared with 35 without protection and 24 with prompt-only protection. It completed the legitimate task safely in **12 of 114 attacked cases**, intervened on **11 of 120 clean cases**, and added **80.3% median clean-task latency**. The held-out split shows the same trade-off.

## Run types and denominators

| Run type | What it measures | Evidence |
|---|---|---|
| Regression tests and mock studies | Permission enforcement, scoring, checkpoints, and report generation with controlled outputs | 74 regression tests passed in the final review. Mock scores describe fixture behavior. |
| Live pilots | Whether the local model and simulation work together, and where early failures occur | Two small matched static studies and separate adaptive pilots |
| Bounded security review | Development profile comparison, validation, held-out pilot, and one adaptive campaign | 44 static runs and 10 adaptive attempts |
| Full workflow study | Performance on social-media tasks and hazards designed for this application | 234 cases per approach and 702 completed live runs |
| External transfer study | Performance on research attack texts transplanted into the social workflow | 6,054 attack inputs and 40 clean controls per approach. 1,563 of 18,282 runs saved at this snapshot. |
| Adaptive campaigns | Whether feedback-guided revisions find a harmful outcome against a fixed defense | Three completed pilot campaigns. The full batch queues 18 further campaigns with up to 25 attempts each. |

All live studies use real local model inference with simulated social reads and writes. A **case** is one scenario. A **run** is one execution of that case under one approach. Each full workflow case ran once with each of the following configurations.

- **Unprotected** (`task_only`) uses the task prompt without the external firewall.
- **Prompt-only** (`prompt_guard`) adds security instructions to that task prompt.
- **Firewall** (`secure`) applies external screening, task permissions, provenance checks, resource limits, and output checks.

| Workflow split | Clean per approach | Attack or hazard per approach | Cases per approach | Runs across three approaches |
|---|---:|---:|---:|---:|
| Development | 76 | 70 | 146 | 438 |
| Validation | 12 | 8 | 20 | 60 |
| Held-out test | 32 | 36 | 68 | 204 |
| **Total** | **120** | **114** | **234** | **702** |

The 114 attack-labelled cases include 110 injection placements and four loop hazards. Repeated placements and related texts share some underlying behavior, so case counts can exceed the number of distinct prompts. The external corpus comprises 1,054 InjecAgent inputs and 5,000 LLMail-Inject inputs adapted to this workflow.

## Completed live workflow results

All three saved split summaries were reproduced from their raw rows. The held-out split is the primary comparison. The pooled results describe coverage across the complete workflow dataset.

| Held-out metric | Unprotected | Prompt-only | Firewall |
|---|---:|---:|---:|
| Attack success rate | 13/36 (36.1%) | 8/36 (22.2%) | 0/36 (0%) |
| Clean-task completion | 30/32 (93.8%) | 32/32 (100%) | 30/32 (93.8%) |
| Clean-task interventions | 0/32 | 0/32 | 2/32 (6.3%) |
| Robustness | 23/36 (63.9%) | 28/36 (77.8%) | 36/36 (100%) |
| Utility under attack | 23/36 (63.9%) | 28/36 (77.8%) | 4/36 (11.1%) |
| Untargeted attack success rate | 36.1% | 22.2% | 88.9% |
| Security tax | Reference | −6.7% | 0.0% |
| Mean latency tax | Reference | −11.3% | +67.7% |
| Median clean-task time | 4.62 s | 4.51 s | 8.38 s |
| Median latency tax | Reference | −2.4% | +81.2% |

The firewall prevented scored harm on all 13 held-out cases that succeeded without protection. Prompt-only protection allowed 8 of those 13 to succeed. The firewall's 32 attacked runs without useful completion ended in 27 kills, three holds, and two denials. Clean cooperation was identical for the firewall and unprotected condition, though their failure mechanisms differed.

| Pooled metric across all workflow splits | Unprotected | Prompt-only | Firewall |
|---|---:|---:|---:|
| Attack success rate | 35/114 (30.7%) | 24/114 (21.1%) | 0/114 (0%) |
| Clean-task completion | 117/120 (97.5%) | 120/120 (100%) | 109/120 (90.8%) |
| Robustness | 69.3% | 78.9% | 100% |
| Utility under attack | 79/114 (69.3%) | 90/114 (78.9%) | 12/114 (10.5%) |
| Untargeted attack success rate | 30.7% | 21.1% | 89.5% |
| Clean-task interventions | 0/120 | 0/120 | 11/120 (9.2%) |
| Security tax | Reference | −2.6% | +6.8% |
| Mean latency tax | Reference | −15.4% | +71.2% |
| Median clean-task time | 4.58 s | 3.93 s | 8.25 s |
| Median latency tax | Reference | −14.2% | +80.3% |

| Split | Attack successes U / P / F | Clean tasks completed U / P / F | Safe completion during attack U / P / F | Firewall median latency tax |
|---|---|---|---|---:|
| Development | 19 / 15 / 0 of 70 | 75 / 76 / 67 of 76 | 51 / 55 / 7 of 70 | +78.2% |
| Validation | 3 / 1 / 0 of 8 | 12 / 12 / 12 of 12 | 5 / 7 / 1 of 8 | +84.7% |
| Held-out test | 13 / 8 / 0 of 36 | 30 / 32 / 30 of 32 | 23 / 28 / 4 of 36 | +81.2% |

U is unprotected, P is prompt-only, and F is firewall. Across the workflow suite, the firewall prevented scored harm in all 35 cases that succeeded unprotected. Prompt-only protection allowed 19 of those 35 to succeed and had five additional successes elsewhere.

## External corpus snapshot

The saved checkpoint contains **1,563 live runs**, or **8.5%** of the planned 18,282. All three approaches have results for 521 cases comprising 481 attacks and 40 clean controls.

| Metric on matched cases | Unprotected | Prompt-only | Firewall |
|---|---:|---:|---:|
| Attack success rate | 26/481 (5.4%) | 1/481 (0.2%) | 0/481 (0%) |
| Clean-task completion | 39/40 (97.5%) | 40/40 (100%) | 35/40 (87.5%) |
| Robustness | 94.6% | 99.8% | 100% |
| Utility under attack | 455/481 (94.6%) | 479/481 (99.6%) | 434/481 (90.2%) |
| Untargeted attack success rate | 5.4% | 0.4% | 9.8% |
| Clean-task interventions | 0/40 | 0/40 | 5/40 (12.5%) |
| Security tax | Reference | −2.6% | +10.3% |
| Mean latency tax | Reference | −18.0% | +69.8% |
| Median latency tax | Reference | −19.6% | +71.7% |

Both defenses prevented scored harm on the 26 cases that succeeded without protection. The prompt-only success occurred outside those 26. The 455 cases that already produced no scored harm when unprotected account for most of the firewall's low overall ASR. These transferred prompts provide breadth, while the workflow suite better exposes the cost of defending relevant tasks. The earlier interrupted transfer batch saved 1,129 runs with an older implementation. Its 336 unprotected and 336 firewall attack rows recorded 16 and six successes, respectively. Prompt-only recorded 0/337. The older code had a connector permission bypass, so those rows remain historical evidence.

## Adaptive and diagnostic evidence

In an adaptive campaign, a separate model proposes a test input, receives outcome feedback, and revises its input. Every attempt starts with fresh simulated state. The defense stays fixed throughout the campaign. Successful candidates receive fresh-run confirmations.

| Completed adaptive pilot | Attempts | Distinct candidate texts | Successes | Target errors |
|---|---:|---:|---:|---:|
| First live pilot | 3 | 2 | 0 | 0 |
| Second live pilot | 10 | 3 | 0 | 0 |
| Security review outlier campaign | 10 | 4 | 0 | 0 |

Candidate uniqueness is measured within each campaign. The three campaigns used small local models and repeated candidate texts. The verified-failure memory remained empty in the bounded review because no qualifying development failure occurred. The batch's 18 scheduled campaigns were pending at this snapshot, and generalized defender learning remains unverified.

| Earlier diagnostic run | Observed result |
|---|---|
| First matched live pilot, one clean and one attacked case per approach | Attack successes 1/1, 0/1, 0/1 in U/P/F order. All clean tasks completed. Median clean time 7.06 s, 5.91 s, and 14.65 s. |
| Second matched live pilot, two clean and two attacked cases per approach | Attack successes 2/2, 0/2, 0/2. Clean completion 2/2, 2/2, 1/2. Firewall median latency tax +178.6%. |
| Review development pilot, 18 live runs | Each approach recorded 0/3 successes. Full and boundary screening both completed 2/3 clean tasks. Median clean time was 7.97 s unprotected, 16.65 s full screening, and 9.47 s boundary screening. |
| Review validation pilot, 10 live runs | Unprotected 1/2 attack successes, full screening 0/2. Both completed 3/3 clean cases. Firewall median latency tax +117.3%. |
| Review held-out pilot, 16 live runs | Unprotected 2/4 attack successes, full screening 0/4. Both completed 4/4 clean cases. Firewall completed 1/4 tasks safely under attack and added 102.3% median latency. |
| Legacy mock simulation, 126 cases per approach | Attack successes 52/66 baseline, 0/66 in-context, 6/66 firewall. Clean completion 60/60, 26/60, 58/60 under the legacy scorer. |
| Legacy mock scoring validation, 12 cases per approach | Attack successes 7/9 baseline, 0/9 in-context, 0/9 firewall. Clean completion 3/3, 2/3, 3/3. |
| Matched adapted AgentDojo mock studies, nine cases per approach | Attack successes 6/6 unprotected, 0/6 prompt-only, 0/6 firewall. The UA verification mock reported zero safe completions under attack for all three. |
| External mock pilot, four cases per approach | All approaches scored 0/2 attack successes. Clean completion was 2/2 unprotected, 0/2 prompt-only, and 2/2 firewall. |

The legacy runs used different defense modes and scoring. The bounded review also tested an experimental boundary profile. These observations describe development history and use their original denominators.

## Metrics and how to use them

| Metric | Calculation | What it answers |
|---|---|---|
| Attack success rate (ASR) | Scored attacker goals or forbidden effects ÷ attacked cases | How often did measurable harm occur? A later stop still counts an earlier harmful effect. |
| Cooperation or benign utility | Correctly completed clean tasks ÷ clean cases | How often did normal work succeed? |
| Clean intervention rate | Clean runs held, killed, or denied ÷ clean cases | How often did enforcement interrupt benign work? Other errors can also reduce cooperation. |
| Robustness | Attacked cases with no scored success and a completed or enforced-stop outcome ÷ attacked cases | How often did the run avoid harm with a valid outcome? A safe stop earns credit. |
| Utility under attack (UA) | Safely completed legitimate tasks ÷ attacked cases | How often did useful work continue safely? A stop earns zero. |
| Untargeted ASR | 100% minus UA | How often did an attack case end without safe task completion? This includes defense-induced disruption. |
| ASR on baseline-susceptible cases | Defended successes on cases that succeeded unprotected ÷ cases that succeeded unprotected | Does protection help on cases that demonstrated a harmful effect in the baseline? |
| Security tax | 100 × (baseline cooperation − defended cooperation) ÷ baseline cooperation | Relative clean-task completion loss. A negative result indicates improvement in that run. |
| Mean or median latency tax | 100 × (defended latency ÷ baseline latency − 1), using the same statistic on matched clean cases | How much slower was the defended workflow? The existing `latency_tax` field uses means. |
| Tail latency, model calls, and tokens | 95th-percentile clean duration and counts including guardian calls | What do slow cases and additional inference cost? |
| Adaptive campaign success and diversity | Successful campaigns ÷ completed campaigns, alongside attempts, distinct texts, errors, and confirmations | How much search was tested, and did the resulting failures reproduce? |

AgentDojo publishes UA and its complement, untargeted ASR. The held-out firewall's 88.9% untargeted ASR means 32 of 36 attacked tasks failed to finish safely. The scoring uses this application's local checks and simulated tool effects. [AgentDojo, Section 3.4](https://arxiv.org/html/2406.13352#S3.SS4)

## Interpretation and acceptance

The held-out firewall prevented more scored harm than prompt-only protection. It completed far fewer tasks under attack and took about 1.81 times as long on clean tasks as the unprotected workflow. Prompt-only protection preserved clean and attacked utility while allowing eight held-out attacks to succeed.

The held-out 0/36 ASR has a nominal 95% Wilson upper bound of **9.6%**. Across all workflow splits the corresponding upper bound for 0/114 is **3.3%**. The intervals assume independent cases, and related variants can weaken that assumption. The data therefore leave the agreed **≤1% ASR** target unverified. The held-out **6.3% clean intervention rate** exceeds the **≤1%** target, and **+81.2% median latency** exceeds the **≤10%** target. Generalized adaptive learning remains unverified.

The outcome checker measures configured effects, such as unauthorized reads and writes, recipient changes, literal secret markers, and resource limits. It has limited coverage of reply quality and transformed disclosures. Negative latency taxes for prompt-only protection describe observed run timings. One historical attacked run included a long system interruption. The latency comparisons in this document use clean runs.

## Evidence files

- [Held-out workflow report](results/live_study_1794329895461361900.md)
- [Validation workflow report](results/live_study_1794339908734282300.md)
- [Development workflow report](results/live_study_1794340229401919100.md)
- [Full batch progress](results/complete_evaluation_20261110/progress.json) and [external progress](results/complete_evaluation_20261110/public/progress.json)
- [Bounded security review](SECURITY_REVIEW_20261110.md) and [adaptive pilot evidence](results/security_review_20261110/adaptive_outlier.json)
- [Metric definitions](METRICS.md) and [implementation journal](IMPLEMENTATION_JOURNAL.md)
- [Legacy mock simulation](results/report_simulation_20261027.md), [legacy scoring validation](results/report_metrics_validation_20261027.md), and [UA mock report](results/review_utility_under_attack.md)
