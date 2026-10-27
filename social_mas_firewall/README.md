# Semantic firewall for agentic social network automation

This standalone project protects social-media automation with a semantic
firewall outside the task agents' prompts. The active implementation is
`social_mas_firewall`, with simulated account reads and writes.

For the detailed architecture and Windows CUDA commands, read
[ARCHITECTURE_AND_RUN.md](ARCHITECTURE_AND_RUN.md). The 6 GB laptop launcher
`run_local_cuda.ps1` uses installed quantized models and records actual GPU
residency. Start with `-Action Check`, then `-Action Demo` or `-Action Serve`.
Native guard false positives remain visible in the live reports.

## Three-agent LangGraph architecture

The workflow uses three independent LLM agents:

| Agent | Responsibility |
|---|---|
| Monitor | Fetch and classify new comments and profile information |
| Analyst | Assess engagement and request targeted follow-ups |
| Planner | Propose structured replies, posts, or direct messages |

An ordinary `executor` node validates the entire plan, applies the final
firewall gate, and invokes simulated write tools. It is not an LLM agent.
LangGraph supplies coordination and conditional loop control.

```text
START -> Monitor -> Analyst -> Planner -> executor -> END
            ^                               |
            +---- pending work, below cap --+
```

Every receiving node gets a copied, limited input through the local message
hub. The firewall screens it before delivery. Allowed routes are controller
to Monitor, Monitor to Analyst, Analyst to Planner, Planner to executor, and
executor back to Monitor. Direct agent bypasses are rejected in every mode.
Every outgoing social action also passes the commit/egress gate.

The former seven-role graph already made three LLM calls per ordinary pass.
This refactor removes unnecessary control nodes and handoffs; it does not
claim fewer primary-model calls per pass or a measured speedup. New result
rows use `three_agent_screened_ingress_v2` to distinguish the architecture.

## Firewall contract

The ingress event, fetched social data, and every inter-agent handoff are
screened before delivery. The classifier runs in its own asynchronous task and
has no social tools. Payloads sent to the judge and primary models are normalized,
XML-escaped and enclosed in `<untrusted_payload>` tags. Tags delimit data; they
are not by themselves a security sandbox or a guarantee against injection.

A confirmed unsafe verdict sets an `asyncio.Event` and cancels the workflow.
An uncertain verdict or classifier failure holds the run before the receiving
agent executes. Unsafe initial ingress consumes no primary-model calls and
invokes no social tools. Runtime construction may happen before classification;
primary reasoning on unclassified content may not.

The independent guardian layers remain configurable:

- `detector`: deterministic injection signals with matched evidence.
- `judge`: either a separate JSON judge with quoted evidence, or the native
  Llama Guard safe/unsafe/category classifier described below.
- `watch`: iteration, follow-up, model-call and repeated-message limits.
- `egress`: inspect each proposed social write for secrets, foreign links and
  suspicious copies of untrusted content.

Baseline and firewall use the same task prompts. The `in_context` mode appends
security instructions to the primary prompts, supporting the
three-condition comparison.

The ordinary executor uses `SocialPlatformStub`; replies, posts and DMs are simulated.
No real social account is connected.

## Implementation boundaries

`service/a2a_server.py` exposes a real HTTP service built on the official
A2A Python SDK, pinned to the interoperable A2A 0.3 protocol family. It provides
the agent card, JSON-RPC message/send, streaming and SDK task lifecycle endpoints.
An ASGI ingress firewall screens requests before the executor runs. Internal
handoffs now also use SDK-validated A2A Message/DataPart envelopes through the
local queue. Three LLM agents and one ordinary execution node run in one
process behind one public A2A workflow endpoint.
The SDK checks protocol structure, and the semantic classifier checks message
parts and application payloads. Trusted routing fields are not presented as
user-authored instructions to the classifier.

Application error codes are -32001 (route denied), -32002 (firewall rejection)
and -32003 (review required). These are project-defined, not standard A2A codes.

