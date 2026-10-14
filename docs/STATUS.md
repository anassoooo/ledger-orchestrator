# État du projet — 13 octobre 2026

## Livré

- Cinq agents déterministes coordonnés et tracés : documents, extraction,
  validation, classeur, revue.
- Profils société/modèle versionnés : identité, exercices, chemins locaux,
  adresses Excel, totaux, libellés et empreinte SHA-256 de la configuration.
- Écriture et couverture pilotées par les mêmes adresses explicites. Un scénario
  fictif vérifie d'autres feuilles, colonnes et les exercices non consécutifs
  2018/2020. Ce test ne qualifie aucune société réelle supplémentaire.
- Contrat de faits financiers contrôlé avant l'écriture : période, montant fini,
  unité, conversion, source déclarée, empreinte, page et méthode. Les montants du
  schéma d'échange sont des chaînes décimales ; les données historiques restent
  dans `report.data` pour compatibilité.
- CLI et API utilisent les exercices du profil. `/profiles` fournit le catalogue
  à l'interface et indique les PDF disponibles. Un profil brouillon, un exercice
  non déclaré ou un adaptateur non qualifié est refusé avant le traitement.
- Revue LangGraph persistante et copilote local optionnel en lecture seule.
- Une prime existante contradictoire est conservée ; ses totaux dépendants sont
  explicitement bloqués, même si toutes les cellules contiennent des nombres.

## Vérification

La suite comporte **88 tests réussis dans l'image Docker reconstruite**, sans
réseau ni montage du code source, y compris le recalcul réel
LibreOffice, les conflits de primes, les profils invalides, les adresses fictives,
la provenance et la sélection API des exercices.

La construction standard depuis l'image Python officielle a réussi le 2 octobre.
Les anciens blocages d'accès au registre ne se sont pas reproduits pendant ce build.
Le run `20261002T184507_5724c9f1`, exécuté hors réseau depuis cette image, réussit
tous les contrôles de non-régression face à `20260924T164906_1b40dd9c`.

`scripts/verify_reference.py` régénère réellement le classeur et compare le
traitement aux rapports locaux de référence : documents, valeurs, contrôles,
anomalies complètes, écritures/preuves, couverture, revue, formules, styles et caches
de calcul. La référence reste inchangée. Une seule normalisation de métadonnée est
autorisée : l'ancien chemin OCR `STAR/2025.pdf` devient `sources/STAR/2025.pdf`.
Une comparaison réussie prouve la non-régression, pas la justesse comptable de la référence.

Les tests publics utilisent des données fictives. Les PDF, classeurs et rapports
de référence confidentiels restent hors Git et hors du contexte de build Docker.

## Périmètre réellement qualifié

L'adaptateur de production reste **STAR, états individuels, 2023–2025, TND**.
Changer seulement `company` dans un JSON n'active pas une autre société.

| Exercice | TAF_G1 | TAF_G3 |
| --- | ---: | ---: |
| 2023 | 74 / 81 | 9 / 9 |
| 2024 | 74 / 81 | 9 / 9 |
| 2025 | 58 / 81 | 9 / 9 |

La référence contient 255 écritures de valeurs/formules, 45 anomalies et 37 cellules
à revoir ; statut `needs_review`. Les 233 cellules cibles alimentées sur 270 mesurent
la couverture, pas la précision. Les 255 écritures incluent les compléments et les totaux.

## Pilote ASTREE — 10 octobre

Extraction candidate reproductible des PDF 2023–2025 : 280 positions concordent
avec le pilote initial ; 97 tests réussis et non-régression réelle STAR réussie.
L'exercice 2011 est explicitement refusé. ASTREE reste hors du registre de production,
avec les définitions/mappings des primes et la référence métier encore à valider.
Voir [la qualification ASTREE](ASTREE_QUALIFICATION.md) pour les limites et les preuves.

## Restant

1. Constituer avec le relecteur métier une référence indépendante, et arbitrer les
   conflits signalés. Aucun avis humain n'est simulé par les tests.
2. Qualifier ASTREE sur les documents fournis et leurs correspondances Excel,
   puis tester un exercice ancien avant d'étendre aux autres sociétés.
3. Implémenter et tester les conversions d'unités avant d'admettre des milliers
   de dinars. Actuellement seul le coefficient 1 est qualifié.
4. Faire évoluer la revue documentée vers une résolution avec preuves, nouveaux
   contrôles et régénération d'une version du classeur.
