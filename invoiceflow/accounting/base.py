from __future__ import annotations

from typing import Protocol

from ..schema import Invoice


class AccountingClient(Protocol):
    def build_payload(self, inv: Invoice) -> dict: ...
    def post_bill(self, inv: Invoice, dry_run: bool = True) -> dict: ...
