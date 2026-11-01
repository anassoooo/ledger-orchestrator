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

🟡 ASTREE delivered: premiums 2012, 2013, 2015, 2017–2021, 2025 complete; life only
for 2022–2024 (annex 13 not found — partly scanned pages). Rejected with reasons:
2011 (statement unit undeclared), 2014 (PRV11 row not found), 2016 (row does not
reconcile). Consolidated (5 profiles): TAF_G3 183/312 (58.7 %).

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

🟡 Phase 1 delivered (1 Nov): benchmark harness, no model involved.
`python -m ledger_orchestrator.evaluation answer-key --consolidation <ref>` freezes 38
TAF_G3 company-years (24 solved, 3 life-only, 11 open) into a fingerprinted key of 344
identity-verified answers; `… harness` scores any reader through a reader-independent
gate (grounding on the cited page, two printings of each total, categories = total,
D-002 zeros). Deterministic baseline: 328/344 admitted, 0 silent errors. Injected
errors: digit swaps, ±10 TND, ×1000 and previous-year copies all caught; **category
swaps across branches pass (2/48 caught)**, so the gate must anchor columns to headers
before any model reader is trusted. External APIs governed by D-010.

✅ Column anchoring (1 Nov): every non-zero category must sit on the annex's
"Primes émises" row under a header naming a category of its template branch.
Category swaps across branches 48/48 caught, "Primes acquises" row 87/87 caught
(STAR only: other layouts give no one-category-per-column earned row to inject),
baseline unchanged at 328/344 with 0 silent errors. Next: the first model reader
(phase 2) with recorded, replayable calls.

🟡 Phase 2 (1 Nov): model readers on Groq's free tier, every call recorded and replayable.
- An exploring agent (`--readers groq-explore`: contents, search, page reads, check) never
  admitted a value: 50–80k tokens per company-year against 200k per day, and re-reading
  what the context budget elided. It did produce the key finding: gpt-oss-120b read the
  right row of STAR 2015 but shifted every amount one column (A.TRAVAIL is blank), and
  column anchoring rejected it.
- The scoped reader (`--readers groq`) separates navigation from reading: a shared,
  deterministic locator finds premium pages by title and "Primes émises" row (38/38 tasks,
  every cited page), and the model receives excerpts plus a Positions block (x-range of each
  header word and amount). Text layout alone could not show STAR's right-aligned amounts
  under left-aligned headers; with coordinates the shift disappeared.
- qwen/qwen3.8-27b, STAR: 2 calls and ~6k tokens per year. First run 100/125 admitted,
  2 silent errors, both a GRELE / M.B swap inside IRDS (template value unchanged) caused by
  the Positions block joining two headers printed 1.7 pt apart; fixed. Rerun: 2012 and
  2014–2016 40/40 admitted, 0 silent errors; 2011 too large for the 7,000 input-token
  per-minute cap; 2017–2022 not reached (daily quota).
Next: finish STAR and run COMAR and ASTREE across days (recordings make reruns free);
compare models; make the context estimate tokenizer-aware.

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
