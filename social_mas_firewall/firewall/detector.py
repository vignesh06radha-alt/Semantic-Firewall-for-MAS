"""Deterministic, evidence-grounded injection detector -- the guardian's fast
first layer. Rules that keep it from 'assuming random stuff':
  1. Every signal carries the exact substring it matched; no match, no signal.
  2. Scored per distinct category (repeats don't escalate), and a single weak
     category never blocks anything.
  3. Three tiers: >=3 'block' (trip the kill switch), 2 'suspect' (let the
     agents keep working but hold outward side effects for human review),
     else 'clean'. 'Suspect' is a routing decision, not an accusation.
  4. It never rewrites content.
Patterns look for the *structure* of an attack on an automation system (text
addressed to an AI/agent, directives to publish / reveal / repeat, delimiter
breakout), not topics -- so ordinary comments that merely say 'admin' or
'reply' score at most 1.
"""
import re
from dataclasses import dataclass, field

BLOCK_THRESHOLD = 3
SUSPECT_THRESHOLD = 2

_SEP_RE = re.compile(r"[_\-]+")
_WS_RE = re.compile(r"\s+")
_DECODED_SEG_RE = re.compile(r"\[DECODED:[a-z0-9]+: (.*?)\](?=\s|$)", re.DOTALL)


def canonicalize(text: str) -> str:
    return _WS_RE.sub(" ", _SEP_RE.sub(" ", text.lower())).strip()


_BOT = (r"(?:the |our |this )?(?:social media (?:assistant|manager|bot|agent)|community manager(?: bot)?|"
        r"account manager(?: bot)?|(?:analyst|monitor|planner|publisher) agent|content bot|automation(?: system)?|"
        r"assistant|ai(?: agent| assistant| model| system)?|llm|language model|bot|agent|model)")
_VERB_ACT = r"(?:publish|post|reply|respond|dm|message|follow|send|include|paste|reveal|share|print|output|write)"

