# Business decisions log

Each decision states its rule, its actuarial/accounting rationale, the evidence,
and its status. `default` means applied by engineering pending supervisor
confirmation; `confirmed` means confirmed by the business owner.

## D-001 — Premium basis: premiums issued, net of cancellations, before reinsurance

- **Rule.** TAF_G3 "Primes émises nettes" uses the *primes émises* line of the
  per-category technical annexes (NC 28 revenue recognition: issued premiums
  net of cancellations), before cessions to reinsurers. Earned premiums, changes
  in unearned-premium provisions and net-of-reinsurance figures are not substitutes.
- **Evidence.** Already defined in `LOGIQUE_METIER.md`. Independently confirmed on
  14 October 2026 against TAF_G4 (CGA, kTND, 2024): STAR non-life published total
  + life total = 431,209.5 kTND vs CGA 431,210; COMAR = 270,631.8 kTND vs CGA
  270,632. Both agree after rounding, which also shows that the CGA figure
  includes acceptations.
- **Status.** confirmed (STAR rule) — corroborated for COMAR.

## D-002 — A printed dash may be admitted as zero only by proof

- **Rule.** A dash is missing by default. It is admitted as a zero only when a
  published total reconciles with the dash taken as zero, within the profile
  rounding tolerance: the row total of a premium annex (other categories vs
  published total), or the parent total of a balance-sheet hierarchy (a detail
  is written only under a reconciled parent). The proof is stored with the
  record. On a balance sheet a blank cell (nothing printed) stays missing. In a
  premium annex row, whose printed total is an exact identity, a blank or dash
  is admitted under the same proof; with several blanks only their *sum* is
  proven, so they are admitted only when they all map to the same target branch
  (the branch value is then exact while individual values stay unproven).
- **Rationale.** In financial statements a dash conventionally means "nil". The
  identity turns that convention into evidence instead of an assumption. Accident
  du travail is essentially a run-off line for Tunisian insurers since the
  compensation regime moved to social security (law 94-28), so nil issued
  premiums are also economically expected (COMAR prints 0 for it in 2023).
- **Evidence.** COMAR 2024/2025: Travail is a dash; the other 13 categories
  reconcile with the published total at +1 / −1 TND. COMAR balance 2024/2025:
  AC322, AC520, AC530, PA340, PA360 are dashes; for the asset rows the prefilled template
  holds 0 for each of them in 2024/2025, i.e. the same convention.
- **Status.** default.

## D-003 — TAF_G3 branch partition: the five target branches partition direct non-life business

- **Rule.** Automobile, Incendie, Transport, IRDS and Groupe must together cover
  all direct non-life categories exactly once. Acceptations (inward
  reinsurance) are excluded and reported separately (STAR rule). IRDS therefore
  receives every direct category that is not Automobile, Incendie,
  Transport/Aviation or Groupe.
  - STAR: IRDS = Risques divers + Accidents du travail (confirmed rule).
  - COMAR: IRDS = Accident du travail + RC + Dommages aux biens + Risques
    agricoles + Construction + Perte d'exploitation + Caution + Assistance +
    Accident corporel.
- **Rationale.** The template defines "Emissions Non Vie" as the sum of the five
  rows. If any direct category is left outside them, that total no longer equals
  the company's direct non-life premiums and becomes incomparable across
  companies and with CGA statistics. Treating Caution or Agricoles separately
  would need a sixth row that the template does not have.
- **Evidence.** COMAR: the five-branch sum equals the published total minus
  acceptations exactly in 2023 and within ±1 TND in 2024/2025 (rounding).
- **Caveat (FTUSA).** FTUSA's seven statistical branches also partition COMAR's
  direct total exactly (2023, 2024), but reallocate business between branches:
  FTUSA Automobile exceeds the accounting annex by 14.2 M TND. The template is
  sourced from the CMF, i.e. the published statements, so the accounting-annex
  categories are used. If the CMF expects the FTUSA statistical taxonomy, the
  branch split (not the total) changes.
- **Status.** default — to confirm with the supervisor: (1) accounting annex vs
  FTUSA statistical branches; (2) whether Crédit/Caution and Risques agricoles
  belong in IRDS.

## D-004 — Rounding tolerance

- **Rule.** 3 TND for sums of published integer amounts (STAR rule), applied to
  COMAR. Every non-zero delta is recorded even when tolerated.
- **Rationale.** Statements are published in whole dinars, rounded from millimes;
  a sum of n rounded items can differ from the rounded total by up to n/2 TND.
- **Status.** confirmed (STAR), default (COMAR).

## D-005 — Current-year publication wins over a later comparative

- **Rule.** When year N's statement and year N+1's comparative column disagree,
  the year N publication is written; the difference is reported with both
  provenances. Restatements are not applied silently.
- **Rationale.** The template records the figures as published for each closing
  date. A restated comparative is a different measurement and must be flagged
  for review (it may reflect an accounting-policy change).
- **Status.** default.

## D-006 — Reading the CGA aggregates of TAF_G4 (kTND)

