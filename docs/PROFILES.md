# Profils et contrats financiers

## Configuration versionnée

`config/star.json` est le premier profil de schéma 1. `profile_id`, `revision` et
l'empreinte du JSON canonique sont enregistrés dans chaque nouveau rapport.
`status: validated` est une décision de qualification maintenue dans le dépôt ;
ce champ ne constitue pas une certification externe.

Le profil déclare :

- l'entreprise, les termes d'identité du document et le répertoire local des PDF ;
- l'adaptateur d'extraction et les exercices admis ;
- le modèle Excel et le nom du classeur produit ;
- les ancrages d'identité, les feuilles et les colonnes explicites par exercice ;
- les lignes de détail, les dépendances des totaux et les corrections de libellés ;
- la feuille complémentaire et la politique métier déjà confirmée.

`CompanyProfile` rejette notamment les collisions de cellules, les années sans
colonnes, les cycles de totaux, les coordonnées hors Excel et les chemins sortant
des répertoires locaux. Les PDF doivent se trouver sous `sources/` et les modèles
sous `templates/`. Les feuilles cibles utilisent des noms ASCII alphanumériques
ou des underscores pour assurer leur compatibilité avec les identifiants de revue.

Le moteur Excel et la couverture utilisent les mêmes colonnes déclarées. La présence
d'un PDF ne suffit jamais à admettre son exercice : son identité et ses en-têtes
sont encore contrôlés pendant l'extraction.

## Qualification d'un adaptateur

`extraction/adapters.py` isole les règles STAR de l'infrastructure. Le seul adaptateur
exécutable aujourd'hui est `star_individual_v1`, limité à STAR 2023–2025. Le profil
fictif des tests sert à vérifier le moteur Excel, pas à annoncer une seconde société
prise en charge. Une nouvelle société nécessite une stratégie d'extraction qualifiée
sur ses documents, en plus de son mapping de classeur.

Les règles de correspondance STAR, les contrôles et les totaux restent inchangés
sur la référence. Une prime existante conflictuelle est désormais exclue de
l'admission des totaux dépendants : leurs formules renvoient un blanc jusqu'à
une régénération après résolution. `COUNT` seul ne prouve pas l'admission.

## Faits financiers

Les nouveaux rapports portent `schema_version: 2` et contiennent `facts`, une liste
de faits de schéma 1. Chaque fait contient :

- société, exercice cible, état (`balance` ou `premiums`), code et admission ;
- `source_amount`, `target_amount` et `target_unit` ;
- preuve : chemin local, SHA-256, exercice du document, page, méthode, unité PDF,
  coefficient de conversion, rectangle et colonne courante/comparative.

Les montants sont sérialisés en chaînes décimales pour un contrat d'échange explicite.
Cela ne change pas l'arithmétique historique du moteur et ne revendique pas une
conversion généralisée. Une unité non confirmée donne `target_amount: null` et
interdit l'admission. Seul le coefficient 1 est qualifié actuellement.

Un comparatif N−1 conserve l'exercice réel et l'empreinte du document N. Une source
non déclarée, une page hors document ou un montant non fini arrête le traitement
avant le classeur. `approved` reprend l'admission par les règles ; ce n'est pas une
probabilité ni une validation humaine.

## CLI, API et interface

Sans `--years`, la CLI traite les exercices déclarés dans le profil sélectionné :

```powershell
docker compose run --rm engine python -m ledger_orchestrator --config /app/config/star.json
```

`GET /profiles` indique les profils configurés, leur qualification et les PDF
disponibles. `POST /runs` accepte un identifiant déclaré côté serveur :

```json
{"profile_id":"star","years":[2023,2024,2025]}
```

Omettre `profile_id` conserve le profil `CMF_CONFIG`. Omettre `years` utilise ses
exercices. L'API n'accepte pas de chemin de configuration ou de PDF fourni par le client.

Le catalogue comprend les profils d'états (`config/*.json`) et d'historique des
primes (`config/history/*.json`), distingués par `kind`. La même commande
`python -m ledger_orchestrator --config …` exécute l'un ou l'autre selon son `kind`.
`POST /consolidations` prend une liste ordonnée d'identifiants :

```json
{"profile_ids":["star","comar","star_premium_history","comar_premium_history","astree_premium_history"]}
```
La revue ouvre le chemin de preuve enregistré, y compris lorsqu'un comparatif
provient du PDF de l'exercice suivant. Le téléchargement utilise le nom enregistré
dans le rapport.

## Non-régression confidentielle

Depuis la stack Docker, avec la référence confidentielle déjà présente localement :

```powershell
docker compose run --rm engine python scripts/verify_reference.py --root /data --output /output --reference /output/20260924T164906_1b40dd9c
```

Le script crée un nouveau run et un `reference_verification.json`. Il compare les
données et le classeur recalculé avec la référence sans modifier celle-ci. L'ancien
script `verify_orchestration_reference.py` reste un diagnostic partiel : il réutilise
le classeur de référence et ne teste pas l'écriture réelle.

## COMAR draft review — 12 October 2026

config/comar.json is a schema-valid draft with explicit 2023–2025 destinations.
It cannot execute through CLI/API, and its extractor is absent from the production
registry. IRDS and the treatment of Caution/Agricoles have not been qualified.
Its three label corrections are proposals; the original workbook is unchanged.
Draft rounding tolerance is zero, with no implicit tolerance admission.

scripts/prepare_comar_review.py stages guarded readings through canonical_facts
without changing their approved:false status. Both current and comparative
readings retain the source document's year, hash, page, rectangle and column.
Missing/dash readings remain in the candidate observations. Printed, unlabeled
group subtotals are retained separately and directly corroborated; PA2 current
facts in 2023/2025 use these printed amounts, not an inferred single-child sum.

outputs/comar_review_20261012 contains the review workbook, canonical staging
report, source/mapping findings and verification. This exercises the shared fact
contract and target-address contract; it does not implement production admission
or claim broad company/year coverage.

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
manifest, then work backward by evidenced families; keep recent admission intact.
COMAR corrected review workbook and premium-basis comparison remain current in
comar_review_20261012_corrected and comar_premium_basis_20261012. Classification,
independent accounting review and admission remain unresolved. Production still
supports STAR 2023-2025 only; header triage does not increase financial coverage.
