# Verified firewall results, 11 November 2026

All three workflow split summaries were recomputed from the saved live runs and
matched the original summaries. The workflow study completed 702 runs covering
234 cases across three approaches. The held-out split has 32 clean and 36
attacked cases per approach.

| Held-out result | Unprotected | Prompt-only | Firewall |
|---|---:|---:|---:|
| Scored attack successes | 13/36 (36.1%) | 8/36 (22.2%) | 0/36 (0%) |
| Clean-task completion | 30/32 (93.8%) | 32/32 (100%) | 30/32 (93.8%) |
| Safe task completion under attack | 23/36 (63.9%) | 28/36 (77.8%) | 4/36 (11.1%) |
| Untargeted ASR | 13/36 (36.1%) | 8/36 (22.2%) | 32/36 (88.9%) |
| Median clean-task time | 4.62 s | 4.51 s | 8.38 s |

AgentDojo Section 3.4 calls the complement of Utility Under Attack the untargeted
attack success rate. Here it measures how often an attacked run fails to deliver
a safe, completed task under the local scoring rules. The firewall had zero
scored harmful effects on this split, but 32 of 36 attacked runs ended in a stop
or denial. See [AgentDojo Section 3.4](https://arxiv.org/html/2406.13352#S3.SS4).

Across all workflow splits the firewall had 0/114 scored attack successes and
12/114 safe completions under attack, giving an untargeted ASR of 89.5%. It
intervened on 11/120 clean cases and added 80.3% median clean-task latency.
On the held-out split it intervened on 2/32 clean cases and added 81.2% median
latency. The held-out 0/36 result has a 95% Wilson upper bound of 9.6% under
the usual independent-case assumption, which related attack variants can weaken.
The review does not establish the 1% ASR target, and observed intervention and
latency rates exceed their agreed targets.

The external checkpoint had 1,532/18,282 runs saved. In the 470 attacked cases
with all three approaches recorded, scored successes were 25 unprotected, one
prompt-only, and zero with the firewall. Both defenses had zero successes on
the 25 cases that succeeded unprotected. The remaining external runs and the
batch's adaptive campaigns were pending at this snapshot.
