from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .accounting import QuickBooksClient, XeroClient
from .extract import ClaudeExtractor
from .pipeline import State, process


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="invoiceflow", description=__doc__)
    ap.add_argument("inputs", nargs="+", type=Path, help="invoice files (pdf/png/jpg/txt)")
    ap.add_argument("--target", choices=["xero", "quickbooks", "none"], default="none")
    ap.add_argument("--live", action="store_true", help="really POST to the accounting API (default: dry run)")
    ap.add_argument("--no-redact", action="store_true", help="disable payment-detail redaction for text inputs")
    ap.add_argument("--state", type=Path, default=Path("out/state.json"))
    ap.add_argument("--review-dir", type=Path, default=Path("review_queue"))
    a = ap.parse_args(argv)

    accounting = {"xero": XeroClient, "quickbooks": QuickBooksClient, "none": lambda: None}[a.target]()
    extractor = ClaudeExtractor(redact_text=not a.no_redact)
    state = State(a.state)

    code = 0
    for f in a.inputs:
        r = process(f, extractor, accounting, state, a.review_dir, dry_run=not a.live)
        line = f"{r.file:32} {r.status:13}"
        if r.invoice:
            line += f" {r.invoice.supplier_name} #{r.invoice.invoice_number} {r.invoice.currency} {r.invoice.total}"
        print(line)
        for issue in (r.report.issues if r.report else []):
            print(f"    ! {issue}")
        if r.status == "failed":
            print(f"    ! {r.detail['error']}")
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
