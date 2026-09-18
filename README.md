# LedgerOrchestrator

### Multi-Agent Financial Statement Intelligence

LedgerOrchestrator is a local-first, agent-ready financial document intelligence prototype. It extracts structured accounting data from financial-statement PDFs, validates evidence, recalculates controlled Excel totals, and produces a reviewable audit trail.

The current reference implementation delivers the deterministic extraction and validation core and is validated on **STAR individual financial statements, 2023–2025**, sourced from the Tunisian CMF publication workflow. Its target architecture is a configurable multi-agent system for multi-company and multi-year processing.

> This repository is a proof-of-concept product, not a certified accounting system. Missing, ambiguous, or contradictory source data is reported and never silently invented.

## Why it matters

Financial PDF extraction is not only an OCR problem. A reliable workflow must preserve units, periods, source locations, accounting relationships, conflicts, and the distinction between a real zero and missing information.

```text
Orchestrator
├── Document agent: identity, period, native text and OCR
├── Mapping agent: configurable labels and business dictionary
├── Validation agent: evidence and accounting controls
├── Workbook agent: controlled Excel writing and recalculation
└── Review agent: anomalies, coverage and human-review queue
```

These roles describe the target multi-agent architecture. In the current MVP, their reliable deterministic capabilities are implemented as isolated Python components; explicit agent coordination is the next product layer.

## Current capabilities

- Local-only processing. Runtime code does not download documents or call cloud AI APIs.
- Native PDF extraction with targeted French OCR for scanned pages.
- Evidence: file, SHA-256, page, bounding box, method, unit and conversion factor.
- Conservative admission rules: blanks remain blank; zero is written only when published and admissible.
- Accounting controls for totals, subtotals, gross/provision/net relationships and year comparatives.
- Controlled workbook editing that preserves the supplied template and existing conflicts.
- LibreOffice recalculation in a disposable environment with formula-cache verification.
- Docker image, CLI and minimal local API.
- Review files for unresolved or non-revalidated target cells.

## Agentic architecture

LedgerOrchestrator separates decision-making from evidence production. Specialist components extract, map, validate, write and review data, while the planned orchestrator will route tasks and consolidate status without bypassing deterministic accounting controls. A future local model is reserved for ambiguous label correspondence; it will never invent or directly approve financial values.

## STAR reference result

| Exercise | TAF_G1 balance | TAF_G3 premiums |
| --- | ---: | ---: |
| 2023 | 74 / 81 | 9 / 9 |
| 2024 | 74 / 81 | 9 / 9 |
| 2025 | 58 / 81 | 9 / 9 |

The result is deliberately marked `needs_review`. This is an evidence-backed demonstrator, not a claim of complete accounting coverage.

## Business rules demonstrated

- Target unit: TND, with source unit and conversion factor retained.
- Premium basis: issued premiums before reinsurance ceded.
- Transport includes Aviation; IRDS includes Accidents at work.
- Non-life Acceptations are kept separately and excluded from the five-branch target total.
- Totals are formulas over validated published details.
- Existing conflicting cells are preserved and reported.

## Quick start

Docker Desktop is required for the full integration workflow.

```powershell
docker compose build
docker compose run --rm engine python -m cmf --years 2023 2024 2025
docker compose up -d
Invoke-RestMethod http://localhost:8000/health
```

Generated artifacts are written under `outputs/<run_id>/`: the review workbook, structured report, anomaly log, review queue and optional previews.

## Repository map

```text
cmf/          extraction, validation, orchestration, Excel writer and API
config/       company/template-specific rules
tests/        deterministic unit and integration tests
docs/         business logic, delivery brief and project status
data/         local confidential inputs (ignored by Git)
outputs/      local reports and workbooks (ignored by Git)
```

## Privacy boundary

PDFs, Excel workbooks, caches, reports and generated outputs are excluded from Git. Only code, configuration templates, tests and documentation belong in the public repository. Do not commit confidential source documents.

The runtime is offline with respect to source documents. External CMF research is not part of the extraction pipeline; only user-provided documents are in scope.

## Test suite

```powershell
python -m unittest discover -s tests -q
```

The Docker workflow additionally verifies the LibreOffice recalculation path. The suite covers number parsing, missing-vs-zero policy, evidence gates, conflicts, grouped premiums, OCR diagnostics, source audits and workbook preservation.

## Product roadmap

1. Generalize the profile and mapping layer from STAR to every supplied company and exercise.
2. Introduce a common financial-record schema and configurable workbook profiles.
3. Add the orchestrator and specialist agents around deterministic extraction and validation components.
4. Add a local human-review interface for conflicts and unresolved mappings.
5. Add an optional local model only for ambiguous correspondence, never as an untraceable value generator.

## Documentation

- [Delivery brief](docs/README_REMISE.md)
- [Business logic](docs/LOGIQUE_METIER.md)
- [Project status](docs/STATUS.md)

## License

MIT. See [LICENSE](LICENSE).
