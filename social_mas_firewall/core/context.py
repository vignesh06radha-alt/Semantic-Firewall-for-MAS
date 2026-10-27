import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from config.settings import settings
from firewall.sanitizer import sandbox_payload, surface_base64
from llm.client import chat_json

if TYPE_CHECKING:
    from firewall.guardian import RunGuardian
    from socialapi.stub import SocialPlatformStub


class FirewallKilled(Exception):
    """Raised inside agent code once the guardian's kill switch is set."""


class FirewallHeld(Exception):
    """An uncertain classification prevents delivery to the receiving agent."""


@dataclass
class RunContext:
    """Everything one workflow run shares. Agents never reach the guardian
    directly; they go through these methods, which is what lets the guardian
    sit outside the agents' prompts and memory."""
    run_id: str
    mode: str  # baseline | in_context | firewall
    platform: "SocialPlatformStub"
    guard: Optional["RunGuardian"] = None
    hub: object = None
    kill: asyncio.Event = field(default_factory=asyncio.Event)
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    iterations: int = 0
    followups_total: int = 0
    executed: list = field(default_factory=list)
    held: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    t0: float = field(default_factory=time.perf_counter)

    def check_alive(self) -> None:
        if self.kill.is_set():
            raise FirewallKilled(self.guard.kill_reason if self.guard else "killed")

    async def llm(self, purpose: str, system: str, user: str, schema: dict, num_predict: int = 220) -> dict:
        self.check_alive()
        # Agent-derived text is untrusted as well as external social content.
        res = await chat_json(purpose=purpose, model=settings.AGENT_MODEL, system=system,
                              user=self.present(user),
                              schema=schema, num_predict=num_predict)
        self.llm_calls += 1
        self.prompt_tokens += res.prompt_tokens
        self.completion_tokens += res.completion_tokens
        self.trace.append({"t_ms": (time.perf_counter() - self.t0) * 1000, "purpose": purpose,
                           "latency_ms": res.latency_ms, "ok": res.ok})
        if self.guard:
            self.guard.note_llm(purpose)
        self.check_alive()
        if not res.ok:
            raise ValueError(f"{purpose} model returned invalid structured output")
        return res.data

    def present(self, untrusted: str) -> str:
        """How untrusted text is shown to an agent. The firewall mode hands
        over the sanitized, XML-contained form; the baselines get the raw
        text (with Base64 surfaced, since an unprotected LLM can decode it
        zero-shot -- same fairness fix as the chemical-lab baseline)."""
        if self.mode == "firewall":
            return sandbox_payload(untrusted)
        return surface_base64(untrusted)

    async def screen(self, source: str, text: str) -> None:
        if self.guard:
            await self.guard.screen(source, text)
            if await self.guard.commit_gate() == "hold":
                raise FirewallHeld("Ingress classification requires review")
        self.check_alive()

    async def commit(self, action: dict | None = None) -> str:
        """Gate before any outward side effect. Returns 'ok' or 'hold';
        raises FirewallKilled if the guardian has tripped."""
        if self.guard:
            return await self.guard.commit_gate(action)
        return "ok"
