# LedgerOrchestrator

### Evidence-first extraction of insurers' financial statements for the CMF template

LedgerOrchestrator fills the CMF workbook `TAF_G1_G2_G3_G4.xlsx` (balance sheets
and premiums by branch of Tunisian insurers) from their published annual reports.
Every number it writes carries its source page, bounding box and SHA-256, and is
admitted only when **independent accounting identities** agree: totals equal their
details, the premium annex equals the technical statement, current figures equal
next year's comparatives. A blank with a reason is preferred to a plausible guess.

> Proof-of-concept, not a certified accounting system. Business rules that still
> await the supervisor's confirmation are labelled `default` in
> [DECISIONS.md](docs/DECISIONS.md).

## Results (14 October 2026)

Coverage of the template cells for which a source document exists, measured by
`python -m ledger_orchestrator.evaluation coverage`:

| Sheet | Filled / sourced cells | Companies |
| --- | ---: | --- |
| TAF_G1 balance sheet 2021–2025 | 446 / 1,245 (35.8 %) | STAR, COMAR 2023–2025 (incl. 94 prefilled COMAR values, confirmed) |
| TAF_G3 premiums by branch 2010–2025 | 183 / 312 (58.7 %) | STAR 2011–2025, COMAR 2019–2025, ASTREE 2012–2025 (partial) |
| TAF_G2 premiums (takaful/life) | 0 / 96 | ZITOUNA not started |

Accuracy against references the extractor never sees, measured by
`python -m ledger_orchestrator.evaluation benchmark`:

| Reference | Compared | Agreement |
| --- | ---: | ---: |
| COMAR balance values already typed in the template (2024/2025) | 92 | 100 % |
| CGA aggregates in TAF_G4, 2024 (premiums, capital, result, equity, placements) — STAR and COMAR | 10 | 100 % |
| ASTREE 2024 non-life + life premiums vs CGA | 1 | exact to the kTND |
| Generic history reader vs the production STAR reader, 2024 | 14 | 100 % |

Years that fail an identity are rejected with a reason rather than guessed (for
example ASTREE 2016, COMAR 2017, the scanned COMAR 2016/2018 reports).

## How it works

```text
documents → extraction → validation → workbook → review     (deterministic agents)
    │            │             │            │          └ coverage, review queue, reasons
    │            │             │            └ guarded writes, COUNT-guarded formulas,
    │            │             │              conflicts preserved, LibreOffice recalc
    │            │             └ identities: Σ details = total, gross − provisions = net,
    │            │               annex = statement = reconciliation, N = N+1 comparative
    │            └ native text or OCR, qualified readers per company and layout family
    └ identity, period, unit, SHA-256
```

- **Statements profiles** (`config/star.json`, `config/comar.json`) drive the full
  balance sheet and premium pipeline for qualified years.
- **Premium-history profiles** (`config/history/*.json`) read the regulated NC 26
  annexes generically: annex 13/12 categories, PRNV11/PRV11 statement rows,
  multi-line and interleaved headers, kTND annexes proven by identity.
- **Consolidation** runs several profiles into one copy of the template and proves
  that every write survived and no cell was written twice.
- **Human review** (LangGraph, SQLite checkpoints) records decisions on unresolved
  cells; an optional local copilot explains a run with checked citations.

### Actuarial and accounting rules (selected)

- Premiums are issued premiums net of cancellations, before reinsurance (NC 28),
  confirmed against CGA totals for STAR and COMAR (D-001).
- The five template branches partition direct non-life business; acceptations are
  excluded and reported (D-003). ASTREE Groupe = Maladie + Invalidité, corroborated
  by FTUSA 2024 (D-009).
- A dash is zero only when a published total proves it (D-002); a restated
  comparative never overwrites the year's own publication (D-005).
- Thousands of dinars are converted only when exact (D-008).

### On language models

Models may propose, never admit. A local `qwen2.5:7b` was evaluated as a table
reader on an ASTREE annex: it invented labels and split amounts, so its output
fails the grounding checks and it is not used to read numbers. This negative
result is recorded in the [plan](docs/PLAN.md).

## Quick start

Docker Desktop is required (Tesseract and LibreOffice live in the image).

```powershell
docker compose build
# One consolidated workbook with every qualified profile:
docker compose run --rm engine python -m ledger_orchestrator.consolidate --configs `
  config/star.json config/comar.json config/history/star_premiums.json `
  config/history/comar_premiums.json config/history/astree_premiums.json
# Measure it:
python -m ledger_orchestrator.evaluation coverage --root data --workbook outputs/consolidated_<id>/TAF_consolide.xlsx
```

The review desk is served at <http://127.0.0.1:8000/review> after `docker compose up -d`
([LangGraph review](docs/REVUE_LANGGRAPH.md), [local copilot](docs/COPILOTE_LOCAL.md)).

## Verification

`scripts/docker_test.sh` runs the 144-test suite offline in the image. Before every
merge, `scripts/verify_reference.py` replays the STAR and COMAR reference runs and
compares documents, values, controls, anomalies, writes, coverage, formulas, styles
and recalculated values (14 checks each). Tests use synthetic data only.

## Repository map

```text
src/ledger_orchestrator/
├── pipeline.py, orchestration.py   statements pipeline and agent trace
├── history.py                      premium-history pipeline (TAF_G3)
├── consolidate.py                  several profiles → one verified workbook
├── evaluation/                     coverage matrix and reference benchmark
├── extraction/                     STAR, COMAR, generic NC 26 annex reader, OCR
├── validation/                     accounting identities and evidence gates
├── workbook/                       guarded writers and recalculation
├── review/, api/, ui/              review queue, LangGraph desk, local API
config/                             company, history and qualification contracts
docs/                               constitution, decisions, plan, status, business rules
```

PDFs, workbooks and run outputs stay local and are excluded from Git.

## Documentation

[Constitution](docs/CONSTITUTION.md) · [Decisions](docs/DECISIONS.md) ·
[Plan](docs/PLAN.md) · [Status](docs/STATUS.md) · [Business rules](docs/LOGIQUE_METIER.md) ·
[Agents](docs/ARCHITECTURE_AGENTS.md) · [Profiles](docs/PROFILES.md) · [Demo](docs/DEMO_15_MIN.md)

## Project attribution

- Author: **Anas Bougrine**
- Academic supervisor: **Lazhar Hedfi, Actuary**

## License

MIT. See [LICENSE](LICENSE).
