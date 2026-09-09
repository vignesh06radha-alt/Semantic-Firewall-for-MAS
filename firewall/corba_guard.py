import hashlib
from collections import defaultdict, deque
from typing import Tuple
from config.settings import settings


class CorbaCircuitBreaker:
    """Detects Contagious Recursive Blocking Attacks (CORBA): stateless classifiers
    evaluate each payload in isolation, so a polite ping-pong loop between agents
    can look benign on every single hop while still exhausting compute/tokens.
    This tracks a per-session ring buffer of content hashes plus a hard hop cap."""

    def __init__(self, window_size: int = 5, max_cycle_frequency: int = 2):
        self.window_size = window_size
        self.max_cycle_frequency = max_cycle_frequency
        self.session_buffers = defaultdict(lambda: deque(maxlen=window_size))

    def evaluate_packet(self, session_id: str, hop_count: int, canonical_content: str) -> Tuple[bool, str]:
        if hop_count > settings.MAX_ALLOWED_HOPS:
            return False, "ERR_SEC_003_MAX_HOPS_EXCEEDED"

        content_hash = hashlib.sha256(canonical_content.strip().encode('utf-8')).hexdigest()
        history = self.session_buffers[session_id]

        if history.count(content_hash) >= self.max_cycle_frequency:
            return False, "ERR_SEC_002_CORBA_RECURSIVE_LOOP_DETECTED"

        history.append(content_hash)
        return True, "OK"


corba_guard = CorbaCircuitBreaker()
