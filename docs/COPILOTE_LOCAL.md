# Copilote local de revue

Le panneau de `/review` pose une question sur un run ou une cellule. Un graphe
LangGraph sélectionne des faits bornés du `report.json`, interroge un modèle
Ollama local, puis vérifie les identifiants de citations retournés. Il ne dispose
d'aucun outil de recherche web, d'accès libre aux fichiers ou d'écriture Excel.
Les extraits fournis au modèle proviennent seulement des PDF traités et du
rapport local de ce run. Une citation renvoie à la preuve enregistrée ; elle ne
certifie pas à elle seule la justesse de l'interprétation du modèle.

Le résultat est une aide à la revue, jamais une validation comptable. Si le
modèle n'est pas configuré, inaccessible ou incapable de citer des faits admis,
le service le signale ou s'abstient. Aucune question ni réponse n'est conservée
dans les checkpoints de revue.

## Activer dans Docker

Le service `ollama` est optionnel (`--profile llm`). Il communique avec le
moteur sur le réseau Docker interne. Son accès réseau sortant sert au
téléchargement initial des poids ; aucun port Ollama n'est publié sur l'hôte.
Il faut d'abord rétablir l'accès au registre Docker pour télécharger son image.

1. Choisir un modèle **local** adapté à la mémoire de la machine. Le nom doit
   correspondre exactement à celui retourné par `ollama list`. Les modèles
   `:cloud` sont rejetés.
2. Démarrer Ollama : `docker compose --profile llm up -d ollama`.
3. Installer le modèle dans le volume Docker local :
   `docker compose exec ollama ollama pull NOM_DU_MODELE`.
4. Définir `CMF_LLM_MODEL=NOM_DU_MODELE` dans un fichier `.env` à la racine du
   dépôt (ce fichier est ignoré par Git), puis relancer :
   `docker compose --profile llm up -d --force-recreate engine gateway`.
5. Vérifier `GET http://127.0.0.1:8000/copilot/status`, puis poser une question
   dans `/review`.

### Variante NVIDIA

Sur une machine dont le GPU NVIDIA est accessible à Docker, ajouter
`-f compose.yaml -f compose.gpu.yaml` à chaque commande `docker compose`
ci-dessus. Cette surcharge réserve un GPU uniquement pour Ollama ; le profil
standard reste utilisable sur une machine sans GPU. Vérifier l'accès au GPU
dans Docker avant de l'activer, par exemple avec une image locale contenant
`nvidia-smi`.

Pour une RTX 3050 de 6 Go et 32 Go de RAM, le modèle
`qwen3:4b-instruct-2507-q4_K_M` (environ 2,5 Go de poids) est un point de
départ prudent pour les questions de revue en français. Ce choix laisse de la
marge pour le contexte et l'application ; il n'autorise jamais le modèle à
écrire des montants dans le classeur. Il faut télécharger l'image Ollama puis
les poids du modèle une première fois avant toute utilisation hors ligne.

Le modèle est vérifié par `/api/tags` avant toute question. L'adaptateur
n'accepte que `http://ollama:11434` ou la boucle locale sur ce même port, sans
proxy HTTP. Aucune URL de modèle n'est fournie par l'utilisateur. Le modèle
reçoit un JSON de faits sélectionnés, pas le PDF entier, et ne peut appeler
aucun outil. La réponse est un JSON à schéma fixe ; les citations inconnues
sont rejetées. Ces protections réduisent le risque d'hallucination, mais une
personne doit toujours lire les preuves et les contrôles.

## Périmètre actuel

Les questions portent sur le statut du run, la couverture, les types
d'anomalies et, pour la cellule sélectionnée, son motif, ses anomalies et
l'enregistrement extrait disponible. Le modèle ne parcourt pas encore toutes
les pages du PDF ; il ne peut donc pas répondre à une question dont la preuve
n'est pas présente dans le rapport. Il ne propose pas encore de correspondances
à l'agent d'extraction. La résolution d'une cellule et la régénération d'un
classeur après arbitrage restent une étape distincte, soumise aux contrôles
métier et à une décision humaine traçable.
