# ASTREE : extraction candidate — 10 octobre 2026

## Résultat de cette étape

Le module `extraction/astree_candidate.py` remplace le script exploratoire local
par une extraction reproductible des mises en page natives ASTREE 2023–2025.
Il reste séparé du registre de production : `get_extractor` refuse toujours ASTREE.
Aucun profil validé ASTREE n'a été ajouté. Tous les enregistrements produits portent
`approved: false` et le résultat porte `production_enabled: false`.

Le candidat vérifie l'identité et le périmètre individuel du document, la géométrie
et la méthode native, les dates et leurs positions, la colonne nette des actifs,
les unités TND non multipliées, les codes attendus, les doublons, la liste des branches
et les totaux publiés des primes. Les regroupements de codes publiés restent groupés.
Les blancs ne deviennent pas des zéros. Les bases d'acceptation restent distinctes.
Les différences de rapprochement sont exposées, jamais corrigées automatiquement.

La frontière basse de l'en-tête est la première ligne comptable : en 2024, le mot
« Net » se trouve plus bas qu'en 2023 et 2025. Le premier passage sur documents
réels a identifié cette différence ; le contrôle a été corrigé et le scénario
synthétique 2024 la couvre désormais.

## Vérifications effectuées

- 97 tests CMF réussis, dont 9 nouveaux tests de qualification ASTREE comportant
  plusieurs variantes de rejet. Après le dernier resserrement des unités, les
  9 tests ASTREE ont été rejoués avec succès.
- Exécution hors réseau dans l'image locale existante, avec le code et les tests
  modifiés montés en lecture seule. L'image de production n'a pas été reconstruite.
- Les 231 positions de bilan et 49 lignes de primes concordent avec le premier
  pilote, y compris les valeurs comparatives, coordonnées et empreintes documentaires.
  Cette comparaison ne constitue pas une référence comptable humaine indépendante.
- L'exercice 2011 fourni est refusé explicitement : sa mise en page reste à qualifier.
- Écarts actifs/passif et catégories d'actif : zéro sur les trois exercices.
  Écarts des catégories de passif : 0 / 1 / 1 TND, conservés.
- Non-régression réelle STAR réussie : run `20261009T231637_6f2c245c`, comparé à
  `20260924T164906_1b40dd9c`. Tous les contrôles sont vrais, dont les écritures,
  anomalies, couverture, revue, formules, styles et valeurs recalculées LibreOffice.
  Les identifiants de run sont horodatés en UTC.

Les preuves locales restent hors Git :
`outputs/astree_candidate_20261010_final/evidence.json` et `verification.json`.
Le classeur du premier pilote est inchangé dans `outputs/astree_qualification_20261009`.

## Rejouer

Depuis un environnement CMF installé avec accès aux données locales :

```sh
python scripts/qualify_astree.py --root /data \
  --reference /output/astree_qualification_20261009/evidence.json \
  --output /output/astree_candidate_nouveau_run
```

Utiliser un nouveau répertoire à chaque passage ; le script refuse d'écraser un
résultat. Il ne modifie ni PDF ni classeur. Les fichiers du candidat doivent être
présents dans l'environnement utilisé ; l'ancienne image seule ne les contient pas.
Les fixtures des tests sont synthétiques et ne contiennent aucun montant confidentiel.

## Avant activation

1. Décider de la définition des primes attendues : tableau de production et primes
   nettes comptables ne sont pas interchangeables.
2. Faire relire les correspondances IRDS/Groupe/Transport et le périmètre des
   acceptations ; ne pas importer implicitement les règles STAR.
3. Constituer la référence métier indépendante et qualifier le profil/adaptateur
   complet, y compris ses cibles Excel, puis intégrer au registre de production.
4. Qualifier séparément le document ancien avant d'étendre les années admises.

Cette étape livre le candidat d'extraction et sa vérification reproductible ;
elle ne qualifie pas un flux ASTREE de production de bout en bout.

## Revue documentaire complémentaire

