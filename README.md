# Inline Semantic Firewall for Multi-Agent Systems

An out-of-band security sidecar for a multi-agent system (MAS), built around a
7-agent LangGraph swarm that simulates an automated chemical-synthesis lab
(microwave-assisted MOF synthesis). It reproduces the "Multi-Agent Security
Tax" experiment from Peigné et al. (AAAI 2025): compare an unprotected
baseline, a naive in-context defense, and a decoupled out-of-band firewall
across attack robustness, benign-task cooperation, and latency overhead.

## Architecture

- **`protocols/`** -- JSON-RPC 2.0 message envelope (`A2AMessage`/`A2AMetadata`)
  and a public agent-card endpoint for capability discovery.
- **`firewall/`** -- the sidecar itself:
  - `sanitizer.py` -- Unicode NFKC + homoglyph normalization, zero-width
    stripping, Base64 detection/decoding, and XML delimiter escaping before
    any untrusted content reaches an agent.
  - `corba_guard.py` -- a sliding-window content-hash circuit breaker that
    catches Contagious Recursive Blocking Attacks (polite ping-pong loops
    that look benign hop-by-hop but exhaust compute/tokens).
  - `classifier.py` -- async client for an OpenAI-compatible safety
    classifier (vLLM-hosted Llama Guard, or the dev mock).
  - `sidecar_proxy.py` -- races classification against agent execution
    (`asyncio.create_task`) and trips a kill-switch (`asyncio.Event`) to
    cancel the agent task if the payload is flagged unsafe, fail-closed on
    timeout or classifier error.
- **`graph/`** -- the LangGraph swarm itself (Atlas orchestrator; Bohr/Curie/
  Faraday/Deng specialists; Edison actuation; Gauss compliance audit with a
  refinement loop back to Atlas).
- **`tools/`** -- mock lab hardware actuation (chemical inventory lookup,
  reaction execution with a hazardous-mixture detonation check).
- **`datasets/`** -- attack/benign/CORBA-loop test suites.
- **`evaluation/`** -- the benchmark runner and saved run results.

## Setup

```bash
cd mas_security_firewall
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\Activate.ps1 in PowerShell
pip install -r requirements.txt
cp .env.example .env            # fill in real values -- never commit .env
```

### Classifier backend

The firewall calls out to an OpenAI-compatible `/v1/chat/completions`
endpoint for safety classification. Two options:

**Dev mock** (no GPU needed, keyword-based, for testing wiring only):
```bash
uvicorn dev_mock_classifier:app --port 8000
```

**Real classifier** (`meta-llama/Llama-Guard-3-1B` via vLLM):
1. Accept the Llama 3.2 Community License on the model's HuggingFace page
   and generate a read-scoped access token.
2. Add `HF_TOKEN=hf_...` to `.env`.
3. `docker compose up -d`

Note: the original design targeted `Llama-Guard-3-8B` with AWQ
quantization. There is no valid pre-quantized AWQ build of that model on
HuggingFace, and the unquantized checkpoint needs ~16GB VRAM -- infeasible
on a typical laptop GPU. `Llama-Guard-3-1B` (~3.3GB at fp16) is used instead.
If you hit `RuntimeError: UVA is not available` under Docker Desktop/WSL2,
the compose file already sets `VLLM_WSL2_ENABLE_PIN_MEMORY=1`, which fixes it.

## Running

```bash
python main.py --mode benchmark   # attack/benign/CORBA suites, prints result tables
python main.py --mode single      # one interactive query through the sidecar
python main.py --mode serve       # FastAPI ingress node on --port (default 8080)
```

## Results

See [`evaluation/results/`](evaluation/results/) for saved benchmark runs.

The headline finding so far: the firewall's *architecture* (async race,
kill-switch, sanitizer, CORBA guard) performs as designed against both a
mock and a real classifier. But classifier *accuracy* matters as much as the
architecture -- against the real, un-calibrated `Llama-Guard-3-1B`,
cooperation on benign in-domain requests drops sharply (33.3% vs. 100% with
the mock) because a general-purpose safety taxonomy has no notion that this
is a benign materials-science domain. It flags things like "synthesize
MOF-321 using standard precursors" the same way it would flag an actual
weapons-precursor request. Robustness against real attacks stays at 100% in
both cases. See the results file for the full breakdown.

## Known limitations

- The LangGraph swarm nodes are deterministic stand-ins, not real LLM calls
  (despite `requirements.txt` including `langchain-google-genai` and
  per-agent Gemini API key slots in `config/settings.py` for that purpose).
  Edison's hazard-detection is a keyword/alias check over the message
  transcript (with Base64 decoding), not real language understanding -- it
  approximates what an unprotected LLM agent would plausibly act on.
- The 12-attack / 6-benign suite only maps a few of its categories onto the
  graph's single actuation hazard (TATP detonation); several attack
  categories (exfiltration, impersonation, JSON parameter hijack) have no
  corresponding vulnerable action wired up in this scaffold to "succeed" at.
- Classifier domain mismatch (above) is unresolved by design -- per project
  direction, this was not prompt-engineered around further.
