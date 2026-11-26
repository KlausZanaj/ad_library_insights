# Contributing to Ad Library Insights

Thanks for helping improve **Ad Library Insights**!

## Core Engineering Principles

1. **Deterministic Python first:** Any metric, statistical test, deduplication rule, or unit-economics formula belongs in pure standard-library Python (`src/ad_library_insights/lab/` or `core/`), with zero heavy ML dependencies.
2. **Engineering honesty:** Meta does not publish commercial ad spend or conversions. Never add fake spend, fabricated ROAS, or extrapolated survival curves when data coverage is below threshold.
3. **Strict untrusted-content isolation:** Any competitor text or video frames handed to LLMs must remain wrapped in `<untrusted_ad_content>` boundaries and audited against `manifest.json` via `check_report`.

## Local Development Setup

```bash
git clone https://github.com/KlausZanaj/ad_library_insights.git
cd ad_library_insights
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

## Running Tests

Every pull request must keep the offline test suite green:

```bash
python -m pytest -q
```

Please add deterministic fixture tests in `tests/` for any new diagnostic, parser fix, or MCP tool behavior.
