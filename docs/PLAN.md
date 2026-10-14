# Delivery plan

Governed by [the constitution](CONSTITUTION.md); business rules in
[DECISIONS.md](DECISIONS.md). Each milestone lands as reviewable commits with
tests, a STAR non-regression replay and a factual `STATUS.md` entry.

## Where we start (14 October 2026)

The template asks for:

| Sheet | Content | Years | Companies with local PDFs |
| --- | --- | --- | --- |
| TAF_G1 | Balance sheet | 2021–2025 | STAR, COMAR, ZITOUNA |
| TAF_G2 | Premiums (takaful / life companies) | 2010–2025 | ZITOUNA |
| TAF_G3 | Premiums by branch | 2010–2025 | STAR, COMAR, ASTREE, CTAMA (2018, 2020) |
| TAF_G4 | CGA aggregates (kTND) | 2024 filled, 2025 empty | reference only |

Production covers STAR 2023–2025 (TAF_G1 + TAF_G3). COMAR and ASTREE exist as
unapproved candidates. TAF_G4 2024 and the COMAR 2024/2025 balance values already
in the template are independent references nobody had used to measure accuracy yet.

## M0 — Baseline and governance ✅

Commit pending work; fix the order-dependent profile test; record the Docker
baseline (107 tests, STAR replay 14/14); write the constitution, decisions and plan.

## M1 — Evaluation harness

`ledger_orchestrator.evaluation`: (a) template coverage matrix — every target
cell of TAF_G1/G2/G3 by company and year, with source availability and filled
state; (b) reference benchmark — compare a run's facts with values already in
the template and with CGA TAF_G4 aggregates (kTND, rounded).

**Acceptance:** one command prints coverage and accuracy for any run; tests on
synthetic workbooks; the benchmark never treats an absent reference as agreement.

## M2 — COMAR 2023–2025 in production

Move the guarded COMAR readers from `scripts/` into the package; register
`comar_individual_v1`; apply D-002/D-003/D-004; validated profile with explicit
balance hierarchy. Values that pass identities are written; conflicts preserved.

**Acceptance:** COMAR run completes through the five agents; every written value
has full evidence; benchmark against the prefilled COMAR 2024/2025 balance and
CGA 2024 premiums reported; STAR replay unchanged; rejection tests for wrong
year, unit, header and corrupted totals.

## M3 — One consolidated workbook

Run several profiles into a single copy of the template (STAR then COMAR, …),
each writer checking that it only touches its own cells.

**Acceptance:** consolidated workbook equals the union of single-company runs;
cross-company write attempts rejected; LibreOffice recalculation clean.

## M4 — Premium history 2010–2022 (TAF_G3)

Biggest coverage gain: six numbers per company-year, 13 years, three companies
(STAR, COMAR, ASTREE), each year also giving the N−1 comparative. Strategy:
classify layouts into families, extract per family, verify with D-001…D-004 and
statement ↔ annex ↔ comparative identities.

**Acceptance:** per company-year verified or reasoned blank; comparatives used as
second evidence; accuracy measured where a reference exists.

## M5 — Model-assisted extraction, verified by identities

A local model (Ollama, Qwen 2.5 7B on the RTX 3050) proposes table readings as
structured JSON for layouts without a deterministic reader. Proposals go through
the same identities (article IV). Evaluated first on 2023–2025, where
deterministic answers exist: exact-match rate, abstention rate, identity-rejection
rate, latency.

**Acceptance:** evaluation report on known years before any use on history;
no admission without identities; prompts and model versions recorded.

## M6 — ZITOUNA TAKAFUL (TAF_G1 + TAF_G2)

Takaful accounting separates the participants' fund from the operator (wakala
fee); statements 2019–2025 show policyholder/operator/combined columns. Define the
target scope in DECISIONS first, then qualify.

## M7 — Review loop and presentation

Human resolution with evidence produces a new workbook version; README rewritten
around coverage, accuracy and caught contradictions; 10-minute demo.

## Out of scope unless re-justified

ASTREE balance sheets (no TAF_G1 block), years before 2021 for TAF_G1, companies
without local PDFs (MAE, CARTE, GAT, MAGHREBIA…).
