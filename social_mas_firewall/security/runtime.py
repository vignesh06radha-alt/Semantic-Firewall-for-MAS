"""Small synchronous reference monitor shared by domain adapters.

Application code is trusted. Models can propose actions, but cannot issue policy,
assign source labels, or call connectors directly. No hostile-code sandbox claim.
"""
from copy import deepcopy
from dataclasses import dataclass, field, replace
import hashlib
import json
import time
from typing import Callable


class PolicyDenied(Exception):
    def __init__(self, rule: str):
        self.rule = rule
        super().__init__(rule)


@dataclass(frozen=True)
class Permission:
    operation: str
    resources: frozenset[str]
    recipients: frozenset[str] = frozenset()
    write: bool = False

    def __post_init__(self):
        object.__setattr__(self, "resources", frozenset(self.resources))
        object.__setattr__(self, "recipients", frozenset(self.recipients))


@dataclass(frozen=True)
class TaskPolicy:
    task_id: str
    permissions: tuple[Permission, ...]
    max_reads: int = 8
    max_writes: int = 2
    max_model_calls: int = 9
    lifetime_seconds: float = 300

    def __post_init__(self):
        object.__setattr__(self, "permissions", tuple(self.permissions))
        if not self.task_id or any(type(n) is not int or n < 0 for n in (
                self.max_reads, self.max_writes, self.max_model_calls)):
            raise ValueError("Invalid task policy")
        if not 0 < self.lifetime_seconds <= 86400:
            raise ValueError("Invalid task lifetime")


@dataclass(frozen=True)
class Action:
    operation: str
    resource: str
    recipient: str = ""
    text: str = ""
    write: bool = False

    def __post_init__(self):
        if any(not isinstance(v, str) for v in (
                self.operation, self.resource, self.recipient, self.text)) or type(self.write) is not bool:
            raise ValueError("Invalid action fields")


@dataclass(frozen=True)
class Source:
    source_id: str
    origin: str
    digest: str
    parents: tuple[str, ...]
    confidentiality: str


@dataclass
class _Ledger:
    started: float = field(default_factory=time.monotonic)
    reads: int = 0
    writes: int = 0
    model_calls: int = 0
    revoked: bool = False
    sources: dict[str, Source] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)


class SecurityRuntime:
    def __init__(self, policy: TaskPolicy):
        self.policy = policy
        self._ledger = _Ledger()

    @property
    def reads(self):
        return self._ledger.reads

    @property
    def writes(self):
        return self._ledger.writes

    @property
    def sources(self):
        # No mutable reference escapes to a receiving agent or adapter consumer.
        return dict(self._ledger.sources)

    @property
    def events(self):
        return deepcopy(self._ledger.events)

    def _deny(self, rule):
        self._ledger.events.append({"kind": "denial", "rule": rule})
        raise PolicyDenied(rule)

    def check_alive(self):
        if self._ledger.revoked:
            self._deny("task_revoked")
        if time.monotonic() - self._ledger.started >= self.policy.lifetime_seconds:
            self._deny("task_expired")

    def revoke(self):
        self._ledger.revoked = True

    def record(self, origin: str, value, *, parents=(), confidentiality="public") -> str:
        self.check_alive()
        parents = tuple(parents)
        if confidentiality not in {"public", "internal", "restricted"}:
            raise ValueError("Invalid confidentiality label")
        if any(p not in self._ledger.sources for p in parents):
            self._deny("unknown_source")
        labels = [confidentiality] + [self._ledger.sources[p].confidentiality for p in parents]
        level = max(labels, key={"public": 0, "internal": 1, "restricted": 2}.get)
        sid = f"{self.policy.task_id}:{len(self._ledger.sources) + 1}"
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        self._ledger.sources[sid] = Source(sid, origin, hashlib.sha256(encoded).hexdigest(), parents, level)
        return sid

    def before_model(self):
        self.check_alive()
        if self._ledger.model_calls >= self.policy.max_model_calls:
            self._deny("model_budget")
        self._ledger.model_calls += 1

    def check(self, action: Action, sources=()):
        self.check_alive()
        grant = next((p for p in self.policy.permissions if p.operation == action.operation
                      and p.write == action.write and action.resource in p.resources
                      and (action.recipient in p.recipients if p.recipients else not action.recipient)), None)
        if grant is None:
            self._deny("operation_scope")
        # Outbound authority includes all information observed by this task.
        # A caller cannot erase a confidential dependency by omitting citations.
        if action.write and any(s.confidentiality != "public" for s in self._ledger.sources.values()):
            self._deny("restricted_disclosure")
        for sid in sources:
            source = self._ledger.sources.get(sid)
            if source is None:
                self._deny("unknown_source")
            if action.write and source.confidentiality != "public":
                self._deny("restricted_disclosure")
        if action.write and self.writes >= self.policy.max_writes:
            self._deny("write_budget")
        if not action.write and self.reads >= self.policy.max_reads:
            self._deny("read_budget")

    def check_batch(self, actions: list[Action], sources=()):
        for action in actions:
            self.check(action, sources)
        if self.writes + sum(a.write for a in actions) > self.policy.max_writes:
            self._deny("write_budget")
        if self.reads + sum(not a.write for a in actions) > self.policy.max_reads:
            self._deny("read_budget")

    def execute(self, action: Action, invoke: Callable, *, sources=()):
        """No await between authorization, budget debit and exact invocation.

        The trusted adapter constructs both the immutable action and callback.
        This runtime must not accept arbitrary callbacks from a model or network.
        """
        sources = tuple(sources)
        self.check(action, sources)
        if action.write:
            self._ledger.writes += 1
        else:
            self._ledger.reads += 1
        event = {"kind": "tool", "operation": action.operation, "resource": action.resource,
                 "recipient": action.recipient, "write": action.write, "sources": list(sources),
                 "text_digest": hashlib.sha256(action.text.encode()).hexdigest(), "status": "started"}
        self._ledger.events.append(event)
        try:
            result = invoke()
        except Exception:
            event["status"] = "error"
            raise
        event["status"] = "executed"
        return deepcopy(result)

    def delegate(self, permissions: tuple[Permission, ...]):
        """Narrow authority while retaining the parent's shared task budget."""
        self.check_alive()
        for child in permissions:
            if not any(child.operation == p.operation and child.write == p.write
                       and child.resources <= p.resources and child.recipients <= p.recipients
                       and bool(child.recipients) == bool(p.recipients)
                       for p in self.policy.permissions):
                self._deny("delegation_expansion")
        delegated = SecurityRuntime(replace(self.policy, permissions=permissions))
        delegated._ledger = self._ledger
        return delegated
