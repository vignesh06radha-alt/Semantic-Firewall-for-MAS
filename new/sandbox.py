import base64
import html
import re
import unicodedata

# Same technique as ../mas_security_firewall/firewall/sanitizer.py, kept as a
# local copy rather than a cross-import: this testbed's whole point is to
# test a *different placement* for the firewall (ASGI ingress middleware,
# perimeter of the service) than that project's inter-agent sidecar, and it
# should stand alone as one self-contained artifact. See README "Design notes".
_HOMOGLYPH_MAP = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X",
    "і": "i", "І": "I", "ѕ": "s", "Ѕ": "S", "ј": "j", "Ј": "J",
    "ο": "o", "Ο": "O", "α": "a", "Α": "A", "ι": "i", "Ι": "I",
})
_ZERO_WIDTH_RE = re.compile(r"[​-‍﻿]")
_B64_RE = re.compile(r"(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")


def _surface_base64(text: str) -> str:
    def replacer(m: re.Match) -> str:
        chunk = m.group(0)
        try:
            decoded = base64.b64decode(chunk).decode("utf-8", errors="ignore")
            return f"{chunk} [DECODED: {decoded}]" if len(decoded.strip()) > 3 else chunk
        except Exception:
            return chunk
    return _B64_RE.sub(replacer, text)


def sandbox_payload(raw: str) -> str:
    """Normalizes an untrusted string (NFKC, homoglyph unification, zero-width
    stripping, Base64 surfacing) and wraps it in an inert XML boundary before
    it ever reaches the guard model or an agent's context."""
    text = unicodedata.normalize("NFKC", str(raw))
    text = text.translate(_HOMOGLYPH_MAP)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _surface_base64(text)
    escaped = html.escape(text, quote=False)
    return f"<untrusted_payload>{escaped}</untrusted_payload>"
