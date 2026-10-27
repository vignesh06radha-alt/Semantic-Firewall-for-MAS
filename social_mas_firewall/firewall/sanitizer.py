import base64
import binascii
import html
import re
import urllib.parse
import unicodedata

# Local normalization for the in-process inter-agent ingress firewall.
_HOMOGLYPH_MAP = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X",
    "і": "i", "І": "I", "ѕ": "s", "Ѕ": "S", "ј": "j", "Ј": "J",
    "ο": "o", "Ο": "O", "α": "a", "Α": "A", "ι": "i", "Ι": "I",
})
# Zero-width characters plus bidi controls (RLO/LRO/isolates can visually
# reorder text so a reviewer and a keyword filter see different strings).
_INVISIBLE_RE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]")
_B64_RE = re.compile(r"(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")
_B64_LOOSE_RE = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){8,}\b")
_PCT_RE = re.compile(r"(?:%[0-9A-Fa-f]{2}){3,}")

_MAX_DECODE_DEPTH = 2


def surface_base64(text: str) -> str:
    """Legacy, Base64-only surfacing. Used unconditionally by
    agents/ingestion.py so the *undefended* baselines don't get accidental
    immunity from this graph never decoding what an LLM could decode
    zero-shot (see the same fix in
    ../mas_security_firewall/graph/workflow.py::_expand_b64_chunks).

    Deliberately NOT upgraded to the multi-codec decoder below: the baselines
    are the control group, and changing what they see would silently change
    the numbers every defense is compared against."""
    def replacer(m: re.Match) -> str:
        chunk = m.group(0)
        try:
            decoded = base64.b64decode(chunk).decode("utf-8", errors="ignore")
            return f"{chunk} [DECODED: {decoded}]" if len(decoded.strip()) > 3 else chunk
        except Exception:
            return chunk
    return _B64_RE.sub(replacer, text)


def _looks_like_text(decoded: bytes) -> str | None:
    """Accept a decode only if it is strict UTF-8 and overwhelmingly
    printable prose-like text. This is what stops the decoder from
    'assuming' things: a SHA hash, a UUID, an API-token-looking string or a
    CSS colour decodes to binary garbage, fails this test, and is left
    exactly as written instead of being treated as a hidden message."""
    try:
        text = decoded.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(text.strip()) < 8:
        return None
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\t")
    letters_spaces = sum(1 for ch in text if ch.isalpha() or ch.isspace())
    if printable / len(text) < 0.95 or letters_spaces / len(text) < 0.6:
        return None
    if " " not in text.strip():
        return None
    return text


def _try_base64(chunk: str) -> str | None:
    cleaned = chunk.replace("-", "+").replace("_", "/")
    cleaned += "=" * (-len(cleaned) % 4)
    try:
        return _looks_like_text(base64.b64decode(cleaned, validate=True))
    except (binascii.Error, ValueError):
        return None


def _try_hex(chunk: str) -> str | None:
    try:
        return _looks_like_text(bytes.fromhex(chunk))
    except ValueError:
        return None


def _try_percent(chunk: str) -> str | None:
    try:
        return _looks_like_text(urllib.parse.unquote_to_bytes(chunk))
    except Exception:
        return None


def decode_all_layers(text: str, _depth: int = 0) -> tuple[str, list[str]]:
    """Surfaces Base64 (standard + URL-safe), hex, percent-encoding and HTML
    entities, recursively up to _MAX_DECODE_DEPTH (so Base64-of-Base64 is
    seen). Each surfaced span is appended inline as `[DECODED:<codec>: ...]`
    next to the original, never replacing it. Returns (new_text, flags)."""
    flags: list[str] = []

    unescaped = html.unescape(text)
    if unescaped != text:
        flags.append("html_entities")
        text = unescaped

    def make_replacer(codec: str, fn):
        def replacer(m: re.Match) -> str:
            chunk = m.group(0)
            decoded = fn(chunk)
            if decoded is None:
                return chunk
            flags.append(codec)
            inner = decoded
            if _depth + 1 < _MAX_DECODE_DEPTH:
                inner, inner_flags = decode_all_layers(decoded, _depth + 1)
                flags.extend(f"nested_{f}" for f in inner_flags)
            return f"{chunk} [DECODED:{codec}: {inner}]"
        return replacer

    text = _B64_LOOSE_RE.sub(make_replacer("base64", _try_base64), text)
    text = _HEX_RE.sub(make_replacer("hex", _try_hex), text)
    text = _PCT_RE.sub(make_replacer("percent", _try_percent), text)
    return text, flags


def normalize_payload(raw: str) -> tuple[str, list[str]]:
    """NFKC, homoglyph unification, invisible/bidi stripping, then
    multi-codec decoding. Returns (normalized_text, flags) -- flags records
    *what was undone*, which is itself evidence (a post that needed three
    layers of unwrapping to read is unusual) but is never treated as proof."""
    flags: list[str] = []
    text = unicodedata.normalize("NFKC", str(raw))
    if _INVISIBLE_RE.search(text):
        flags.append("invisible_chars")
    text = _INVISIBLE_RE.sub("", text)
    translated = text.translate(_HOMOGLYPH_MAP)
    if translated != text:
        flags.append("homoglyphs")
    text, decode_flags = decode_all_layers(translated)
    flags.extend(decode_flags)
    return text, flags


def sandbox_payload(raw: str) -> str:
    """Normalize and XML-escape data. Delimiters aid separation but cannot
    guarantee that a language model will ignore instructions in the data."""
    text, _ = normalize_payload(raw)
    return f"<untrusted_payload>\n{html.escape(text, quote=False)}\n</untrusted_payload>"