La revue locale du 10 octobre est dans `outputs/astree_review_20261010/REVIEW.md`.
Elle propose les annexes comptables pour les primes, identifie les correspondances
directes et laisse IRDS/Groupe à définir. Le libellé PRNV11 de 2024 nécessite une
corroboration explicite ; les annexes 2023 en image nécessitent une qualification
séparée. Le candidat actuel reste limité aux tableaux de production du pilote.

## Export partiel 2024–2025

Un extracteur des annexes comptables et un export de revue sont livrés dans
`outputs/astree_partial_20261010`. Les quatre correspondances étayées alimentent
TAF_G3 ; IRDS/Groupe et les totaux dépendants restent vides. 103 tests réussis,
38 positions source et 10 cellules cibles vérifiées, recalcul LibreOffice réussi.
Le registre de production reste inchangé. Voir le README de ce run pour la portée
et la distinction entre préparation JSON reproductible et génération du classeur.

## Vie 2023 et limite OCR

`outputs/astree_partial_20261010_v2` ajoute la Vie 2023 issue de l’état natif.
Les branches non-vie scannées restent non admises après lectures OCR incompatibles.
107 tests réussis ; les cibles 2024–2025 sont inchangées. L’ancien signalement
d’un écart de total scanné 2023 est corrigé dans la revue : les totaux concordent.

## Diagnostic de mise en page historique 2022 — 13 octobre

Le diagnostic local `scripts/probe_astree_2022_layout.py` examine uniquement les
pages 2 et 3 de l'état ASTREE 2022, après contrôle de l'identité, des périodes et
de l'empreinte du document. Il prépare 149 faits candidats numériques couvrant
2022 et les comparatifs 2021. Chaque montant reste non approuvé ; les cibles
Excel sont nulles, car le mapping n'est pas qualifié. Le rapport est local et ne
modifie pas le classeur ni le registre de production.

La page d'actif sépare les colonnes Brut, Amortissements, Net et comparatif. Le
lecteur récent ne peut pas réutiliser sa bande sans risquer de mélanger des
colonnes. Le manifeste de lignes 2022 diffère aussi : AC520 est absent et AC550
est présent sans montant publié ; ce blanc ne devient pas zéro. Sur la page de
passif, PA350 contient un zéro publié dont le groupe numérique dépasse de peu la
borne récente. Une bande 2022 propre à cette page le détecte sans chevaucher le
comparatif.

Dans le candidat local, le sous-total des catégories d'actif présente un écart
de 1 TND avec le total imprimé. Le sous-total du passif se rapproche exactement ;
les deux totaux imprimés du bilan concordent. L'écart d'actif demeure à résoudre
et aucune ligne n'est approuvée. Le dossier
`outputs/astree_2022_candidate_20261013_v2/qualification.json` conserve les faits
avec leur document, empreinte, page, colonne, libellé et rectangle de preuve.

Prochaine étape : concevoir une lecture ASTREE 2022 séparée avec son manifeste de
lignes et ses colonnes explicites, puis rapprocher l'écart de 1 TND avec un
relecteur. Le garde-fou récent 2023–2025 reste inchangé et l'exercice historique
demeure refusé par le registre de production.

## Observation visuelle ASTREE 2021 — 13 octobre

Les pages 2–3 de `data/sources/ASTREE/2021.pdf` ont été rendues et inspectées.
Elles présentent la même structure générale que 2022 : actif avec Brut,
Amortissements, Net et comparatif ; passif avec les périodes 31/12/2021 et
31/12/2020. C'est une hypothèse de famille pour prioriser le prochain adaptateur,
pas une qualification machine des coordonnées ni des lignes. Aucun fait 2021
n'a été extrait ou approuvé, et aucune valeur n'a été écrite dans Excel.

Étape suivante : mesurer les ancres, bandes et manifestes de 2021, puis appliquer
des contrôles indépendants aux totaux et aux lignes avant de partager un lecteur
historique entre 2021 et 2022. Conserver séparés les exercices jusqu'à cette
vérification et à la résolution humaine de l'écart d'actif 2022.
