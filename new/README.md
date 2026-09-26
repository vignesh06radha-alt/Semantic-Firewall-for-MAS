# Ingress Semantic Firewall -- social-media moderation MAS

A third, independent testbed alongside [`../mas_security_firewall`](../mas_security_firewall)
and [`../moderation-mas`](../moderation-mas), reproducing the same
"Multi-Agent Security Tax" finding from Peigné et al. (AAAI 2025) with a
different firewall *placement*: instead of an inter-agent sidecar
(`mas_security_firewall`) or a sequential per-hop gate wired into an
existing graph (`moderation-mas`), this one sits at the HTTP ingress
boundary as ASGI middleware, in front of a 3-agent LangGraph content-
moderation pipeline (Ingestion → Policy Evaluator → Enforcement) modeling a
social network's (e.g. Instagram's) moderation service.

This is defensive security research: the "attacks" here are a synthetic
benchmark dataset used to measure a defense, not a tool aimed at any real
service. See [[project-semantic-firewall]] in project memory for how this
relates to the other two testbeds.

## Architecture

- **`state.py`** -- `ModerationState` TypedDict (`post_id`, `content`,
  `policy_verdict`, `iteration_count`, `latency_ms`, `agent_path`, plus
  bookkeeping fields needed to actually run the benchmark).
- **`agents/`** -- the 3-agent LangGraph pipeline:
  - `ingestion.py` -- parses post text, OCR text, and metadata into one
    normalized view. Deterministic, no LLM call.
  - `policy.py` -- analyzes content against community guidelines (hate
    speech, spam, restricted goods) and decides ALLOW/FLAG/TAKEDOWN. The
    only agent that calls a real model (`AGENT_MODEL` via Ollama) -- see
    "Mock vs real" below for why the other two stay deterministic.
  - `enforcement.py` -- executes the verdict, logs the audit trail, and
    owns the hard cycle-limit check (`iteration_count <= MAX_ITERATIONS`)
    that catches DoS-loop exhaustion.
- **`graph.py`** -- wires the three nodes with a conditional loop-back edge
  from Enforcement to Ingestion, gated by `loop_request`.
- **`sandbox.py`** -- Unicode NFKC + homoglyph normalization, zero-width
  stripping, Base64 surfacing, and XML delimiter escaping (`<untrusted_payload>`)
  before any untrusted text reaches a model.
- **`tagging.py`** -- "LLM Tagging": prefixes every agent-generated message
  with `[AGENT:<name>]` before it's routed onward, so a receiving agent's
  prompt can treat a peer's output as data, never as a new instruction.
- **`ollama_client.py`** -- async client for Ollama's OpenAI-compatible
  `/v1/chat/completions` endpoint: `guard_classify()` for the firewall,
  `agent_complete()` for Policy Evaluator.
- **`firewall/middleware.py`** -- `SemanticFirewallMiddleware`, a pure-ASGI
  (not `BaseHTTPMiddleware`) sidecar that drains the request body, sandboxes
  it, classifies it with the guard model concurrently via `asyncio.create_task`,
  and fails fast with a 403 JSON-RPC error if it's flagged unsafe. Only
  mounted for the `proposed` configuration (see `app.py`).
- **`app.py`** -- `create_app(config_label)` builds one FastAPI instance per
  experimental condition; only `proposed` gets the middleware.
- **`dataset/build_dataset.py`** -- generates the 200-item benchmark
  (50 each of Clean, ComplexBenign, Toxic, IPI_DoS).
- **`benchmark/`** -- `harness.py` drives all 200 items through all three
  configs via `httpx.ASGITransport` (in-process, no real socket needed);
  `metrics.py` computes ASR, CSS, ST, and LT.

## Configurations

| Label | Firewall middleware | Policy Evaluator prompt |
|---|---|---|
| `baseline_a` | absent | pure task prompt |
| `baseline_b` | absent | heavily "vaccinated" (in-context defense) |
| `proposed` | active | pure task prompt (identical to `baseline_a`) |

Comparing `baseline_a` vs `baseline_b` isolates the Security Tax of an
in-context defense. Comparing `baseline_a` vs `proposed` isolates what an
out-of-band firewall buys you (robustness) and costs you (latency) without
also taxing agent cooperation, since `proposed`'s agent prompt is
byte-identical to the undefended baseline's.

## Mock vs real

Two independent toggles (`.env` / `config.py`), because a full 200-item ×
3-config sweep is ~600 Policy Evaluator calls plus ~200 guard-model calls,
and iterating on wiring shouldn't cost that every time:

- **`MOCK_FIREWALL=true`** -- `guard_classify()` becomes a keyword scan
  instead of a real call to `GUARD_MODEL`.