- **Rule.** Used as an independent accuracy reference, not as a source:
  Primes nettes = published non-life total (acceptations included) + life total;
  Capital social = CP1; Résultat comptable = CP6; Fonds propres (2) = equity
  *before* the result of the year; Placements nets cumulés (3) = AC3 + AC71
  (investments plus bank and cash). Provisions techniques (1) remain indicative.
- **Evidence.** STAR 2024: every listed metric matches to the kTND
  (fonds propres 400,085 = 429,898 − 29,813; placements 1,140,463 = 1,112,770
  + 27,693). Technical provisions differ by 7,697 kTND from PA3 and from every
  simple combination of published lines, so the CGA basis is unknown.
- **Status.** corroborated on STAR 2024; to recheck on each new company.

## D-007 — Premium history: three readings, OCR only with native corroboration

- **Rule.** A historical year (TAF_G3, no TAF_G1 column) is admitted when annex 13
  categories reconcile with the annex total, the annex total equals the first
  amount of the PRNV11 statement row (gross, year N), and the life total equals
  PRV11 — through annex 12 when published, otherwise through a second page that
  prints the same life total. The unit is the statement's declaration, or that
  of a page printing the same amount. "MD" (millions) is never read as thousands.
  An OCR reading is admitted only if a native page prints the same amount.
- **Rationale.** These are the regulated NC 26 disclosures; three independent
  printings of the same figure make a misread column practically impossible.
- **Evidence.** STAR 2011–2022: 11/11 years admitted, identity deltas 0 or ±1 TND.
  On 2024, where the production reader is known, the generic reader agrees 14/14;
  on 2023 and 2025 (scanned statements) it rejects rather than guessing. The
  2018→2019 life growth (12.7 → 30.0 M TND) is printed on three pages and the
  2019 comparative column confirms the 2018 level.
- **Amendments (COMAR).** Typographic minus signs (U+2010…) before digits are
  minus signs; reconciliation tables (annexes 15/16) are never read as category
  annexes; a document-wide policy sentence ("les positions comptables sont
  exprimées en dinar tunisien") is accepted as unit evidence only when no page of
  the document declares thousands. Without annex 13 no branch value is admitted.
- **Status.** default.

## D-008 — Exact unit conversion and annex units proven by identity

- **Rule.** Thousands of dinars are converted to TND only when every amount has
  at most three decimals, so the result is exact; the printed amount, the source
  unit and the factor 1000 are kept in the evidence. A category annex may use a
  different unit from its statement: among TND and kTND, exactly one must make the
  annex total equal the statement's gross premium in TND, and a declared annex
  unit must agree.
- **Evidence.** ASTREE 2012–2015 print statements in TND and annex 13 in kTND
  (84 404 579 TND = 84 404,579 kTND in 2012).
- **Status.** default.

## D-009 — ASTREE branch mapping

- **Rule.** Groupe = Maladie + Invalidité; Transport = Transport + Aviation; IRDS =
  RC décennale, RC civile, Risques agricoles, Autres dommages aux biens, Assistance,
  Assurance crédit, Individuelle accidents, Loi (accidents du travail), Pertes
  pécuniaires (from 2024); Acceptations excluded (D-003).
- **Evidence.** FTUSA 2024 Groupe maladie for ASTREE = 34 503 323 TND = Maladie
  31 661 853 + Invalidité 2 841 470 (prior review, outputs/astree_classification_20261010).
  CGA 2024 ASTREE primes nettes 253 411 kTND = published non-life 176 216 228 +
  life 77 194 873. Annex 13 is read through ordered layout families: columns that
  change a branch (Auto, Transport, Aviation, Incendie, Maladie, Invalidité, totals,
  Acceptations) must show their header key; IRDS-internal columns are positional.
- **Status.** default — same supervisor question as D-003 for Crédit/Agricoles.

## D-010 — External model APIs may read published annual reports, nothing else

- **Rule.** This is the decision that article XI requires before any document
  leaves the machine. An external model API (for example Groq, Google AI Studio or
  OpenRouter, free tiers included) may receive **only** the text, word positions or
  rendered page images of the insurers' published annual reports in
  `data/sources/`. It never receives the CMF template, output workbooks, run
  reports, values already typed into the template, review notes, or the benchmark
  answer key. Every call is recorded (provider, exact model identifier, prompt
  hash, request, response, latency) so that a benchmark can be replayed offline at
  no cost and with identical results; a run without a recording is not a result.
  API keys come from environment variables and never enter Git. Article IV is
  unchanged: a model proposes readings, the identity gate admits or rejects them.
- **Rationale.** Annual reports are public documents that the companies publish
  themselves, so sending them reveals nothing confidential; free tiers may train on
  their inputs (Gemini's free tier does outside the EEA, Switzerland and the UK),
  which is acceptable for public inputs only. The CMF template and everything derived
  from it are not public. A local machine with an RTX 3050 cannot run a vision model
  good enough for scanned statements, and comparing providers is itself a result.
- **Evidence.** Local `qwen2.5:7b` invented labels and split amounts on the ASTREE 2020
  annex (14 October, PLAN M5). Free-tier limits change often and are checked on each
  provider's console before a benchmark run, not assumed.
- **Status.** decided by the project owner, 1 November 2026.