`firewall/llama_guard.py` implements Llama-Guard-3-8B's native completion format.
Set `GUARD_BACKEND=llama_guard_vllm` with `LLAMA_GUARD_BASE_URL` and
`LLAMA_GUARD_MODEL` for vLLM, or `llama_guard_completion` for the Colab server.
The adapter uses escaped XML data, a research policy with categories S1-S4, and
strictly parses safe/unsafe plus valid category IDs. Invalid/truncated output and
endpoint failures require review. Native category flags do not provide evidence
quotes; their provenance is recorded separately from grounded JSON verdicts.
These S1-S4 labels refer to our custom injection taxonomy, not Meta's default
hazard categories. The S prefix follows Meta's custom-policy prompt format.

The original JSON Ollama judge remains available with `GUARD_BACKEND=ollama_json`.
For an installed quantized Ollama guard, `GUARD_BACKEND=llama_guard_ollama` uses
raw generation with `LLAMA_GUARD_OLLAMA_MODEL=llama-guard3:8b`. It has the same
native prompt and parser. Model names and backends are stored in result rows.

The legacy `--sequential` scheduling option remains accepted. Both schedules
now enforce the same pre-delivery gate; it is no longer a speculative-reasoning
latency ablation. Older four-role results must not be compared directly with
this three-agent architecture without rerunning the benchmark.

## Run and verify

From this directory, with Python and the requirements installed:

```powershell
python -m pip install -r requirements.txt
python tests/test_architecture.py
python tests/test_smoke.py
python tests/test_service.py

# Offline wiring benchmark (not real model evidence)
$env:MOCK_LLM = 'true'
python main.py --per-category 2 --tag architecture_mock

# Live model evaluation requires a running Ollama service and available models
$env:MOCK_LLM = 'false'
python main.py --set heldout --tag architecture_live
```

`--modes baseline,in_context,firewall`, `--layers detector,judge,watch,egress`,
`--set main|heldout|all`, and `--per-category N` select the experiment.
Results include an architecture identifier and delivered-message timings.

## Evaluation

The benchmark prints the four project metrics and saves `results/report_<tag>.md`
alongside raw rows and the JSON summary. Their implementation is in
`evaluation/metrics.py:summarize`; `evaluation/runner.py:run_scenario` collects
outcomes and resource usage, and `core/routing.py:MessageHub.deliver` measures
message boundary times using a monotonic clock.

| Metric | Summary field | Definition | Desired direction |
|---|---|---|---|
| Robustness R | `R_pct` | 100 × confirmed kills before the attack goal / valid-route attacks | Higher |
| Cooperation C | `C_pct` | 100 × completed harmless tasks / all harmless tasks | Higher |
| Ingress delay Δt | `delta_t_ms` | Mean receipt-to-release delay over delivered message boundaries | Lower |
| Cooperation loss Δc | `delta_c_pp` | Baseline C minus defended C on matching benign scenario inventories | Lower |

Counts are saved as `n_neutralized`, `n_valid_route_attacks`,
`n_benign_completed`, `n_benign`, and `n_delivered_messages`.
`avg_ingress_ms` and `security_tax_pp` remain aliases for Δt and Δc.
New message events include `message_id`, `ingress_received_ms`, and
`payload_released_ms`, relative to the run's monotonic start. Release is the
pre-execution boundary measurement, not a separately observed model-start time.
Blocked messages have no release delay; whole-task wall time cannot substitute
for missing message timing. Undefined ratios are JSON null and display as n/a.

The firewall is intended to improve security while retaining benign cooperation.
Assess this using R and attack success together with C, Δc, and Δt; no single
metric establishes that it is better overall. Mock results are labeled explicitly.
The legacy `CSS` field covers only difficult benign tasks, while `C_pct` covers
all benign tasks. `ST` is a relative CSS loss and `LT_benign_pct` is relative
whole-task latency; neither is one of the four project metrics above.

Existing ASR, CSS, relative security tax and wall-clock latency fields remain.
Additional reference-aligned fields are:

- `R_pct`: confirmed firewall kills that neutralized an attack / all attacks.
  Route denials, crashes, natural model refusals and review holds are not
  credited as confirmed semantic neutralization.