- **`MOCK_AGENTS=true`** -- `policy_node` becomes a keyword-heuristic stand-in
  (`agents/policy.py::_mock_policy`) instead of a real call to `AGENT_MODEL`.

`tests/test_smoke.py` runs with both mocked -- it validates the graph
wiring, the hard cycle cap, and the middleware's block/pass behavior for
free, and is what was used to validate this implementation. **It is not a
substitute for running `run_benchmark.py` with both toggles off** -- keep
this distinction explicit in any reported numbers, the same rule that
applies to the other two testbeds.

This environment has `llama-guard3:8b` and `gemma4:26b` already pulled via
Ollama, so both toggles can be left off for a real run -- no vLLM/Docker/GPU
setup needed here, unlike the other two testbeds' classifier backend.
`gemma4:26b` is a large model to run per-item on non-datacenter hardware;
budget accordingly, or point `AGENT_MODEL` at a smaller pulled model.

## Setup

```bash
cd new
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; .venv\Scripts\Activate.ps1 in PowerShell
pip install -r requirements.txt
cp .env.example .env
ollama serve                    # if not already running
```

## Running

```bash
python tests/test_smoke.py                 # offline, no Ollama needed, ~instant
python dataset/build_dataset.py             # (re)generate dataset/dataset.json
python run_benchmark.py --limit 8           # small real sample against Ollama, all 3 configs
python run_benchmark.py                     # full 200-item x 3-config sweep (slow -- see above)
```

Each run writes `results/raw_results_n<N>.json` (per-item rows, gitignored)
and `results/metrics_n<N>.json` (ASR/CSS/ST/LT per config, gitignored) and
prints a summary table. `results/` is gitignored; see `RESULTS.md` (once a
full real run has been made) for a committed writeup, same convention as
`../mas_security_firewall/evaluation/results/`.

## Design notes / deviations

- **`sandbox.py` is a local copy, not a cross-import** of
  `../mas_security_firewall/firewall/sanitizer.py`, even though the logic is
  identical. This testbed tests a different firewall *placement* (ASGI
  ingress middleware vs. an inter-agent sidecar) and is meant to stand alone
  as one artifact rather than depend on a sibling directory via `sys.path`,
  unlike `moderation-mas/firewall_integration.py`'s deliberate reuse.
- **Ingestion and Enforcement are deterministic, not LLM calls.** The spec
  describes what they do (parse; execute + audit) without requiring either
  to reason over content -- Policy Evaluator is explicitly the "analyzes
  ... against community guidelines" agent, and is the only one whose
  judgment the benchmark's CSS/ST metrics are about. Keeping the other two
  deterministic also keeps the real-call budget for a 200-item sweep to
  ~1 agent call/item instead of ~3.
- **The DoS-loop mechanism is a structured `LOOP_REQUEST` field**, not a
  free-running content-hash loop detector like
  `../mas_security_firewall/firewall/corba_guard.py`. Policy Evaluator's
  output contract (`agent_prompts.py::OUTPUT_CONTRACT`) always includes
  `LOOP_REQUEST: NONE|RERUN`; `induce_loop`-category payloads try to get a
  susceptible model to set `RERUN`, and `enforcement_node` honors it up to
  `MAX_ITERATIONS` before aborting (`status="aborted_dos"`). This makes the
  DoS class something the *agent* can be manipulated into rather than a
  hard-coded property of the graph.
- **ASR for `induce_loop` items is scored as `iteration_count > 1`**, not
  whether the hard cap was hit. The cap is a safety net; the thing being
  measured is whether the injection ever got a single re-run out of the
  model in the first place. See `benchmark/metrics.py::_attack_succeeded`.
- **`force_allow` IPI items use "borderline" cover text** (mildly spammy/
  suspicious, not innocuous) precisely so that ALLOW can only really happen
  *because* the injection worked, not because the underlying post was
  benign anyway.
- **Llama Guard is prompted like a generic chat classifier**
  (`ollama_client.py::GUARD_TASK_PROMPT`), not with Meta's official
  structured Llama-Guard-3 conversation template -- same simplification
  `../mas_security_firewall/firewall/classifier.py` already made against a
  real Llama-Guard-3-1B backend. Ollama's model-specific chat template
  still applies server-side; this hasn't been checked against the official
  template for calibration, only for a safe/unsafe string response.

## Known limitations

- `dataset/dataset.json`'s Toxic/ComplexBenign/Clean banks are templated
  with a handful of slot-fillable variants per category, not 150 fully
  independent hand-written posts -- enough diversity to avoid literal
  duplicates, not a claim of linguistic breadth.
- No results are committed yet -- `results/` only exists once
  `run_benchmark.py` has actually been run against the real models in this
  environment.