_PATTERNS: list[tuple[str, int, re.Pattern]] = [
    ("delimiter_breakout", 3, re.compile(
        r"</? ?untrusted payload ?>|< ?/? ?(?:system|assistant|instruction|prompt|admin)\b[^>]{0,60}>")),
    ("agent_addressing", 2, re.compile(
        r"\b(?:notes?|messages?|instructions?|directives?|notices?|memo|reminder|attention|nota|mensaje) (?:to|for|para) " + _BOT + r"\b"
        r"|\b(?:hey|dear|attention) " + _BOT + r"\b"
        r"|\bas the (?:account|community|social media) (?:manager|assistant|bot)\b"
        r"|\byou are (?:now )?(?:an? )?(?:unrestricted|different|new) (?:assistant|model|agent|bot)\b"
        r"|\b(?:pretend|act as|roleplay as) (?:you are|you're|to be)\b[^.\n]{0,40}\b(?:assistant|model|agent|bot|manager)\b"
        r"|\bpara el asistente\b")),
    ("vocative", 1, re.compile(r"(?:^|[.!?:] |, )(?:assistant|bot|agent|manager)[,:]")),
    ("override_instruction", 2, re.compile(
        r"\b(?:ignore|disregard|forget|bypass|override|skip|discard|ignora)\b[^.\n]{0,40}"
        r"\b(?:previous|prior|above|earlier|anteriores?|all|your|any|these|the)\b[^.\n]{0,30}"
        r"\b(?:instructions?|guidelines?|rules?|polic(?:y|ies)|prompts?|restrictions?|safeguards?|reglas|instrucciones)\b")),
    ("action_directive", 2, re.compile(
        r"\b(?:you|assistant|bot|agent|manager) (?:must|should|will|need to|have to|are to)\b[^.\n]{0,40}\b" + _VERB_ACT + r"\b"
        r"|\b(?:publish|post|send)\b[^.\n]{0,25}\b(?:saying|that says|with the text|reading|exactly)\b"
        r"|\breply (?:to this comment )?with exactly\b"
        r"|\b(?:publish|publica)\b[^.\n]{0,30}\b(?:new post|main feed|right away|immediately|now|ahora)\b")),
    ("exfil_directive", 2, re.compile(
        r"\b(?:include|paste|print|reveal|share|send|output|show|give|leak|expose|disclose|incluye|comparte)\b[^.\n]{0,35}"
        r"\b(?:your|the account'?s?|tu|the confidential|the internal)\b[^.\n]{0,25}"
        r"\b(?:api|token|credentials?|password|configuration|config|system prompt|secrets?|campaign|configuraci)\w*")),
    ("dos_directive", 2, re.compile(
        r"(?<!i )(?<!we )(?<!'m )(?<!'ll )\b(?:keep|continue) (?:replying|responding|monitoring|investigating|reviewing|answering|re ?checking|the conversation)\b"
        r"|\b(?:never stop|do not stop|don'?t stop) (?:replying|responding|monitoring|answering|the conversation)\b"
        r"|\bkeep going until\b"
        r"|\b(?:investigate|check|review|audit|scan|open|visit)\b[^.\n]{0,25}\b(?:every|each|all)\b[^.\n]{0,35}\b(?:followers?|accounts?|profiles?|comments?|replies|posts?)\b"
        r"|\b(?:re ?check|re ?review|re ?run|repeat)\b[^.\n]{0,40}\b(?:after every|every (?:action|reply|pass|time)|again and again|until (?:i|you|someone) (?:say|tell|stop))\b"
        r"|\bforever\b|\buntil everyone is reviewed\b|\bdo not stop until\b|\banswer each one immediately\b")),
    ("authority_claim", 1, re.compile(
        r"\b(?:admin(?:istrator)? (?:note|directive|ruling)|platform (?:team|staff)|trust (?:and|&) safety|meta (?:team|staff)|"
        r"official notice|moderation team|security team|this account is verified)\b")),
    ("component_mention", 1, re.compile(
        r"\b(?:social media (?:assistant|manager|bot)|community manager bot|account manager bot|"
        r"(?:analyst|monitor|planner|publisher) agent|automation system)\b")),
]


@dataclass(frozen=True)
class Signal:
    name: str
    weight: int
    evidence: str


@dataclass
class Detection:
    score: int = 0
    signals: list[Signal] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def tier(self) -> str:
        if self.score >= BLOCK_THRESHOLD:
            return "block"
        if self.score >= SUSPECT_THRESHOLD:
            return "suspect"
        return "clean"

    def summary(self) -> str:
        return f"score={self.score} tier={self.tier} " + "; ".join(
            f"{s.name}({s.weight}):{s.evidence[:50]!r}" for s in self.signals)


def _scan(canon: str) -> dict[str, Signal]:
    found = {}
    for name, weight, pattern in _PATTERNS:
        m = pattern.search(canon)
        if m:
            found[name] = Signal(name, weight, m.group(0))
    return found


def detect(normalized_text: str, normalize_flags: list[str] | None = None) -> Detection:
    """`normalized_text` is sanitizer.normalize_payload()'s output (decoded
    spans already inlined as `[DECODED:codec: ...]`)."""
    found = _scan(canonicalize(normalized_text))

    # A directive hidden inside an encoding is stronger evidence than the same
    # words in plain text: ordinary comments rarely smuggle imperatives
    # through Base64/hex/percent-encoding.
    hidden = False
    for seg in _DECODED_SEG_RE.findall(normalized_text):
        inner = _scan(canonicalize(seg))
        if any(s.weight >= 2 for s in inner.values()):
            hidden = True
            for name, sig in inner.items():
                found.setdefault(name, sig)
    if hidden:
        found["hidden_in_encoding"] = Signal("hidden_in_encoding", 1, "directive inside decoded span")

    signals = sorted(found.values(), key=lambda s: -s.weight)
    return Detection(score=sum(s.weight for s in signals), signals=signals, flags=list(normalize_flags or []))