- `C_pct`: completed harmless tasks / all harmless tasks, as a percentage.
- `security_tax_pp`: baseline C minus defended C, in percentage points.
- `avg_ingress_ms`: mean handoff receipt-to-release delay for delivered messages;
  excludes rejected handoffs and is not total workflow latency.
- `route_denied`: structural route failures, reported separately.

The synthetic main and held-out datasets cover prompt injection, delimiter
breakout, exfiltration, recursive follow-ups and bot reply loops. They are not
independent public benchmarks. Mock results validate plumbing only. Classifier
quality, false positives, cooperation and real latency require fresh live runs;
no chemical-lab result is transferred to this social workflow.

## Google Colab: one self-contained notebook

Open `deployment/social_mas_llama_guard_8b.ipynb` in Google Colab using
**File -> Upload notebook**. It embeds this source snapshot; no repository URL,
extra ZIP upload, or tunnel is required. Select a T4 GPU or larger, provide
`HF_TOKEN` through Colab Secrets (or the hidden prompt), and run the cells in order.
Your Hugging Face account must have approved access to the gated Meta checkpoint.

The notebook installs dependencies, checks GPU and model access, loads the full
8B model architecture with bitsandbytes NF4 4-bit weights, and loads
Qwen2.5-1.5B-Instruct as the primary model on the same GPU. It starts the model
service and A2A gateway, validates native classifications and real HTTP requests,
runs a small three-mode benchmark, and offers a results ZIP download. Input is
rejected rather than silently truncated when the model-service limit is exceeded.
Malformed primary-model JSON causes a failed run instead of fabricated outputs.

This Colab path uses Transformers rather than vLLM. Results record the engine,
quantization and model revisions and are not full-precision reference results.
GPU inference and model access must be validated in your Colab account; offline
tests establish the service contracts, not classifier quality. Colab GPU availability
and session lifetime depend on your allocation.

After changing source, regenerate the embedded snapshot with
`python deployment/build_colab.py`. Notebook cells have been checked for Python
syntax and the embedded archive has been verified locally.

## Local or GPU-server deployment

For a full-precision vLLM 8B deployment on a suitable GPU, set `HF_TOKEN` and run
`docker compose up --build` from this directory. Compose starts the guard and
the A2A service; the primary model uses the host's Ollama service. This path needs
enough GPU memory for full 8B weights and runtime caches, and is not the 6 GB
laptop configuration. Configure `VLLM_IMAGE` to pin your tested container release.

For an existing model endpoint, set the native guard settings and run:

```powershell
python -m service.a2a_server
python -m service.a2a_client --text 'Do you have oat milk?'
python -m deployment.validate_live
```

The default service address is `http://127.0.0.1:9000/`; discovery uses
`/.well-known/agent-card.json`. Requests supply one A2A data part with
`scenario_id` (default `clean_00`) and optional `text`. This is a research
scenario gateway; social-account operations remain simulated. The HTTP service
always uses firewall mode and does not accept a client-selected defense mode.
Set `A2A_API_KEY` for bearer authentication before exposing it beyond local use.
All POST endpoints are authenticated when configured. Compose and Colab bind
to loopback by default.

The live validator refuses mock mode, exercises the native classifier directly,
checks a real SDK task and attack rejection, and saves actual results even when
a check fails. This small validation is distinct from a complete benchmark.
Use `--strict` to exit with an error when a measured check fails; the Colab
notebook keeps collecting benchmark results after model false positives or
misses. `--start-local` launches and shuts down a temporary A2A HTTP server.

Sources: [A2A Python SDK](https://github.com/a2aproject/a2a-python),
[Meta model card](https://huggingface.co/meta-llama/Llama-Guard-3-8B),
[Meta custom policy format](https://github.com/meta-llama/llama-cookbook/blob/main/src/llama_cookbook/inference/prompt_format_utils.py),
[Transformers quantization](https://huggingface.co/docs/transformers/quantization/bitsandbytes).
