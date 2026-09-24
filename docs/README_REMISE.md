# Dossier de remise — LedgerOrchestrator

**Auteur :** Anas Bougrine

**Encadrant académique :** Lazhar Hedfi, actuaire

## Titre

LedgerOrchestrator — prototype local d'extraction contrôlée des états financiers publiés en PDF vers un classeur Excel.

## Périmètre présenté

Cette version est un MVP validé sur les états financiers individuels STAR des exercices 2023, 2024 et 2025.
Elle traite les zones TAF_G1 (bilan) et TAF_G3 (primes par branche) du modèle fourni.
Les documents restent locaux et ne sont pas envoyés à un service externe.

Le moteur n'est pas encore présenté comme une solution complète pour toutes les entreprises et toutes les années. La généralisation constitue la phase suivante.

## Ce que le prototype réalise

- vérifie l'entreprise, l'exercice, l'unité et l'identité du PDF ;
- lit le texte natif et utilise l'OCR pour les pages scannées ;
- associe les rubriques aux lignes du classeur avec un dictionnaire métier ;
- conserve la page, la zone, le fichier, l'empreinte et la méthode de lecture ;
- recalcule les totaux avec des formules Excel contrôlées ;
- laisse vide une donnée absente ou insuffisamment prouvée ;
- conserve une valeur existante en cas de conflit et crée une anomalie ;
- produit un rapport JSON, un rapport CSV de revue et un classeur de sortie ;
- s'exécute localement avec Docker et expose une API minimale.

## Règles métier principales

- Unité cible : TND.
- Une cellule vide ne signifie pas zéro.
- Les totaux ne sont calculés qu'à partir des détails effectivement publiés et validés.
- Pour TAF_G3 : Transport inclut Aviation ; IRDS inclut Accidents du travail ; les Acceptations non-vie sont conservées séparément et exclues du total des cinq branches.
- Les valeurs contradictoires ne sont pas corrigées automatiquement.

## Résultat de démonstration

Dernière exécution : `20260917T125647_54b032c5`.

| Exercice | TAF_G1 | TAF_G3 |
| --- | ---: | ---: |
| 2023 | 74 / 81 | 9 / 9 |
| 2024 | 74 / 81 | 9 / 9 |
| 2025 | 58 / 81 | 9 / 9 |

Le statut est `needs_review` : le résultat est exploitable comme démonstrateur, mais il n'est pas une certification comptable complète.

## Contrôles réalisés

- 53 tests locaux recensés ; les tests d'intégration Docker incluent le recalcul LibreOffice.
- Audit de 255 écritures, dont 73 formules.
- Vérification de l'empreinte des sources et de la conservation du modèle original.
- Rapports de cellules à revoir, anomalies, couverture et audit des sources.

## Démonstration conseillée

Depuis la racine du projet :

```powershell
docker compose build
docker compose run --rm engine python -m cmf --years 2023 2024 2025
docker compose up -d
Invoke-RestMethod http://localhost:8000/health
```

Présenter ensuite :

1. `outputs/20260917T125647_54b032c5/STAR_consolide.xlsx` ;
2. `cellules_a_revoir.csv` pour montrer les limites et les anomalies ;
3. `report.json` pour la traçabilité ;
4. `docs/LOGIQUE_METIER.md` pour les règles métier.

## Limites assumées

- Les autres entreprises et exercices du dossier ne sont pas encore généralisés.
- Les documents illisibles, les rubriques absentes et les contradictions restent bloqués ou signalés.
- Le modèle local et l'interface de résolution humaine ne sont pas encore intégrés.
- Les recherches externes ne font pas partie du traitement : l'agent doit utiliser uniquement les documents fournis.

## Suite proposée

Une orchestration déterministe coordonne maintenant les étapes document, extraction, validation, classeur et revue, avec une trace consultable. La prochaine phase transforme le profil STAR en moteur configurable multi-entreprises et multi-années : détection du profil du document, dictionnaires par modèle et schéma de données commun. Le prototype sert de base de test et de preuve de faisabilité.
