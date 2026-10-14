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

## M1 — Evaluation harness ✅

`ledger_orchestrator.evaluation`: (a) template coverage matrix — every target
cell of TAF_G1/G2/G3 by company and year, with source availability and filled
state; (b) reference benchmark — compare a run's facts with values already in
the template and with CGA TAF_G4 aggregates (kTND, rounded).

**Acceptance:** one command prints coverage and accuracy for any run; tests on
synthetic workbooks; the benchmark never treats an absent reference as agreement.

✅ Delivered. `python -m ledger_orchestrator.evaluation coverage|benchmark`.
Baseline with the STAR reference run: sourced input cells filled — TAF_G1
300 / 1,245 (24.1 %, of which 94 prefilled COMAR values), TAF_G2 0 / 96,
TAF_G3 18 / 312 (5.8 %). STAR against CGA 2024: 5 / 5 defined metrics agree
(premiums, capital, result, equity before result, placements); technical
provisions differ by 7,697 kTND (CGA basis unknown, D-006).

## M2 — COMAR 2023–2025 in production ✅

Move the guarded COMAR readers from `scripts/` into the package; register
`comar_individual_v1`; apply D-002/D-003/D-004; validated profile with explicit
balance hierarchy. Values that pass identities are written; conflicts preserved.

**Acceptance:** COMAR run completes through the five agents; every written value
has full evidence; benchmark against the prefilled COMAR 2024/2025 balance and
CGA 2024 premiums reported; STAR replay unchanged; rejection tests for wrong
year, unit, header and corrupted totals.

✅ Delivered. Reference run `20261014T011312_02d71100` (deterministic replay
passes 14/14). TAF_G1 81/81 cells for 2024 and 2025, 78/81 for 2023 (three rows
not published that year); TAF_G3 27/27. Accuracy: 92/92 prefilled template values
agree; CGA 2024: 5/5 defined metrics agree. No conflicts; 12 comparative
restatements of 1–2 TND retained (D-005). STAR replay unchanged.

## M3 — One consolidated workbook ✅

Run several profiles into a single copy of the template (STAR then COMAR, …),
each writer checking that it only touches its own cells.

**Acceptance:** consolidated workbook equals the union of single-company runs;
cross-company write attempts rejected; LibreOffice recalculation clean.

✅ Delivered. `python -m ledger_orchestrator.consolidate --configs config/star.json
config/comar.json` → `outputs/consolidated_*/TAF_consolide.xlsx`, checked for
preserved writes, disjoint cells and distinct companies; no formula errors after
recalculation. Template-wide: TAF_G1 446 / 1,245 sourced cells (35.8 %),
TAF_G3 36 / 312 (11.5 %). COMAR reference run is now `20261014T011713_cc31123a`
(no empty details sheet).

## M4 — Premium history 2010–2022 (TAF_G3)

Biggest coverage gain: six numbers per company-year, 13 years, three companies
(STAR, COMAR, ASTREE), each year also giving the N−1 comparative. Strategy:
classify layouts into families, extract per family, verify with D-001…D-004 and
statement ↔ annex ↔ comparative identities.

**Acceptance:** per company-year verified or reasoned blank; comparatives used as
second evidence; accuracy measured where a reference exists.

🟡 STAR delivered: `python -m ledger_orchestrator.history --config
config/history/star_premiums.json`. Generic NC 26 annex reader
(`extraction/premium_annex.py`) with three-reading identities (D-007). STAR TAF_G3
84/96 (2010 and 2013 have no source document). Consolidated STAR + COMAR + STAR
history: TAF_G3 102/312 (32.7 %). Next: ASTREE (kTND years need D-008 exact
conversion) and COMAR history.

🟡 COMAR delivered for 2019–2022 (multi-line headers, typographic minus signs,
policy-level unit declaration). 2011–2016 publish no category annex 13, so the
branch split has no source; 2016/2018 are scanned; 2017 is rejected because one
column holds only a small amount. Consolidated (4 profiles): TAF_G3 126/312 (40.4 %).

M5 finding (14 Oct): `qwen2.5:7b` (local, RTX 3050) on the ASTREE 2020 annex
invented category labels and split amounts (27 s per page). Its output fails the
grounding checks, so a 7B text model is not used as a table reader. Model
assistance is re-scoped to proposing alias-table entries for human review.

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
