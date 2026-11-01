import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

from invoiceflow.accounting import QuickBooksClient, XeroClient
from invoiceflow.pipeline import State, process
from invoiceflow.redact import redact
from invoiceflow.schema import Invoice, LineItem


def inv(total="540", conf=0.95):
    return Invoice(supplier_name="Acme", invoice_number="INV-2041", invoice_date=date(2026, 10, 3),
                   currency="GBP", subtotal=D("450"), tax_total=D("90"), total=D(total),
                   line_items=[LineItem(description="Brackets", quantity=D(10), unit_price=D("42.5"), amount=D("425")),
                               LineItem(description="Delivery", unit_price=D(25), amount=D(25))],
                   confidence={"totals": conf})


class Fake:
    """Stands in for Claude: first answer can be wrong, second (with feedback) is fixed."""
    def __init__(self, *answers): self.answers, self.calls = list(answers), []
    def extract(self, path, hints=None, feedback=None):
        self.calls.append(feedback)
        return self.answers.pop(0)


def run(tmp_path, fake, client=None):
    f = tmp_path / "a.txt"; f.write_text("x")
    return process(f, fake, client or XeroClient(), State(tmp_path / "s.json"), tmp_path / "rq")


def test_auto_post_dry_run(tmp_path):
    r = run(tmp_path, Fake(inv()))
    assert r.status == "dry_run" and r.detail["payload"]["Invoices"][0]["Status"] == "DRAFT"


def test_self_correction_pass(tmp_path):
    fake = Fake(inv(total="999"), inv())
    r = run(tmp_path, fake)
    assert r.status == "dry_run" and fake.calls[1]  # second call carried feedback


def test_low_confidence_goes_to_review(tmp_path):
    r = run(tmp_path, Fake(inv(conf=0.4)))
    assert r.status == "needs_review"
    assert json.loads((tmp_path / "rq" / "a.json").read_text())["min_confidence"] == 0.4


def test_duplicate_blocked_second_time(tmp_path):
    state = State(tmp_path / "s.json"); f = tmp_path / "a.txt"; f.write_text("x")
    process(f, Fake(inv()), XeroClient(), state, tmp_path / "rq")
    r = process(f, Fake(inv()), XeroClient(), state, tmp_path / "rq")
    assert r.status == "needs_review" and any("duplicate" in i for i in r.report.issues)


def test_quickbooks_payload(tmp_path):
    r = run(tmp_path, Fake(inv()), QuickBooksClient())
    assert len(r.detail["payload"]["Line"]) == 2


def test_extraction_failure_is_reported(tmp_path):
    class Boom:
        def extract(self, *a, **k): raise RuntimeError("api down")
    assert run(tmp_path, Boom()).status == "failed"


def test_redaction():
    out = redact(Path(__file__).parent.parent.joinpath("samples/acme_layout_a.txt").read_text())
    assert "GB29NWBK" not in out and "540.00" in out
