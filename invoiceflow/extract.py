"""Extraction agent: Claude reads PDFs / images / text and returns a validated Invoice."""
from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Protocol

from .redact import redact
from .schema import Invoice, tool_schema

SYSTEM = (
    "You are an accounts-payable extraction agent. Read the supplied document and call "
    "record_invoice exactly once. Rules: copy numbers exactly as printed; do not infer or "
    "compute missing amounts; dates as ISO YYYY-MM-DD; currency as ISO 4217; credit notes "
    "have document_type 'credit_note' with positive amounts. In `confidence` give a 0-1 score "
    "for: supplier, dates, line_items, totals. Score low if the scan is blurry, handwritten, "
    "or values conflict."
)


class Extractor(Protocol):
    def extract(self, path: Path, hints: list[dict] | None = None,
                feedback: list[str] | None = None) -> Invoice: ...


def _content_block(path: Path, redact_text: bool) -> dict:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime == "application/pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return {"type": "document", "source": {"type": "base64", "media_type": mime, "data": data}}
    if mime.startswith("image/"):
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}
    text = path.read_text(errors="replace")
    return {"type": "text", "text": redact(text) if redact_text else text}


class ClaudeExtractor:
    """Uses Claude with a forced tool call so output always matches the Invoice schema."""

    def __init__(self, model: str | None = None, redact_text: bool = True, client=None):
        import anthropic

        self.client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or os.getenv("INVOICEFLOW_MODEL", "claude-sonnet-5-5")
        self.redact_text = redact_text

    def extract(self, path: Path, hints: list[dict] | None = None,
                feedback: list[str] | None = None) -> Invoice:
        content = [_content_block(path, self.redact_text)]
        if hints:  # approved corrections for this supplier -> few-shot, no retraining
            examples = "\n".join(str(h) for h in hints[:3])
            content.append({"type": "text", "text": f"Previously approved extractions "
                            f"from this supplier, for layout reference only:\n{examples}"})
        if feedback:  # self-correction pass: re-read the document against failed checks
            content.append({"type": "text", "text": "A previous extraction failed these checks: "
                            + "; ".join(feedback) + ". Re-read the document carefully and fix "
                            "only what is actually wrong. If the document itself is inconsistent, "
                            "keep the printed values and lower the confidence."})
        content.append({"type": "text", "text": "Extract this document."})

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=[tool_schema()],
            tool_choice={"type": "tool", "name": "record_invoice"},
            messages=[{"role": "user", "content": content}],
        )
        for block in resp.content:
            if block.type == "tool_use":
                return Invoice.model_validate(block.input)
        raise RuntimeError("Model returned no tool call")
