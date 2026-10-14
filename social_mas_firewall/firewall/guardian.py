"""External semantic classification with cancellation and social egress gates.

RunContext awaits screening at each ingress before releasing data to a role.
The legacy parallel flag changes task scheduling only, not this invariant.
Detector, judge, runtime watch and egress remain independently configurable.
"""
import asyncio
import re
import time
from typing import Awaitable, Callable

from config.settings import settings
from core.context import FirewallHeld, FirewallKilled, RunContext
from firewall.detector import Detection, detect
from firewall.guardian_llm import judge
from firewall.loop_guard import LoopGuard
from firewall.sanitizer import normalize_payload
from socialapi.stub import SECRET_PLAN, SECRET_TOKEN

# Egress policy. In a real deployment the guardian is configured with the
# secrets it must protect and the brand's own domains; here that is the same
# fake secret and domain the simulated account uses.
_SECRETS = (SECRET_TOKEN, SECRET_PLAN, "sk-live")
_ALLOWED_HOSTS = ("lumen.coffee",)
_URL_RE = re.compile(r"(?:https?://|hxxps?://|www\.)[^\s'\"<>]+|\b[a-z0-9-]+\.(?:com|net|org|io|co|xyz|ru|info|example)\b", re.I)
_ECHO_WINDOW = 30


