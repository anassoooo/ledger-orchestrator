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

## D-002 — A printed dash in a premium annex may be admitted as zero only by proof

- **Rule.** A dash is missing by default. It is admitted as a zero only when the
  published total of the same row reconciles with the other categories with the
  dash taken as zero, within the profile rounding tolerance. The reconciliation
  delta and the source total are stored with the record.
- **Rationale.** In financial statements a dash conventionally means "nil". The
  identity turns that convention into evidence instead of an assumption. Accident
  du travail is essentially a run-off line for Tunisian insurers since the
  compensation regime moved to social security (law 94-28), so nil issued
  premiums are also economically expected (COMAR prints 0 for it in 2023).
- **Evidence.** COMAR 2024/2025: Travail is a dash; the other 13 categories
  reconcile with the published total at +1 / −1 TND.
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
- **Status.** default — to confirm with the supervisor, in particular whether
  Crédit/Caution should be reported elsewhere by the CMF.

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
