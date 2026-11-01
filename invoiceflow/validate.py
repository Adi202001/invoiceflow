"""Deterministic checks. The LLM extracts; plain code decides whether to trust it."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from .schema import Invoice

TOL = Decimal("0.02")


@dataclass
class Report:
    issues: list[str] = field(default_factory=list)
    min_confidence: float = 1.0

    @property
    def ok(self) -> bool:
        return not self.issues


def fingerprint(inv: Invoice) -> str:
    key = f"{inv.supplier_name.strip().lower()}|{inv.invoice_number.strip().lower()}|{inv.total}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def validate(inv: Invoice, seen: set[str] | None = None) -> Report:
    r = Report()
    line_sum = sum((li.amount for li in inv.line_items), Decimal("0"))
    if not inv.line_items:
        r.issues.append("no line items extracted")
    if abs(line_sum - inv.subtotal) > TOL:
        r.issues.append(f"line items sum {line_sum} != subtotal {inv.subtotal}")
    if abs(inv.subtotal + inv.tax_total - inv.total) > TOL:
        r.issues.append(f"subtotal+tax {inv.subtotal + inv.tax_total} != total {inv.total}")
    for li in inv.line_items:
        if abs(li.quantity * li.unit_price - li.amount) > Decimal("0.05") + TOL:
            r.issues.append(f"line '{li.description[:30]}': qty*price != amount")
    if inv.due_date and inv.due_date < inv.invoice_date:
        r.issues.append("due date before invoice date")
    if len(inv.currency) != 3:
        r.issues.append(f"bad currency code '{inv.currency}'")
    if inv.document_type not in ("invoice", "credit_note"):
        r.issues.append(f"not postable: document_type={inv.document_type}")
    if seen is not None and fingerprint(inv) in seen:
        r.issues.append("duplicate of an already-processed invoice")
    if inv.confidence:
        r.min_confidence = min(inv.confidence.values())
    return r
