# LedgerOrchestrator Constitution

These articles govern every change to the project. A change that conflicts with
an article must amend the article first, in its own commit, with a rationale.

## Mission

Fill the CMF template `TAF_G1_G2_G3_G4.xlsx` from the insurers' published
financial statements, with every number traceable to its source and checked by
accounting identities, so that an actuary or analyst can trust, audit and reuse it.

The project demonstrates two things together: production-grade AI engineering
(evaluation, provenance, controlled automation) and correct insurance accounting
(Tunisian sector standards NC 26–31, premium bases, branch structures).

## North-star metrics

1. **Verified coverage**: target cells of the template filled with values that
   passed at least one independent identity, divided by target cells for which a
   source document exists. Reported by sheet, company and year.
2. **Measured accuracy**: agreement with independent references (values already
   present in the template, CGA aggregates in TAF_G4). Reported with the number
   of compared cells; never extrapolated beyond them.
3. **Silent errors: zero.** A wrong value written without a flag is the worst
   possible outcome; a blank with a reason is acceptable.

## Articles

**I. Evidence before value.** Every written number carries file, SHA-256, page,
bounding box, extraction method, source unit and conversion factor. No evidence,
no write.

**II. Blank is not zero.** An undetected row stays blank. A printed zero is a
zero. A printed dash is *missing* unless a published total proves that it is nil
within the rounding tolerance (decision D-002); the proof is stored.

**III. Identities are the verifier.** An admitted amount must be covered by at
least one independent accounting identity: parent = sum of children,
gross − provisions = net, statement = annex = reconciliation table, current year =
next year's comparative, company total = CGA aggregate. Tolerances are explicit,
small (rounding only) and every non-zero delta is recorded.

**IV. Models propose, identities dispose.** A language or vision model may
propose a reading, a label correspondence or an explanation. It never admits a
financial value. Its proposals pass the same gates as deterministic extraction
and are evaluated against known answers before use.

**V. Business semantics are explicit, versioned and justified.** Premium basis,
branch groupings, acceptations, life/non-life scope and takaful funds are
written in the profile and in `DECISIONS.md` with their actuarial rationale and
supporting evidence. A default awaiting supervisor confirmation is labelled as such.

**VI. Coverage drives priorities.** Work is ranked by the target cells it unlocks.
Work that fills no template cell (for example balance sheets for years the
template does not contain) needs an explicit justification in the plan.

**VII. Flag, don't freeze.** A value that passes its identities is written and
marked; conflicts with existing cells are preserved and reported; everything else
goes to the review queue with a reason. "Unapproved forever" is not a state.

**VIII. Conflicts are never resolved silently.** An existing template value that
differs from the source is kept; both values and both provenances are reported.

**IX. Non-regression is mandatory.** The STAR reference replay
(`scripts/verify_reference.py`) and the full suite (`scripts/docker_test.sh`) pass
before any merge. Each milestone adds tests, including negative (rejection) cases.

**X. Small milestones, always committed.** Each milestone has acceptance
criteria in `PLAN.md`, lands as reviewable commits, and updates `STATUS.md` with
facts, not intentions. Nothing stays uncommitted overnight.

**XI. Local-first and confidential by default.** PDFs, workbooks and run outputs
never enter Git. Runtime code does not send documents to external services
unless a decision explicitly allows it.

**XII. One code path.** Qualification scripts may explore; anything that writes
the template lives in the package, behind the profile registry, with tests.
