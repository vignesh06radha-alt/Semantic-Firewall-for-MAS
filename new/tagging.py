import re
from typing import Optional, Tuple

_TAG_RE = re.compile(r"^\[AGENT:\s*([A-Za-z0-9_]+)\]\s*")


def tag(agent_name: str, content: str) -> str:
    """Prefixes agent-generated content with an explicit provenance marker
    before it's routed to the next agent ("LLM Tagging" in the spec). This is
    what lets a receiving agent's prompt distinguish a peer's output (never
    re-executed as an instruction) from untrusted external text -- which
    never carries a well-formed leading tag, since sandbox.py escapes the
    literal characters `[AGENT:` would need to spoof one convincingly, and
    any injected fake tag still arrives wrapped inside sandbox.py's own
    <untrusted_payload> boundary rather than at the true message start."""
    return f"[AGENT:{agent_name}] {content}"


def strip_tag(tagged_content: str) -> Tuple[Optional[str], str]:
    """Returns (agent_name_or_None, content_without_the_tag)."""
    m = _TAG_RE.match(tagged_content)
    if not m:
        return None, tagged_content
    return m.group(1), tagged_content[m.end():]