5. Installer et évaluer le modèle local ; il reste désactivé dans l'application.
   Les propositions de correspondances par LLM restent à développer.

La revue actuelle consigne des décisions sans modifier les montants. Les anciennes
observations et les résultats d'audit détaillés sont dans [HISTORY.md](HISTORY.md).
Voir les [contrats de profils](PROFILES.md) et les [critères de la suite](ROADMAP.md).

## Coverage inventory and classification review — 10 October 2026

The local inventory is saved in outputs/coverage_inventory_20261010:
61 PDFs, 2,624 pages, including hashes and per-page text/geometry metadata.
This is document triage, not financial validation. Filename years are unverified.
MAE has no local PDFs; CTAMA has only 2018 and 2020; STAR lacks 2013.
COMAR 2016/2018 and ZITOUNA 2016/2018 have almost no native text.

Latest ASTREE workbook: outputs/astree_mapping_20261010/ASTREE_review_2023_2025.xlsx.
Separate Credit/Agricultural rows and proposed Groupe/Divers are on a new
classification sheet. Seven original sheets preserved byte-for-byte; native
recalculation and missing/zero probes passed. Production activation is unchanged.

COMAR_layout_discovery.json records native 2023–2025 annex locations and geometry.
No COMAR financial values have been admitted. Next technical work: implement
bounded COMAR extraction with identity, unit, category and current-gross checks,
then reconcile against the published statements and annex bridges. Do not map
dashes to zero, copy ASTREE geometry, or assume Caution equals Credit.

Remaining review dependency: company-specific grouped branch definitions and an
independent financial reference. The user's authorization to make implementation
choices does not constitute an independent accounting review. Missing local
company/year files also limit end-to-end coverage of the full requested dataset.

## COMAR native premium candidate — 11 October 2026

scripts/qualify_comar_premiums.py produces read-only evidence for 2023–2025.
Run saved in outputs/comar_premiums_20261011. All 3 annex totals match the main
statement and bridge. 45 source positions: 43 numeric, two unresolved dashes.
2023 complete category sum agrees; 2024/2025 known numeric sums differ by +1/-1 TND.
These are not complete reconciliations because Travail is a dash in both years.
Manual parser probes and source-render inspection passed; no independent human
reference, no workbook writes and no production activation. Header identity and
gross-column admission guards need strengthening before adapting this pilot into
the application. Caution-to-Credit and grouped IRDS mapping are not assumed.

## COMAR header and period guards — 11 October 2026

Latest candidate evidence: outputs/comar_guarded_20261011.
All 15 category headers now checked by column; current/comparative periods and
gross heading checked spatially. Missing/contradictory controls and source changes
are rejected. The 2025 upper header line clipping has been corrected.
16 deliberate corruption probes rejected; 45 real positions and reconciliations
unchanged. No production activation. Next: COMAR balance/life qualification and
explicit target mapping, then shared workflow integration after qualification.

## COMAR qualification audit — 11 October 2026

outputs/comar_qualification_20261011 contains the qualification matrix and 27
balance/life diagnostic source positions. Current and comparative balance totals
agree in all 3 years; life statement/annex/bridge agree. 2025 asset gross minus
provisions minus net differs by +1 TND and is retained. COMAR remains not ready
for integration: detailed balance extraction, life admission, company profile,
canonical facts, workbook mapping and end-to-end validation are unfinished.

## COMAR guarded life candidate — 11 October 2026

The premium script now includes guarded life extraction for 2023–2025.
Latest evidence: outputs/comar_life_20261011. Nine source positions agree across
statement/category annex/bridge; nine corruption probes rejected. All 45 prior
non-life positions unchanged. This supersedes the audit's statement that life
candidate extraction is not implemented; production life admission remains absent.
Resume with detailed balance extraction/qualification, followed by explicit COMAR
profile and canonical/workbook integration. No production adapter enabled.

## COMAR detailed balance candidate — 11 October 2026

scripts/qualify_comar_balance.py and outputs/comar_balance_20261011 provide
232 account/total rows across 2023–2025. Period and column headers checked;
six wrong net-heading probes rejected. Current/comparative balance totals agree.
Explicit hierarchy controls retain missing/dash components and small differences.
PA2 vs PA23 presentation handled by year/source presence. Ten 2023 vs 2024
comparative differences of 1–2 TND retained; 2024 vs 2025 comparable values agree.
No production or Excel admission. Next: verify full code/label coverage against
source pages, define admissible per-record results and explicit COMAR mapping,
then integrate canonical facts and verify a complete workbook plus STAR regression.

