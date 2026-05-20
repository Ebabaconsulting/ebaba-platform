# ebaba-platform

Foundational Python toolkit for **ebabaConsulting**. v1 ships two deterministic, audit-friendly tools:

| Tool | Purpose | Output |
|---|---|---|
| `client_intake` | Convert raw client info (text / markdown / JSON) into a validated executive profile. | `outputs/client_profiles/*.json` |
| `market_analyzer` | Parse and clean industry trend feeds (text / md / json / csv) into an executive brief. | `outputs/market_reports/*.md` |

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Optional dev extras (pytest):

```bash
pip install -e ".[dev]"
```

## Run

```bash
# 1) Client intake (sample data provided)
python -m ebaba.tools.client_intake --input data/inbox/acme.txt

# 2) Market analyzer (sample feed provided)
python -m ebaba.tools.market_analyzer \
    --input data/market_feeds/fintech_sample.txt \
    --industry fintech
```

Outputs land in `outputs/client_profiles/` and `outputs/market_reports/`.

## Tests

```bash
pytest -q
```

## Layout

```
src/ebaba/
├── core/         # I/O, validation, formatting, logging, enrichment
├── schemas/      # Pydantic models (ClientProfile, MarketReport)
├── templates/    # Jinja2 + JSON schema + section config
└── tools/        # CLI entrypoints: client_intake.py, market_analyzer.py
```

## Design Notes

- **Deterministic v1**: no LLM calls. All enrichment (engagement tier, priority score, recommended practice area) is rule-based from `revenue_band_usd`, `engagement.budget_band_usd`, and signal density.
- **Atomic writes**: every artefact is written via a temp file + `os.replace` so a crash never leaves a half-written executive deliverable.
- **Section configuration** (`templates/sections.json`) explicitly covers **M&A Activity** (Competitive Landscape) and **Talent & Skills** (Macro Drivers).
