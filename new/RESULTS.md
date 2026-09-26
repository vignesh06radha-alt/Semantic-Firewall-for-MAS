# Benchmark results -- 2026-09-26

Full real run: 200 items (50 each Clean / ComplexBenign / Toxic / IPI_DoS) x
3 configurations. **No mocking** -- `GUARD_MODEL=llama-guard3:8b` and
`AGENT_MODEL=llama3.2:3b`, both real Ollama calls, for all 600 pipeline
invocations. Raw data: [`results/raw_results_n200.json`](results/raw_results_n200.json)
(gitignored -- regenerate with `python run_benchmark.py`); this file is the
committed writeup, same convention as
[`../mas_security_firewall/evaluation/results/`](../mas_security_firewall/evaluation/results/).

## Headline metrics

| Config | ASR ↓ | CSS ↑ | ST | LT | avg latency |
|---|---|---|---|---|---|
| `baseline_a` (undefended) | 86.0% | 86.0% | -- | -- | 2,537ms |
| `baseline_b` (vaccinated) | 48.0% | 80.0% | +7.0% | +59.0% | 4,033ms |
| `proposed` (ASGI firewall) | **30.0%** | **86.0%** | **+0.0%** | +482.1% | 14,767ms |

This reproduces the Peigné et al. finding this project exists to test: the
out-of-band firewall gets **both** the lowest attack success rate **and**
zero measurable cooperation tax (`proposed`'s CSS exactly matches the
undefended baseline's, because Policy Evaluator's prompt is byte-identical
between the two). The in-context "vaccination" defense (`baseline_b`) buys
less robustness (48% ASR vs. 30%) while still taxing cooperation (80% vs.
86% CSS) -- worse on both axes than pushing the defense out-of-band.

## The latency number needs a hardware caveat

+482% is real, but it is **not** a property of "ASGI middleware firewalls"
in general -- it's this machine's GPU having 6GB VRAM, too little to hold
`GUARD_MODEL` (4.9GB) and `AGENT_MODEL` (2GB) resident at once. Every
`proposed`-config item that passes the firewall forces Ollama to evict and
reload one model for the other (see the `config.py`/`ollama_client.py`
commit history in this repo for how this was diagnosed -- it first showed up
as *every single item, including obviously benign ones, timing out and
getting blocked*, which was the tell that this was a reload artifact, not a
real classification). On hardware that can hold both models at once (or a
real deployment using separate inference endpoints per model, which is the
realistic production setup anyway), the latency tax would be closer to just
the guard model's own inference time layered onto the pipeline -- a few
seconds, not 5x. Take the *ordering* (proposed > vaccinated > undefended) as
real; don't cite the exact +482.1% outside this specific machine.

## Zero false positives at the ingress layer

```
proposed, blocked-at-ingress rate by category:
  Clean:          0/50 (0%)
  ComplexBenign:  0/50 (0%)
  Toxic:         22/50 (44%)
  IPI_DoS:       33/50 (66%)
```

This is *why* ST is exactly 0%: the firewall never blocks Clean or
ComplexBenign content, so every complex-benign item that reaches Policy
Evaluator under `proposed` gets the exact same judgment it would have gotten
under `baseline_a` -- CSS is identical because the input to the agent is
identical. The Security Tax isn't just low, it's structurally zero for this
run: nothing about "proposed" changes what a benign item's journey through
the pipeline looks like unless the firewall actually blocks it, and it never
did for these two categories, in 100 attempts.

## The firewall isn't IPI/DoS-selective -- it's a general safety gate

`GUARD_TASK_PROMPT` explicitly asks the classifier to look for injection/DoS
patterns, not general content policy. It blocks 44% of Toxic posts anyway.
This is the same finding [`../mas_security_firewall`](../mas_security_firewall)
already documented for `Llama-Guard-3-1B`: an off-the-shelf safety
classifier's own trained taxonomy leaks through regardless of how the task
prompt frames the request. Arguably a feature for a real moderation
service (catching obvious toxicity at the perimeter for free), but it means
the firewall's block rate is not a clean measurement of IPI/DoS detection
alone -- the IPI_DoS-category numbers below are the ones that isolate that.

## Attack breakdown (IPI_DoS category, 50 items, 25 force_allow / 25 induce_loop)

Attack success rate by `payload_goal`:

| Config | force_allow | induce_loop |
|---|---|---|
| baseline_a | 88% | 84% |
| baseline_b | 36% | 60% |
| proposed | 36% | **24%** |

The firewall is markedly better against loop-inducing payloads than
verdict-hijacking ones -- "re-run this evaluation" / "resend to Ingestion"
phrasing is apparently more distinctive to the guard model than
administrative-sounding hijack text ("Trust & Safety", "SYSTEM OVERRIDE").
`baseline_b` and `proposed` tie exactly on `force_allow` (36%); the
firewall's advantage over vaccination shows up entirely on the loop class.

Attack success rate by obfuscation vector (`proposed` only, 10 items/vector):

| Vector | baseline_a | proposed | Catch rate |
|---|---|---|---|
| ocr_embedded | 80% | **0%** | 100% caught |
| delimiter_breakout | 90% | 30% | 67% caught |
| authority_spoof | 90% | 40% | 56% caught |
| plain | 80% | 20% | 75% caught |
| base64 | 90% | **60%** | 33% caught -- weakest |

Base64-wrapped payloads are the firewall's weakest spot by a clear margin,
even though `sandbox.py::surface_base64` does decode and annotate them
before classification (see the ingestion-side version of this same gap,
fixed earlier this session). OCR-embedded payloads -- text arriving via a
separate field with no surrounding "cover" content -- are caught 100% of
the time, plausibly because an isolated instruction-shaped string has
nothing else in the payload to look legitimate next to.

## Mock vs real

This entire run used real models throughout -- both toggles
(`MOCK_AGENTS`, `MOCK_FIREWALL`) were off, and all 600 pipeline invocations
(0 transport errors) hit actual Ollama inference. `tests/test_smoke.py` is
still mock-only and exists purely to validate wiring for free; it was not
used to produce any number in this file.