## COMAR row coverage, canonical staging and workbook review — 12 October 2026

Latest deliverable: outputs/comar_review_20261012/COMAR_review_2023_2025.xlsx.
It adds COMAR_Bilan, COMAR_Primes and COMAR_Mapping; four original worksheet
parts are byte-identical. Three original template label corrections are proposed
on the review sheet, not applied to TAF_G1. All COMAR readings remain unapproved.

config/qualification/comar_balance_v1.json freezes the six inspected balance
page row/label sequences (265 rows including headings and four previously skipped
unlabeled PA2/PA5 subtotals). qualify_comar_balance.py now rejects missing, extra,
misidentified or relabeled financial rows and contradictory printed subtotals,
and rejects missing numeric grand controls explicitly. Original 232 account
readings are unchanged. 42 row/label probes, four subtotal contradictions and
six missing-grand-control probes rejected. These are disposable manual probes,
not a new full automated-suite run or independent accounting review.

config/comar.json is a validated-by-schema DRAFT profile, not a qualified
production extractor. scripts/prepare_comar_review.py feeds the existing
canonical_facts contract: 502 numeric facts, comprising 228 current balance,
228 comparative balance and 46 premium/life readings. All approved:false.
Comparative evidence for 2022 is retained without qualifying the 2022 document.
The API lists COMAR as non-runnable and rejects its execution with HTTP 422;
STAR remains default and runnable. No production adapter registry change.

All 270 target addresses examined: 156 empty targets, 87 agreeing existing
numeric amounts, 20 empty targets without a candidate, seven existing values
without a numeric source candidate. Those seven include AC721 2024 (12,494,585):
the PDF publishes AC72 but omits this detail, so the template child is not inferred.
Ten 2023/current vs 2024/comparative differences retained with both provenances.
IRDS composition and Caution/Agricoles treatment remain unresolved; published
non-life totals include Acceptation and are kept separate from target branch totals.

LibreOffice recalculation has no formula errors. All 243 balance positions,
48 premium/life positions and 270 mapping destinations checked. Blank/zero
disposable probes passed; missing dependencies remain blank, published zero is
preserved, and 2025 Travail=0 exposes the retained -1 TND difference. Sources and
template unchanged. Actual STAR reference replay 20261011T230247_cee9ed14 passed
all 14 comparisons against 20260924T164906_1b40dd9c.

Reproduction: python scripts/prepare_comar_review.py --root data --profile
config/comar.json --output outputs/<new-directory>. Review.json and verification
sidecars are saved alongside the final workbook. Authoring/packaging/native probe
scripts and previews remain in the authorized conversation scratch directory,
under comar_review.mjs, append_review_sheets.py and comar_workbook_20261011.

Next: company-specific mapping/per-record admission review and a canonical
production adapter, then a real complete COMAR workbook run plus STAR regression.
Independent financial reference review remains pending. Historical company/year
layout qualification can continue separately; none has been promoted by this work.

## COMAR review fixes — 12 October 2026

Latest: outputs/comar_review_20261012_corrected/COMAR_review_2023_2025.xlsx.
README.md, review.json, verification.json, fix_verification.json,
workbook_verification.json and initial_review.md accompany it.

Astra review findings R1/R2 implemented in draft review scripts only.
comar_review_guards.py and config/qualification/comar_template_v1.json check
270 destination identities and 166 identity cells, including balance years,
account labels and the complete premium year formula chain. Mapping validates
the contract itself, including duplicate/profile destination changes. The three
explicit proposed label corrections are accepted alternatives, not silently applied.

qualify_comar_notes.py extracts AC721 from COMAR 2024 p. 21 with explicit AC7,
label/period/layout/numeric checks and printed-parent corroboration. Added current
2024 12,494,585 TND and comparative 2023 12,661,333 TND; retained the 2025
comparative separately. Balance-page manifest unchanged. All 502 earlier facts,
balance/premium candidates, source/template hashes and ten conflicts unchanged.
504 facts now, all unapproved. Exactly one mapping gains a candidate: AC721 2024.
Six existing template amounts still have no numeric current-source candidate.

181 disposable fault probes rejected. Fresh LibreOffice recalculation: no formula
errors; 243 balance positions, 48 premium positions and 270 destinations checked.
Four original worksheet XML parts byte-identical. Nine review-tab cell changes;
all formulas unchanged. Prior blank/zero probes were not repeated; full automated
suite and STAR reference extraction were not rerun. COMAR draft execution rejection
checked directly; production registry/profile status unchanged.

