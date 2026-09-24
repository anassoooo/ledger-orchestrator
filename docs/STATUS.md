# État du MVP

## Mise à jour du 24 septembre 2026

L'exécution passe désormais par cinq agents déterministes : documents, extraction,
validation, classeur et revue. Un orchestrateur vérifie leurs dépendances, arrête
la chaîne sur erreur et écrit les transitions dans `report.json`. Une vue compacte
est disponible via `GET /runs/{run_id}/agents`. Il ne s'agit pas encore d'agents IA
autonomes ni d'une prise en charge validée des autres entreprises.

Les 59 tests locaux passent, dont deux ignorés ici sans LibreOffice ni FastAPI. Une comparaison
avec le run STAR de référence confirme les montants extraits et les branches,
les types d'anomalies, la couverture et la file de revue. Le test Docker complet
n'a pas été rejoué le 24 septembre : le service Docker Desktop était indisponible
sur cette session. Cette comparaison réutilise le classeur de référence : elle
ne valide donc pas à nouveau l'écriture Excel et le recalcul LibreOffice.

## État de référence au 17 septembre 2026

## Fonctionnel et vérifié

Docker Desktop fonctionne. Commande et API locale sont opérationnelles : lancement,
suivi, rapport et téléchargement. Le classeur téléchargé a été comparé au fichier
local par SHA-256 : identité confirmée lors de la vérification précédente. Les 53 tests passent dans Docker, dont le
recalcul LibreOffice réel, les conflits et les regroupements de branches.

Les règles confirmées sont actives : TND, STAR_Details, primes avant réassurance,
Transport + Aviation, IRDS + Accidents du travail, Acceptations non-vie exclues.
La documentation complète est dans LOGIQUE_METIER.md.

La dernière exécution `20260917T125647_54b032c5` produit 255 écritures de valeurs/formules (pas 255 montants indépendants).
Le résultat reste partiel : statut needs_review. Les sources restent inchangées.

La couverture mesurée des cellules configurées, totaux inclus, est :

| Exercice | TAF_G1 | TAF_G3 |
| --- | --- | --- |
| 2023 | 74 / 81 | 9 / 9 |
| 2024 | 74 / 81 | 9 / 9 |
| 2025 | 58 / 81 | 9 / 9 |

Les 233 cellules remplies sur 270 ne constituent pas un taux de précision. Les
rubriques non publiées restent incluses dans le dénominateur et ne sont pas mises à zéro.

## Travail restant

- Actif 2025 : notes natives pages 24–28 intégrées, avec correspondances limitées aux
  codes et libellés identifiés. Les ventilations différentes restent non mappées.
- AC613 et AC62 : écarts brut − provision − net de +900 et −900 TND dans la note
  page 27, bloquants. Aucun ajustement automatique pour équilibrer les montants.
- Primes non-vie OCR 2023/2025 : corroborées par total natif et identités comptables
  par catégorie, désormais écrites. Les Acceptations restent exclues du total cible.
- Rubriques absentes : cellules vides, sans supposer des zéros.
- Acceptations non-vie exclues des cinq branches, signalées dans les rapports.
- Interface de résolution humaine, modèle local et conversion de milliers de dinars
  non implémentés. Le périmètre opérationnel reste STAR 2023–2025.
- Le profil OCR ciblé ne permet que l'admission stricte d'AC33 2025, corroboré
  par ses composantes natives et le montant natif 2024. Les autres candidats restent exclus.
- Les 37 cellules restantes sont expliquées dans `cellules_a_revoir.csv` (motif,
  action, source et dépendances). Aucune absence de détection n'est déclarée être zéro.
- Répartition : 8 codes absents des pages natives de bilan vérifiées, 19 montants
  non détectés, 8 totaux bloqués et 2 incohérences source. L'absence sur une page
  native ne signifie pas absence dans l'ensemble des notes.
- AC22 2025 est complété par la ligne MMB de la note AC2, avec contrôle du net.

Le fichier généré est un classeur de revue, pas une livraison comptable complète.

## Diagnostic complémentaire sans écriture comptable

`cmf.diagnostics` compare les candidats OCR au texte natif et contrôle les familles
complètes. Le diagnostic de la dernière exécution relève 14 écarts/contrôles
à examiner. Ils ne sont pas 14 nouvelles anomalies comptables confirmées : les
candidats restent non validés, même si deux lectures OCR concordent.
Le fichier Excel n'a pas changé pendant cette investigation.

L'audit en lecture seule des 255 écritures (73 formules) ne détecte pas d'écart
interne, mais signale 23 cellules et totaux dépendants à revoir. Une nouvelle
lecture PDFium, indépendante du cache et de pdfplumber mais utilisant les
coordonnées enregistrées, confirme numériquement 234 références sur 252.
Il reste 15 références scannées et 3 références de totaux non confirmées.
Ces nombres comptent des références sources, pas des cellules distinctes, et ne
certifient ni la correspondance sémantique ni l'absence de contradictions entre pages.
Rapports : `outputs/audit_cellules_20260917/`.

La revue visuelle suivante clôt les 18 références numériques restantes, sans
modifier les résultats du premier passage. AC633 2025 est confirmé à 5 014 076 TND
sur le bilan et la note. AC541 2025 reste contradictoire entre ces deux sources
(écart 100 000 TND) : la cellule et AC5 sont à arbitrer. La synthèse à jour est
`outputs/audit_cellules_20260917/SYNTHESE_AUDIT.md`. La revue sémantique exhaustive
et la résolution de toutes les contradictions ne sont pas terminées.

Le 18 septembre, les états financiers publics téléchargés du CMF sont confirmés
identiques à notre PDF source (SHA-256). Le rapport annuel 2025, page 26 individuelle,
fournit des montants natifs pour des rubriques bloquées, mais introduit des conflits
AC33/AC336 et des différences de 1 TND. Aucune substitution globale ni écriture
Excel effectuée. Voir `outputs/cmf_verification_20260918/COMPARAISON_CMF.md`.

Le mode `cmf.ocr_probe --raw` reconstitue les bandes d'images qui se chevauchent
avec une ligne. AC322 peut ainsi être examiné, mais les lectures anglaise et
française divergent encore. Aucun assouplissement des règles d'admission.
