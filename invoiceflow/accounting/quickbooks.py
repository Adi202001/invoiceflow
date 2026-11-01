"""QuickBooks Online: Bill (or VendorCredit) with idempotent vendor lookup-or-create."""
from __future__ import annotations

import os

import httpx

from ..schema import Invoice


class QuickBooksClient:
    def __init__(self, access_token: str | None = None, realm_id: str | None = None,
                 expense_account_id: str = "7", base_url: str | None = None):
        self.token = access_token or os.getenv("QBO_ACCESS_TOKEN", "")
        self.realm = realm_id or os.getenv("QBO_REALM_ID", "")
        self.base = (base_url or os.getenv("QBO_BASE_URL", "https://sandbox-quickbooks.api.intuit.com"))
        self.expense_account_id = expense_account_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base}/v3/company/{self.realm}/{path}"

    def _vendor_id(self, name: str) -> str:
        q = f"select Id from Vendor where DisplayName = '{name.replace(chr(39), chr(92) + chr(39))}'"
        r = httpx.get(self._url("query"), params={"query": q, "minorversion": 70},
                      headers=self._headers(), timeout=30)
        r.raise_for_status()
        found = r.json().get("QueryResponse", {}).get("Vendor", [])
        if found:
            return found[0]["Id"]
        c = httpx.post(self._url("vendor?minorversion=70"), json={"DisplayName": name},
                       headers=self._headers(), timeout=30)
        c.raise_for_status()
        return c.json()["Vendor"]["Id"]

    def build_payload(self, inv: Invoice, vendor_id: str = "{vendor-id}") -> dict:
        return {
            "VendorRef": {"value": vendor_id},
            "DocNumber": inv.invoice_number[:21],
            "TxnDate": inv.invoice_date.isoformat(),
            "DueDate": (inv.due_date or inv.invoice_date).isoformat(),
            "CurrencyRef": {"value": inv.currency},
            "PrivateNote": f"PO: {inv.purchase_order or '-'} | imported by invoiceflow",
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": float(li.amount),
                "Description": li.description,
                "AccountBasedExpenseLineDetail": {"AccountRef": {"value": self.expense_account_id}},
            } for li in inv.line_items],
        }

    def post_bill(self, inv: Invoice, dry_run: bool = True) -> dict:
        if dry_run:
            return {"dry_run": True, "payload": self.build_payload(inv)}
        entity = "bill" if inv.document_type == "invoice" else "vendorcredit"
        payload = self.build_payload(inv, self._vendor_id(inv.supplier_name))
        r = httpx.post(self._url(f"{entity}?minorversion=70"), json=payload,
                       headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()