Next: resolve company-specific IRDS/Caution/Agricoles crosswalk, template premium
nettes versus before-reinsurance meaning, and the 73,060 TND COMAR/FTUSA Groupe
2023 reference discrepancy. Keep missing/dash and small differences unresolved
until evidence/policy supports admission. Independent accounting reference review
and canonical production adapter remain outstanding. Broader historical/company
source qualification can continue independently. See corrected README for reproduction.

## COMAR premium basis comparison — 12 October 2026

outputs/comar_premium_basis_20261012 is the latest accounting-meaning checkpoint.
The corrected workbook in outputs/comar_review_20261012_corrected remains current.
qualify_comar_premium_basis.py reproduces guarded FTUSA comparison: 27 reference
cells, two exact direct-total reconciliations (2023/2024), twelve branch comparisons
with nine differences. Life agrees in both years. The 2023 Groupe difference was
already present in FTUSA 2023, not introduced by the following publication.
Exact branch-level allocation/cause remains unproven; no FTUSA number substitutes
for a COMAR accounting-annex value. The interpretation of target net premiums was
already defined in LOGIQUE_METIER.md as net of cancellations, before reinsurance.
NC28 official reference corroborates distinctions from earned premiums and describes
other accounting adjustments. The terminology alone no longer blocks candidate basis.

Two explicit IRDS grouping options are staged, with Agricoles/Caution separate or
included, neither admitted. Six partition checks retain every category once and
preserve missing Travail. Twelve manual fault probes reject wrong metric (including
a real claims table), identities, years, missing values and percentage intrusion.
No new automated suite/STAR run; no source fact or workbook changed. All COMAR
facts remain unapproved; production remains disabled. README and source hashes,
physical page/bbox evidence, verification and reference images saved alongside.

Next: advance historical company/year source qualification using the existing
coverage inventory. Target crosswalk and admission questions remain explicit and
can proceed independently; the completed inventory/extractions need not be repeated.


## Historical header qualification and ASTREE compatibility - 12 October 2026

outputs/historical_headers_20261012 is the current historical source-header
checkpoint. Reused the saved coverage inventory; 61 source hashes rechecked.
Bounded native pass: first four physical pages per PDF, 244 pages. 53 documents
have native company/closing-year/two-period balance-header observations. Eight
exceptions have explicit routes: 14 new header OCR/visual pages from six historical
reports and three existing STAR OCR pages reused by source/cache hash. Original
OCR imperfections remain visible; STAR 2025 comparative date is visually 31/12/2024,
although cached OCR reads 21/12/2024. No cache or financial record was changed.
Spaced EXERCICE year headings supported with original text/bboxes; malformed and
reversed headings rejected. Eleven disposable negative header probes, two positive
controls, and recheck of all 61 saved observations passed. No project suite run.

Material layout findings: STAR 2019-2021 distinct restated/published comparatives;
CTAMA 2018 three-decimal and trailing-minus amounts; Zitouna 2019-2025 combined
policyholder/operator/combined columns (2020 via visual evidence); Zitouna 2011
creation phase. These are bounded observations, not ready-to-run layouts. Missing
local inputs remain MAE, STAR 2013 and 13 CTAMA filename years within 2011-2025;
this interval is not a claim of public filing requirements or company activity.

outputs/astree_historical_balance_20261012 checks 12 historical ASTREE reports
(2011-2022) against unchanged recent internal balance guards. 22/24 sections reject;
2017/2021 liabilities produce 66 unapproved rows, no complete historical balance.
Observed blockers include shifted period/net bands, changed account rows, note
references entering monetary bands, dashes and missing amounts. No year gate was
relaxed and no adapter/profile was enabled. Reports retain source/extractor hashes,
page/bbox evidence and reasons. Scripts are standalone diagnostics, outside registry.

Next implementation: inspect ASTREE 2022 historical balance columns and account-row
manifest (completed 13 October), then qualify 2021 as a possible related layout
family. The 2021 visual review suggests the same broad column structure but is not
machine-qualified. Keep recent admission intact.
COMAR corrected review workbook and premium-basis comparison remain current in
comar_review_20261012_corrected and comar_premium_basis_20261012. Classification,
independent accounting review and admission remain unresolved. Production still
supports STAR 2023-2025 only; header triage does not increase financial coverage.

## Diagnostic ASTREE 2022 — 13 octobre

