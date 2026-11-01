"""Xero Accounting API: ACCPAY invoice (a supplier bill). Idempotency-Key prevents duplicates on retry."""
from __future__ import annotations

import os

import httpx

from ..schema import Invoice
from ..validate import fingerprint

API = "https://api.xero.com/api.xro/2.0"


class XeroClient:
    def __init__(self, access_token: str | None = None, tenant_id: str | None = None,
                 account_code: str = "400", tax_type: str = "INPUT2"):
        self.token = access_token or os.getenv("XERO_ACCESS_TOKEN", "")
        self.tenant = tenant_id or os.getenv("XERO_TENANT_ID", "")
        self.account_code, self.tax_type = account_code, tax_type

    def build_payload(self, inv: Invoice) -> dict:
        return {"Invoices": [{
            "Type": "ACCPAY" if inv.document_type == "invoice" else "ACCPAYCREDIT",
            "Contact": {"Name": inv.supplier_name},
            "InvoiceNumber": inv.invoice_number,
            "Date": inv.invoice_date.isoformat(),
            "DueDate": (inv.due_date or inv.invoice_date).isoformat(),
            "CurrencyCode": inv.currency,
            "Reference": inv.purchase_order,
            "LineAmountTypes": "Exclusive",
            "Status": "DRAFT",  # a human approves in Xero; automation never self-approves payment
            "LineItems": [{
                "Description": li.description,
                "Quantity": float(li.quantity),
                "UnitAmount": float(li.unit_price),
                "AccountCode": self.account_code,
                "TaxType": self.tax_type,
            } for li in inv.line_items],
        }]}

    def post_bill(self, inv: Invoice, dry_run: bool = True) -> dict:
        payload = self.build_payload(inv)
        if dry_run:
            return {"dry_run": True, "payload": payload}
        r = httpx.post(f"{API}/Invoices", json=payload, timeout=30, headers={
            "Authorization": f"Bearer {self.token}", "xero-tenant-id": self.tenant,
            "Accept": "application/json", "Idempotency-Key": fingerprint(inv)})
        r.raise_for_status()
        return r.json()
