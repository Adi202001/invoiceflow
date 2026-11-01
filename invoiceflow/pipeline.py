"""Orchestration: extract -> validate -> (self-correct once) -> route to auto-post or human review."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .accounting.base import AccountingClient
from .extract import Extractor
from .schema import Invoice
from .validate import Report, fingerprint, validate

AUTO_POST_CONFIDENCE = 0.85


class State:
    """Tiny JSON store: processed fingerprints (dedupe) + approved examples per supplier."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {"seen": [], "approved": {}}

    @property
    def seen(self) -> set[str]:
        return set(self.data["seen"])

    def hints(self, supplier: str) -> list[dict]:
        return self.data["approved"].get(supplier.lower(), [])

    def record(self, inv: Invoice, approved: bool = True):
        self.data["seen"].append(fingerprint(inv))
        if approved:
            ex = self.data["approved"].setdefault(inv.supplier_name.lower(), [])
            ex.append(json.loads(inv.model_dump_json(exclude={"confidence", "notes"})))
            del ex[:-5]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


@dataclass
class Result:
    file: str
    status: str  # posted | dry_run | needs_review | failed
    invoice: Invoice | None
    report: Report | None
    detail: dict | None = None


def process(path: Path, extractor: Extractor, accounting: AccountingClient | None,
            state: State, review_dir: Path, dry_run: bool = True,
            supplier_hint: str | None = None) -> Result:
    hints = state.hints(supplier_hint) if supplier_hint else None
    try:
        inv = extractor.extract(path, hints)
        if not hints:  # now we know the supplier -> use past approvals on retry
            hints = state.hints(inv.supplier_name) or None
        report = validate(inv, state.seen)
        if report.issues and not any("duplicate" in i for i in report.issues):
            inv = extractor.extract(path, hints, feedback=report.issues)  # one self-correction pass
            report = validate(inv, state.seen)
    except Exception as e:  # unreadable file, API error, schema violation
        return Result(path.name, "failed", None, None, {"error": str(e)})

    trusted = report.ok and report.min_confidence >= AUTO_POST_CONFIDENCE
    if trusted and accounting:
        out = accounting.post_bill(inv, dry_run=dry_run)
        state.record(inv)
        return Result(path.name, "dry_run" if dry_run else "posted", inv, report, out)

    review_dir.mkdir(parents=True, exist_ok=True)
    item = {"source": str(path), "issues": report.issues, "min_confidence": report.min_confidence,
            "extracted": json.loads(inv.model_dump_json())}
    (review_dir / f"{path.stem}.json").write_text(json.dumps(item, indent=2))
    return Result(path.name, "needs_review", inv, report, item)
