# Logique métier — extraction STAR

Règles confirmées par le responsable du projet. Configuration exécutable : `config/star.json`.

## Périmètre et unités

Le MVP traite les états financiers individuels STAR 2023, 2024 et 2025 et produit un
classeur consolidé à partir d'une copie du modèle. Les autres sociétés et exercices
restent inchangés. Aucun montant n'est inventé pour 2013.

L'unité cible est le dinar tunisien (TND). L'unité source et le coefficient de conversion
sont conservés dans les preuves. Les pages acceptées actuellement sont en dinars :
coefficient 1. Une unité inconnue ou exprimée en milliers bloque la donnée tant que
sa conversion n'est pas explicitement prise en charge. Le nom du PDF ne suffit pas
à déterminer l'exercice ; les colonnes N et N−1 sont vérifiées dans le document.

## TAF_G1 — bilan

La zone STAR commence à la ligne 51. L'actif 2025, 2024 et 2023 va respectivement dans
les colonnes C, D et E. Les capitaux propres et passifs vont dans K, L et M.

Les détails publiés alimentent des valeurs numériques. Les totaux sont des formules
recalculées, rapprochées des totaux publiés conservés comme preuves indépendantes.
La somme n'inclut jamais à la fois un sous-total et ses propres détails.

Le modèle omet plusieurs rubriques STAR. Une feuille visible `STAR_Details` conserve
les rubriques complémentaires nécessaires aux calculs, dont les résultats reportés,
AC541, AC732 et les écarts de conversion. Les formules du bilan pointent vers ces
détails lorsqu'ils sont nécessaires. La feuille ne remplace pas les rubriques existantes.

Les différences de nomenclature sont explicites :

| Rubrique STAR | Traitement du modèle |
| --- | --- |
| CP5 — résultat reporté | Ajout dans STAR_Details |
| CP6 — résultat de l'exercice | Correction de l'intitulé I58 et alimentation du résultat |
| PA360 — autres provisions techniques vie | Correction du code PA380 en I71 |
| PA710 — report de commissions reçues des réassureurs | Correction du libellé I85 |

Les sous-totaux utilisent les enfants publiés identifiés par le dictionnaire. Les
rubriques non trouvées restent absentes, jamais transformées en zéros. Un total n'est
autorisé que si les détails retenus rapprochent le total publié. Une formule exige
ensuite que tous ses détails référencés soient effectivement présents dans Excel.

La tolérance technique d'arrondi actuelle est de 3 TND. Chaque écart est enregistré,
même lorsqu'il est toléré. Cette tolérance n'autorise ni correction des détails ni
invention d'un montant d'ajustement.

## TAF_G3 — primes émises par branche

« Primes nettes » signifie ici nettes d'annulations, **avant cessions en réassurance**.
On utilise la ligne « Primes émises » des annexes par catégorie. Les primes acquises,
les variations de provisions et les opérations nettes de réassurance ne sont pas
des substituts à cette mesure.

| Ligne cible | Agrégation retenue |
| --- | --- |
| Automobile (4) | Automobile / Auto |
| Incendie (5) | Incendie |
| Transport (6) | Transport + Aviation |
| IRDS (7) | Risques divers + Accidents du travail |
| Groupe (8) | Groupe |
| Émissions non-vie (9) | Somme des lignes 4 à 8 |
| Vie (10) | Total des primes émises vie publié et rapproché de ses catégories |
| Émissions vie (11) | Ligne 10 |
| Primes vie et non-vie (12) | Ligne 9 + ligne 11 |

Les colonnes O, P et Q représentent 2023, 2024 et 2025.
Leur largeur est adaptée dans la copie pour afficher les montants TND sans `####` ;
cette largeur s'applique à la colonne entière, sans modifier les valeurs des autres sociétés.
Les colonnes K à M de TAF_G1 sont également élargies pour rendre les totaux lisibles.

Les **Acceptations non-vie** sont conservées séparément dans les preuves et le rapport
d'anomalies. Elles ne sont affectées à aucune des cinq branches sans ventilation.
Le total non-vie du classeur exclut donc ces Acceptations. Il ne doit pas être présenté
comme le total publié, qui les inclut. Le contrôle source vérifie toutes les catégories,
Acceptations comprises ; le contrôle cible applique exactement les cinq branches convenues.
Pour la vie, le total publié est utilisé ; une éventuelle Acceptation vie fait partie
de son rapprochement et reste identifiée dans les preuves.

## Valeurs absentes, conflits et confiance

- Une information introuvable ou douteuse laisse une cellule vide.
- Un zéro n'est écrit que s'il est effectivement extrait d'une source admissible.
- Une valeur existante différente est conservée et une anomalie contient les deux valeurs.
- Les totaux 2023–2025 reçoivent une garde COUNT pour ne pas masquer des entrées manquantes.
- L'original n'est jamais modifié ; chaque exécution produit sa propre copie consolidée.

Le niveau `high` est une catégorie de preuves, pas une probabilité annoncée à 95 %.
L'écriture exige les contrôles applicables et une preuve admissible : extraction native
ou lecture OCR corroborée. Dans la première implémentation, la corroboration OCR du
bilan utilise le comparatif natif de l'exercice suivant, avec concordance exacte et
validation de cette source. Une différence entre N et le comparatif N−1 est signalée,
jamais écrasée silencieusement.

### Preuves supplémentaires intégrées le 16 septembre 2026

