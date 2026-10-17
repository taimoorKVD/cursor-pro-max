"""Best-effort redaction before WhatsApp / logs."""
from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
]


def scrub(text: str) -> str:
    out = text
    for pattern in _PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out