class RunGuardian:
    def __init__(self, ctx: RunContext, parallel: bool | None = None, layers: set[str] | None = None):
        self.ctx = ctx
        self.parallel = settings.PARALLEL_GUARD if parallel is None else parallel
        self.layers = settings.layers if layers is None else layers
        self.tasks: list[asyncio.Task] = []
        self.agent_task: asyncio.Task | None = None
        self.kill_reason = ""
        self.t_kill_ms: float | None = None
        self.quarantine_reasons: list[str] = []
        self.events: list[dict] = []
        self.guard_llm_calls = 0
        self.guard_tokens = 0
        # max_repeats=1: the first near-duplicate of an earlier incoming
        # message already counts. A legitimate thread never receives the same
        # message twice; a bot ping-pong does by its second round.
        self._loops = LoopGuard(max_repeats=1)
        self._followups = 0
        self.corpus: list[str] = []  # every untrusted text screened so far

    @property
    def quarantine(self) -> bool:
        return bool(self.quarantine_reasons)

    # ---- kill switch ----
    def trip(self, reason: str, cancel: bool = True) -> None:
        if self.ctx.kill.is_set():
            return
        self.kill_reason = reason
        self.t_kill_ms = (time.perf_counter() - self.ctx.t0) * 1000
        self.ctx.kill.set()
        # `cancel=False` is used when the trip happens inside the agent's own
        # call stack: the agent's next check_alive() raises FirewallKilled.
        if cancel and self.agent_task and not self.agent_task.done():
            self.agent_task.cancel()

    def _hold(self, reason: str) -> None:
        self.quarantine_reasons.append(reason)

    # ---- parallel screening ----
    async def screen(self, source: str, text: str) -> None:
        # Egress echo detection compares external social content, not the
        # agent's own proposed action that was screened at a peer boundary.
        if not source.startswith("message:"):
            self.corpus.append(normalize_payload(text)[0].lower())
        task = asyncio.create_task(self._screen(source, text))
        self.tasks.append(task)
        if not self.parallel:
            await task

    async def _screen(self, source: str, text: str) -> None:
        t0 = time.perf_counter()
        ev: dict = {"source": source, "start_ms": (t0 - self.ctx.t0) * 1000}
        try:
            normalized, flags = normalize_payload(text)
            det = detect(normalized, flags) if "detector" in self.layers else Detection()
            ev["detector"] = det.summary()
            if det.tier == "block":
                self.trip(f"detector:{'+'.join(s.name for s in det.signals[:3])}")
                return
            if det.tier == "suspect":
                self._hold(f"detector-suspect@{source}")

            if "judge" in self.layers:
                res = await judge(normalized)
                self.guard_llm_calls += 1
                self.guard_tokens += res.tokens
                ev["judge"] = f"{res.verdict}:{res.category}:{res.quote[:50]!r}"
                ev["judge_backend"] = res.backend
                ev["native_verdict"] = res.raw_verdict
                if res.verdict == "unsafe":
                    self.trip(f"judge:{res.category}")
                elif res.verdict == "uncertain":
                    self._hold(f"judge-uncertain@{source}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A guardian failure must never silently *permit* side effects,
            # but it also shouldn't destroy benign work: hold, don't kill.
            ev["error"] = type(exc).__name__
            self._hold(f"guard-error@{source}:{type(exc).__name__}")
        finally:
            ev["ms"] = (time.perf_counter() - t0) * 1000
            self.events.append(ev)

    # ---- commit gate ----
    async def commit_gate(self, action: dict | None = None) -> str:
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.ctx.check_alive()
        if action is not None and "egress" in self.layers:
            verdict = self._egress(action)
            if verdict:
                self.events.append({"source": "egress", "detector": verdict})
                if verdict.startswith("secret"):
                    self.trip(f"egress:{verdict}", cancel=False)
                    self.ctx.check_alive()
                return "hold"
        return "hold" if self.quarantine else "ok"

    def _egress(self, action: dict) -> str | None:
        """Output-side check, independent of how the injection was phrased.
        Deterministic and grounded: it only fires on text that is really in
        the outgoing action.
          secret  -> a protected secret is leaving: trip the kill switch
          url     -> a link to a host that is not the brand's own: hold
          echo    -> a publish/DM that repeats >=30 chars of untrusted text
                     verbatim: hold (replies may legitimately quote)"""
        text = str(action.get("text", ""))
        low = text.lower()
        if any(s.lower() in low for s in _SECRETS):
            return "secret_leak"
        for m in _URL_RE.finditer(text):
            if not any(h in m.group(0).lower() for h in _ALLOWED_HOSTS):
                return f"foreign_url:{m.group(0)[:40]}"
        if action.get("type") in ("publish", "dm") and len(low) >= _ECHO_WINDOW:
            for i in range(0, len(low) - _ECHO_WINDOW + 1, 5):
                window = low[i:i + _ECHO_WINDOW]
                if any(window in c for c in self.corpus):
                    return "echo_of_untrusted"
        return None

    # ---- runtime watch (reads the agents' own trace) ----
    def note_llm(self, purpose: str) -> None:
        if "watch" in self.layers and self.ctx.llm_calls > settings.WATCH_MAX_LLM_CALLS:
            self.trip(f"watch:llm_calls>{settings.WATCH_MAX_LLM_CALLS}", cancel=False)

    def note_iteration(self, n: int, incoming_texts: list[str]) -> None:
        if "watch" not in self.layers:
            return
        if n > settings.WATCH_MAX_ITERATIONS:
            self.trip(f"watch:passes>{settings.WATCH_MAX_ITERATIONS}", cancel=False)
            return
        if n > 1:
            for text in incoming_texts:
                if self._loops.observe(self.ctx.run_id, text):
                    self.trip("watch:repeated_incoming_messages", cancel=False)
                    return
        else:
            for text in incoming_texts:
                self._loops.observe(self.ctx.run_id, text)

    def note_followups(self, k: int) -> None:
        self._followups += k
        if "watch" in self.layers and self._followups > settings.WATCH_MAX_FOLLOWUPS:
            self.trip(f"watch:followups>{settings.WATCH_MAX_FOLLOWUPS}", cancel=False)

    # ---- entry point ----
    async def protect(self, event: dict, runner: Callable[[], Awaitable]) -> str:
        """Runs the workflow under guard: completed, killed, or held."""
        try:
            # Runtime construction may precede screening, but neither the
            # primary model nor its tools receive an unclassified payload.
            await self.ctx.screen("ingress", str(event))
            self.agent_task = asyncio.create_task(runner())
            await self.agent_task
            return "completed"
        except FirewallHeld:
            return "held"
        except FirewallKilled:
            return "killed"
        except asyncio.CancelledError:
            if not self.ctx.kill.is_set():
                raise
            return "killed"
        finally:
            for t in self.tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
