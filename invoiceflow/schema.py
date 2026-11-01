"""Canonical invoice schema. Claude is forced to return exactly this shape."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal
    amount: Decimal = Field(description="Line total excluding tax")
    tax_rate: Optional[Decimal] = Field(None, description="Percent, e.g. 20 for 20%")


class Invoice(BaseModel):
    document_type: Literal["invoice", "credit_note", "receipt", "statement", "other"] = "invoice"
    supplier_name: str
    supplier_tax_id: Optional[str] = None
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None
    currency: str = Field(description="ISO 4217 code, e.g. USD")
    line_items: list[LineItem]
    subtotal: Decimal
    tax_total: Decimal = Decimal("0")
    total: Decimal
    purchase_order: Optional[str] = None
    # Model's self-reported certainty per field group, 0..1
    confidence: dict[str, float] = Field(default_factory=dict)
    notes: Optional[str] = None


def tool_schema() -> dict:
    """JSON schema handed to Claude as a forced tool call."""
    return {
        "name": "record_invoice",
        "description": "Record the structured data extracted from the document. "
        "Use null for anything not present; never guess amounts.",
        "input_schema": Invoice.model_json_schema(),
    }
