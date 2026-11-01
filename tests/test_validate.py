from datetime import date
from decimal import Decimal as D

from invoiceflow.schema import Invoice, LineItem
from invoiceflow.validate import fingerprint, validate


def make(**kw):
    base = dict(supplier_name="Acme", invoice_number="1", invoice_date=date(2026, 10, 3),
                currency="GBP", subtotal=D("450"), tax_total=D("90"), total=D("540"),
                line_items=[LineItem(description="a", quantity=D(10), unit_price=D("42.5"), amount=D("425")),
                            LineItem(description="b", unit_price=D(25), amount=D(25))],
                confidence={"totals": 0.97})
    base.update(kw)
    return Invoice(**base)


def test_clean_invoice_passes():
    assert validate(make()).ok


def test_bad_totals_flagged():
    r = validate(make(total=D("600")))
    assert any("!= total" in i for i in r.issues)


def test_line_sum_mismatch():
    assert any("subtotal" in i for i in validate(make(subtotal=D("500"), total=D("590"))).issues)


def test_duplicate_detected():
    inv = make()
    assert any("duplicate" in i for i in validate(inv, {fingerprint(inv)}).issues)


def test_non_invoice_not_postable():
    assert not validate(make(document_type="statement")).ok