Les notes natives de l'actif 2025 peuvent compléter le bilan. Leur périmètre est borné
par les titres des notes de l'actif et du passif, avec contrôle des dates et de l'unité.
Seuls les codes explicites et les libellés du dictionnaire sont admis. Une ventilation
différente n'est pas assimilée arbitrairement aux sous-rubriques du bilan. Un détail
natif peut être admis grâce au rapprochement brut − amortissements/provisions = net.
Les sous-totaux gardent leurs exigences de détails. Un échec arithmétique est bloquant,
même si une autre somme globale paraît correcte. Les montants ne sont jamais ajustés.

Pour les primes non-vie OCR, la règle `native_gross_total_and_category_identities_v1`
exige simultanément :

- date, unité et position des neuf en-têtes de catégories reconnues ;
- total des primes émises strictement identique au montant brut de la note native PRNV1 ;
- contrôle brut − cessions = net dans cette note native ;
- somme des huit catégories rapprochée du total pour chacune des trois lignes :
  primes émises, primes acquises et variation des primes non acquises ;
- identité primes émises + variation = primes acquises vérifiée pour chaque catégorie
  et pour le total, dans la tolérance de 3 TND.

Tous les contrôles et les sources sont conservés. Une seule somme globale ou deux
lectures OCR concordantes ne suffisent pas. Cette règle rend les primes 2023/2025
admissibles sans les qualifier de lectures natives ni garantir une absence d'erreur.

Le rapport `coverage` compte les cellules cibles configurées de TAF_G1 et TAF_G3,
totaux inclus et STAR_Details exclue. Il distingue données remplies, cellules vides
ou bloquées, conflits et valeurs existantes non revalidées. Ce taux de couverture
ne mesure ni la précision statistique ni le pourcentage d'achèvement du logiciel.

### Compléments et revue des cellules

Une rubrique absente de l'extraction de N peut être complétée par sa colonne N−1
explicitement publiée dans le bilan natif de N+1. Conditions : montant numérique
présent (zéro compris), rubrique non ambiguë, unité vérifiée, source N+1 admissible
et contrôles du bilan N recalculés. Aucune valeur déjà extraite n'est remplacée.
Le rapport conserve `source_year`, `source_column` et la preuve d'origine dans
`source_events` et dans l'enregistrement. Ce n'est pas une imputation de zéro.
Seuls les documents déjà chargés pour les exercices demandés servent à ce complément.

AC34 peut être vérifié indépendamment par les deux lignes natives de dépôts en
garantie PPNA et PSAP, rapprochées du total publié. Une composante manquante ou
dupliquée ne permet pas cette validation.

`cellules_a_revoir.csv` explique chaque cellule cible non renseignée ou non revalidée :
motif, action, source et dépendances. « Non détecté » ne signifie ni « non publié »
ni « zéro » ; cette distinction est conservée tant que la présence de la rubrique
n'a pas été établie. Les décisions humaines ne doivent pas masquer un défaut OCR.

Pour AC33 de 2025 uniquement, le profil OCR ciblé peut fournir le sous-total publié
si ses lectures concordent, si son comparatif est exactement égal au montant natif
2024 validé et si ses détails 2025, tous natifs et admissibles, rejoignent exactement
ce sous-total. Aucun chiffre n'est corrigé pour satisfaire cette égalité. Les rubriques
non détectées restent absentes, sans zéro ajouté. La preuve et les composantes sont
conservées dans `subtotal_corroboration`. Cette autorisation limitée ne s'étend pas
aux autres montants du profil OCR.

## Traçabilité et limites

Le diagnostic OCR est strictement séparé de l'admission comptable. Il compare
les candidats aux références natives et aux sous-totaux publiés, sans modifier
les enregistrements, approuver un montant ou écrire dans Excel. Un écart OCR/natif
ne prouve pas une erreur du document et une égalité de somme ne prouve pas chacun
des détails. Pour comparer une famille entière, tous ses enfants configurés doivent
être présents dans les candidats. La reconstruction des bandes d'image sert à la
lecture diagnostique uniquement.

Le libellé exact MMB, uniquement dans la note AC2 de STAR 2025, correspond à
AC22. Son net publié est utilisé seulement si le contrôle brut − amortissement =
net réussit. Le montant manquant d'AC21 n'est jamais déduit du total AC2.

La revue distingue les codes absents d'une page de bilan native vérifiée des codes
simplement non détectés. Cette qualification exige les deux dates attendues, au
moins huit codes et une seule page candidate pour le côté actif ou passif. Elle
ne prouve pas une absence dans toutes les notes et ne justifie jamais un zéro.
Les pages OCR ne permettent pas cette qualification. La page et les codes observés
sont conservés dans `presence_evidence` du rapport.

Le rapport conserve : exercice, société, rubrique source et normalisée, valeur,
unité, conversion, fichier, SHA-256, page, coordonnées, méthode d'extraction,
contrôles, décision d'écriture, cellule et ancienne valeur. Les Acceptations et les
détails non mappés restent visibles dans les résultats structurés.

Un statut `needs_review` signifie que le fichier est partiel ou contient des alertes.
Il ne constitue pas une attestation de complétude comptable. Les règles validées ne
dispensent pas de traiter les défauts OCR, notamment l'actif scanné 2025.

Tout le traitement est local. Aucun modèle cloud ni API externe n'est appelé avec les
documents. Le modèle local pour les cas ambigus reste une extension future ; les
règles actuelles utilisent du code, un dictionnaire et des contrôles comptables.
