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
