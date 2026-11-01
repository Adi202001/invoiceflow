# invoiceflow

Claude-powered accounts-payable pipeline: **read any invoice layout → validate the maths → post a draft bill to Xero or QuickBooks Online**, with a human review queue for anything doubtful.

```
PDF / scan / image / text
        │
        ▼
 Extraction agent (Claude, forced tool call → strict JSON schema)
        │
        ▼
 Deterministic validation (totals, line maths, dates, currency, duplicates)
        │  fails? → one self-correction pass: Claude re-reads the document with the failed checks
        ▼
 Router ── confidence ≥ 0.85 and all checks pass ──► Xero / QuickBooks (DRAFT bill, idempotent)
        └─ otherwise ───────────────────────────────► review_queue/*.json (human approves)
```

## Why it handles varying layouts
No per-vendor templates or regex. Claude reads PDFs and images natively and fills a fixed schema (`invoiceflow/schema.py`), so a new supplier layout needs no new code. Accuracy comes from the code around the model, not from trusting it:

- **Forced tool call** – output always matches the schema; the model is told to use `null` rather than guess.
- **Deterministic validation** – line items must sum to subtotal, subtotal + tax must equal total, qty × price must match each line, dates and currency must be sane, duplicates are blocked.
- **Self-correction** – if a check fails, the document is re-read once with the failed checks as feedback.
- **Confidence routing** – the model scores supplier, dates, line items and totals; anything under 0.85 goes to a human.
- **Learning without retraining** – approved extractions per supplier are fed back as few-shot examples (`State.hints`).
- **Prompt caching** on the system prompt keeps repeat-volume cost down.

## Accounting integrations
| | Object created | Safeguards |
|---|---|---|
| `accounting/xero.py` | `ACCPAY` invoice (or `ACCPAYCREDIT`) | created as **DRAFT**; `Idempotency-Key` header so retries never duplicate |
| `accounting/quickbooks.py` | `Bill` (or `VendorCredit`) | vendor lookup-or-create; sandbox base URL by default |

Both default to **dry-run** (print the exact payload, send nothing). `--live` is required to post. Auth is a pre-obtained OAuth2 access token via env vars; a production deployment would add the OAuth refresh flow.

## Data privacy
- Payment details (card numbers, IBANs, account/sort codes) are masked **before text leaves your machine** (`redact.py`). PDFs/images are sent as-is to the model, so use the Claude API's zero-data-retention option for highly sensitive documents.
- Secrets only via environment variables; `.env`, extracted state and the review queue are git-ignored.
- Nothing is auto-approved for payment: bills land in the ledger as drafts.
- Anthropic's commercial API terms do not use API inputs to train models.

## Run it
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # add ANTHROPIC_API_KEY, then: export $(cat .env | xargs)

pytest                          # 12 tests, no API key needed (Claude is stubbed)

invoiceflow samples/acme_layout_a.txt samples/brightpath_layout_b.txt --target xero
invoiceflow samples/*.txt --target quickbooks          # dry-run: prints payloads
invoiceflow invoice.pdf --target xero --live           # really posts drafts
```
Two deliberately different sample layouts are in `samples/`.

## Layout
```
invoiceflow/
  schema.py     canonical Invoice model + Claude tool schema
  extract.py    Claude extraction agent (PDF/image/text, caching, few-shot, feedback)
  validate.py   deterministic checks + duplicate fingerprint
  redact.py     pre-model PII masking
  pipeline.py   orchestration, routing, state
  accounting/   Xero + QuickBooks clients
  cli.py
tests/          validation, routing, self-correction, dedupe, payloads, redaction
```

## Status / limits
- Unit-tested end to end with a stubbed model. The live Claude call and live Xero/QuickBooks posting are written to each API's documented shape but need your own keys/sandbox to exercise.
- Tax-code and chart-of-accounts mapping use single configurable defaults; a real rollout maps per supplier.
- Statements and receipts are classified and routed to review rather than posted.
