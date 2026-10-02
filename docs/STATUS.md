# État du projet — 2 octobre 2026

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
