"""Optional pre-model redaction of payment details (bank accounts, card numbers).

Totals, supplier and line items are untouched; only data the extraction does not need
is masked before the document text leaves your environment.
"""
import re

_PATTERNS = [
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD-REDACTED]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN-REDACTED]"),
    (re.compile(r"(?i)(account|acct|a/c)\s*(no\.?|number|#)?\s*[:\-]?\s*\d{6,}"), "[ACCOUNT-REDACTED]"),
    (re.compile(r"(?i)(sort code|routing)\s*[:\-]?\s*[\d\- ]{6,11}"), "[ROUTING-REDACTED]"),
]


def redact(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text
