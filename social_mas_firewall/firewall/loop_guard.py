"""Loop detection for the runtime-watch layer -- the CORBA-style defence
(see ../mas_security_firewall/firewall/corba_guard.py), extended with
near-duplicate matching. The chemical-lab version hashed exact message
content; real bots rarely repeat byte-for-byte, so this also counts
messages whose word sets overlap >= `sim` as repeats."""
import re
from collections import defaultdict, deque

_WORD_RE = re.compile(r"[a-z0-9']+")


def _words(text: str) -> frozenset:
    return frozenset(_WORD_RE.findall(text.lower()))


def similarity(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


class LoopGuard:
    def __init__(self, window: int = 6, max_repeats: int = 2, sim: float = 0.8):
        self.max_repeats = max_repeats
        self.sim = sim
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))

    def observe(self, session: str, content: str) -> bool:
        """True once `content` has (near-)repeated `max_repeats` times within
        the recent window for this session."""
        words = _words(content)
        history = self._history[session]
        repeats = sum(1 for w in history if similarity(words, w) >= self.sim)
        history.append(words)
        return repeats >= self.max_repeats
