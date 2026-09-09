import base64
import html
import re
import unicodedata

# NFKC normalization only flattens Unicode *compatibility* variants (full-width
# forms, ligatures, superscripts) -- it does NOT unify cross-script confusables.
# Cyrillic 'а' (U+0430) and Latin 'a' (U+0061) have no compatibility relationship,
# so NFKC alone leaves homoglyph substitution completely intact. This explicit
# table covers the common Cyrillic/Greek lookalikes actually used in homoglyph
# attacks against Latin-script keyword filters.
_HOMOGLYPH_MAP = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X",
    "і": "i", "І": "I", "ѕ": "s", "Ѕ": "S", "ј": "j", "Ј": "J",
    "ο": "o", "Ο": "O", "α": "a", "Α": "A", "ι": "i", "Ι": "I",
})

_ZERO_WIDTH_RE = re.compile(r'[\u200B-\u200D\uFEFF]')
_B64_RE = re.compile(r'(?:[A-Za-z0-9+/]{4}){4,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?')


def canonical_normalize(raw_text: str) -> str:
    """Strips zero-width spaces, unifies homoglyphs, and surfaces Base64 payloads."""
    text = unicodedata.normalize("NFKC", raw_text)
    text = text.translate(_HOMOGLYPH_MAP)
    text = _ZERO_WIDTH_RE.sub('', text)

    def b64_replacer(match: re.Match) -> str:
        chunk = match.group(0)
        try:
            decoded = base64.b64decode(chunk).decode('utf-8', errors='ignore')
            return f"{chunk} [DECODED: {decoded}]" if len(decoded.strip()) > 3 else chunk
        except Exception:
            return chunk

    return _B64_RE.sub(b64_replacer, text)


def sanitize_and_inoculate(raw_payload: str) -> str:
    """Normalizes, escapes structural delimiters, and wraps in an XML sandbox."""
    normalized = canonical_normalize(str(raw_payload))
    escaped = html.escape(normalized, quote=False)
    return f"<untrusted_payload>{escaped}</untrusted_payload>"
