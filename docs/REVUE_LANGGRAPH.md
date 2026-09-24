# Revue humaine avec LangGraph

## Usage

Après `docker compose build` puis `docker compose up -d`, ouvrir
<http://127.0.0.1:8000/review>. La page permet de lancer une extraction STAR sur
les exercices 2023–2025, de choisir un run terminé et d'examiner chaque cellule
restée ouverte. Elle montre le motif, l'action suggérée, les dépendances et un
lien vers la page du PDF source. Les documents et le navigateur communiquent
uniquement avec l'API locale publiée sur `127.0.0.1`.

Deux décisions sont possibles : `Suivi nécessaire` et `Revue documentée`.
La seconde signifie seulement qu'une personne a examiné le cas ; elle ne
certifie pas le montant et ne résout pas automatiquement l'anomalie. Chaque
décision exige un nom et une note. Une nouvelle décision complète l'historique
sans effacer la précédente.

## Fonctionnement

Un graphe LangGraph distinct de l'orchestrateur comptable ouvre un dossier,
appelle `interrupt()` avant chaque décision et reprend avec `Command(resume=...)`.
Le checkpointer SQLite enregistre l'état dans `outputs/review_graph.sqlite3`,
ce qui permet de reprendre la revue après un redémarrage. L'identifiant du
thread est constitué du run et de la cellule. Les accès au checkpointer sont
sérialisés dans le processus API.

L'historique porte sur des décisions de revue, pas sur des écritures Excel.
Ni le PDF, ni le modèle de classeur, ni le classeur généré, ni `report.json`
ne sont modifiés par la revue. Les décisions restent locales sous `outputs/`,
ignoré par Git. Aucun modèle de langage n'est requis ou appelé.

## Routes locales

| Route | Rôle |
| --- | --- |
| `GET /review` | Interface navigateur |
| `GET /runs` | Runs terminés disponibles |
| `POST /runs` | Démarrer l'extraction depuis l'interface |
| `GET /runs/{run_id}/review` | File de cellules et dernière décision |
| `GET /runs/{run_id}/review/{case_id}` | Dossier et historique |
| `POST /runs/{run_id}/review/{case_id}/start` | Créer le point d'interruption |
| `POST /runs/{run_id}/review/{case_id}/decision` | Reprendre avec une décision humaine |
| `GET /runs/{run_id}/review/{case_id}/source` | PDF source, servi en lecture seule |

Le serveur reste lié à l'interface loopback. Cette version ne fournit pas
d'authentification multi-utilisateur, de validation comptable par clic, ni de
résolution automatique des conflits. Pour un déploiement distant ou partagé,
il faudra ajouter une authentification et une gestion des rôles avant d'exposer
les PDF ou les notes de revue.

Référence technique : [interruptions LangGraph](https://docs.langchain.com/oss/python/langgraph/interrupts).