L'inspection détaillée des pages 2–3 confirme une famille distincte : l'actif
publie Brut, Amortissements, Net et comparatif ; son manifeste omet AC520 et laisse
AC550 vide. Au passif, PA350 est un zéro publié, situé juste au-delà de la borne
récente de la colonne courante. Le probe historique dédié détecte ce zéro avec
une bande géométrique propre à 2022.

Le probe produit localement 149 faits candidats pour 2022 et les comparatifs 2021,
avec source, empreinte, page, colonne et rectangle de preuve. Les cibles Excel
restent indéfinies et tous les faits sont non approuvés. Les lignes du passif se
rapprochent exactement, ainsi que les deux totaux imprimés du bilan. Le sous-total
des catégories d'actif diffère toutefois du total imprimé de 1 TND. Ce point reste
ouvert ; le classeur et le reader 2023–2025 n'ont pas été modifiés. Détails dans
[le dossier ASTREE](ASTREE_QUALIFICATION.md).

## Revue visuelle ASTREE 2021 — 13 octobre

Les pages 2–3 de l'état 2021 montrent la même structure générale que 2022,
notamment Brut/Amortissements/Net/comparatif à l'actif et deux périodes au passif.
Cette observation visuelle sert à orienter l'adaptateur historique ; aucune
coordonnée, ligne ou valeur 2021 n'est encore qualifiée par machine. Aucun fichier
financier ni classeur n'a été modifié. Prochaine étape : vérifier bandes et
manifestes 2021, puis contrôles ligne à ligne.

## COMAR en production et mesure de précision — 14 octobre

Gouvernance : [constitution](CONSTITUTION.md), [décisions](DECISIONS.md) et
[plan](PLAN.md). Les lecteurs COMAR qualifiés sont déplacés sans modification
dans `extraction/comar.py` (sorties identiques vérifiées sur 2023–2025) et
enregistrés comme `comar_individual_v1`. Le profil COMAR est validé.

Run de référence `20261014T011713_cc31123a` : TAF_G1 81/81 en 2024 et 2025, 78/81 en 2023
(trois rubriques non publiées), TAF_G3 27/27, aucun conflit. Les 94 valeurs
saisies dans le modèle pour 2024/2025 servent de référence indépendante :
92/92 comparables concordent. TAF_G4 (CGA 2024) : 5/5 indicateurs définis
concordent pour COMAR comme pour STAR (D-006).

Règles appliquées : partition des branches (D-003, Acceptations exclues), tiret
admis comme zéro seulement si un total publié le prouve (D-002), tolérance 3 TND
(D-004), publication de l'exercice prioritaire sur le comparatif ultérieur (D-005).
Un total saisi égal au total publié est « confirmé » et non plus signalé en conflit.

Vérification : 123 tests Docker réussis, non-régression STAR 14/14, rejeu COMAR 14/14.
Outil de mesure : `python -m ledger_orchestrator.evaluation coverage|benchmark`.

## Classeur consolidé — 14 octobre

`python -m ledger_orchestrator.consolidate --configs config/star.json config/comar.json`
exécute chaque profil à la suite sur la même copie du modèle et vérifie que toutes
les écritures sont conservées, qu'aucune cellule n'est écrite deux fois et que les
sociétés sont distinctes. Couverture du modèle complet : TAF_G1 446 / 1 245 cellules
disposant d'une source (35,8 %), TAF_G3 36 / 312 (11,5 %). Aucune erreur de formule.
Une feuille de compléments n'est créée que si des rubriques publiées n'ont pas de ligne.

## Historique des primes STAR 2011–2022 — 14 octobre

Lecteur générique des annexes réglementaires (NC 26) : annexe 13 non-vie, annexe 12
vie, ligne PRNV11/PRV11 des états de résultat technique. Une année est admise si les
catégories rapprochent le total de l'annexe, si ce total égale le brut de l'état et
si le total vie est imprimé une seconde fois (D-007). En-tête inconnu, colonne
ambiguë, unité non déclarée ou écart : l'année est rejetée avec son motif.

STAR : 11/11 exercices admis (écarts 0 ou ±1 TND), TAF_G3 84/96 ; 2010 et 2013 n'ont
pas de document source. Évaluation sur 2024, où le lecteur de production est connu :
14/14 valeurs identiques ; 2023 et 2025 (états scannés) rejetés plutôt que devinés.
Classeur consolidé STAR + COMAR + historique STAR : TAF_G3 102/312, aucune erreur.
Vérification : 137 tests, non-régression STAR 14/14, rejeu COMAR 14/14.
