# Architecture des agents

## Périmètre actuel

LedgerOrchestrator exécute cinq agents logiciels déterministes sur les états
financiers individuels STAR 2023–2025. Chaque agent reçoit uniquement les résultats
de ses prédécesseurs déclarés. Les PDF et le classeur sont fournis localement.

| Agent | Entrée | Sortie et responsabilité |
| --- | --- | --- |
| Documents | Chemins des PDF et exercices demandés | Pages, empreintes SHA-256, identité, exercice, méthode OCR/native |
| Extraction | Pages vérifiées | Rubriques du bilan, notes, primes et preuves |
| Validation | Rubriques extraites | Contrôles comptables, comparatifs, admission ou revue |
| Classeur | Montants validés | Copie Excel remplie, formules contrôlées, conflits |
| Revue | Montants validés et classeur | Couverture et file de cellules à examiner |

L'orchestrateur impose l'ordre et les dépendances. Un échec interrompt la chaîne ;
le classeur ne peut pas être écrit si la validation n'a pas terminé. Les événements
`running`, `completed` et `failed` sont enregistrés avec leur horodatage, durée et
mesures agrégées. Aucune valeur financière brute n'est copiée dans cette trace.

La trace est incluse dans `report.json` et consultable seule à l'adresse
`GET /runs/{run_id}/agents`. Les preuves financières détaillées restent dans les
sections existantes du rapport.

## Graphe de revue humaine

LangGraph pilote un second flux, indépendant des cinq agents d'extraction :
`dossier → interruption → décision humaine → historique → interruption`.
Le checkpointer SQLite permet de reprendre un dossier après redémarrage.
L'interface locale présente la file, le motif, la page PDF et l'historique.
Une décision de revue ne valide pas une valeur et n'écrit rien dans Excel.
Voir [Revue humaine avec LangGraph](REVUE_LANGGRAPH.md).

## Règles qui ne dépendent pas d'un modèle

- L'unité cible STAR est le TND ; l'unité source et la conversion sont conservées.
- Une rubrique absente reste vide et ne devient jamais un zéro supposé.
- Un total exige des détails validés et un contrôle avec le total publié.
- Un conflit avec une valeur Excel existante conserve la valeur et crée une anomalie.
- Une incohérence source bloque la rubrique concernée et ses totaux dépendants.

## Limites et prochaine extension

L'architecture est multi-agent au sens d'une coordination explicite de composants
spécialisés. Elle n'utilise pas encore de modèle local pour résoudre les libellés
ambigus. Les profils d'autres entreprises et années devront être validés avant
d'être activés. Une éventuelle proposition d'un modèle restera soumise aux règles
de preuve et de contrôle comptable ci-dessus.
