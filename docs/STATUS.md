# État du MVP

## Copilote local de revue (24 septembre 2026)

Une intégration Ollama optionnelle a été ajoutée en lecture seule : graphe
LangGraph à trois étapes (sélection des faits, appel du modèle local, vérification
des citations), API et panneau dans `/review`. Les dossiers affichent maintenant
les montants extraits et anomalies déjà présents dans le rapport. Aucun modèle
n'est installé dans la stack actuelle ; l'intégration est couverte par des tests
avec transport simulé, mais pas encore par un essai avec un vrai modèle. Le
service Ollama Docker ne pourra être téléchargé tant que la connexion HTTPS à
Docker Hub reste indisponible : le DNS répond désormais, mais la connexion au
port 443 échoue. Voir [Copilote local](COPILOTE_LOCAL.md).
La suite complète passe avec 70 tests dans l'image Docker locale mise à jour.

La revue humaine ne valide toujours pas un montant et ne régénère pas le
classeur. L'interface doit rester décrite comme une revue documentée, pas une
résolution comptable complète.

## Interface de revue LangGraph

Une interface locale de revue est ajoutée sous `/review`. Elle liste les runs
terminés et les cellules à examiner, permet d'ouvrir le PDF source et consigne
les décisions humaines avec une note. LangGraph suspend chaque dossier avec
`interrupt()` et conserve son historique dans un checkpointer SQLite local.
Les décisions ne modifient pas les montants, les PDF, les rapports d'extraction
ou le classeur. L'interface peut aussi démarrer un traitement STAR 2023–2025.
Les 63 tests passent avec le code courant dans Docker. Une image incrémentale
contient le code et les
dépendances, sans montage du dépôt. Cette image est affectée au nom local utilisé
par Compose ; `engine` et `gateway` ont démarré, et `/review` répond sur
`127.0.0.1:8000` avec les 37 dossiers du run de référence. Le checkpoint créé
avant le redémarrage est toujours consultable. La reconstruction standard depuis
Docker Hub reste bloquée par la résolution DNS de `registry-1.docker.io` ; le
build neuf sur une autre machine n'est donc pas encore confirmé.
Un lancement par `POST /runs` depuis cette stack a aussi terminé le run
`20260924T164906_1b40dd9c` avec 255 écritures, 45 anomalies, 37 dossiers de
revue et cinq agents terminés.

## Vérification Docker du 24 septembre 2026

Le moteur Docker est de nouveau accessible. Les 59 tests passent dans le conteneur,
sans test ignoré, avec le code actuel monté en lecture seule sur l'image locale.
Une exécution complète STAR 2023–2025 a produit le run
`20260924T074936_4a5f2ea5` : 255 écritures, 45 anomalies, 37 cellules à revoir,
et le statut `needs_review`. Les rapports coïncident avec la référence du
17 septembre pour les documents, les données extraites, les écritures, les types
d'anomalies, la couverture et la revue. Les 255 cellules écrites du classeur,
dont 73 formules, ont les mêmes formules et valeurs recalculées que la référence.
L'audit interne de ce nouveau classeur relève zéro erreur d'intégrité. L'API
locale a répondu à `/health` et à `/runs/{run_id}/agents` avec les cinq agents
terminés.

La reconstruction de l'image Docker n'a pas abouti : Docker Hub a expiré lors
de la résolution de `python:3.12-slim-bookworm`. Ces contrôles utilisent donc
l'image locale du 18 septembre avec le code courant monté en lecture seule ;
ils valident le parcours d'exécution, mais pas la reproductibilité d'un build
neuf hors ligne. Le conteneur temporaire de test API a été arrêté.

## Orchestration ajoutée le 24 septembre 2026

L'exécution passe désormais par cinq agents déterministes : documents, extraction,
validation, classeur et revue. Un orchestrateur vérifie leurs dépendances, arrête
la chaîne sur erreur et écrit les transitions dans `report.json`. Une vue compacte
est disponible via `GET /runs/{run_id}/agents`. Il ne s'agit pas encore d'agents IA
autonomes ni d'une prise en charge validée des autres entreprises.

À cette étape, 59 tests locaux passaient, dont deux ignorés hors Docker sans
LibreOffice ni FastAPI. La suite courante compte désormais 70 tests réussis.
Une première comparaison, hors Docker, avait confirmé les montants extraits et
les branches, les types d'anomalies, la couverture et la file de revue. Elle
réutilisait le classeur de référence et ne validait donc pas l'écriture Excel ni
le recalcul LibreOffice. La vérification Docker ci-dessus a depuis couvert ces
deux étapes avec un classeur nouvellement généré.

## État de référence au 17 septembre 2026

## Fonctionnel et vérifié

Docker Desktop fonctionne. Commande et API locale sont opérationnelles : lancement,
suivi, rapport et téléchargement. Le classeur téléchargé a été comparé au fichier
local par SHA-256 : identité confirmée lors de la vérification précédente. À cette
date, 53 tests passaient dans Docker, dont le recalcul LibreOffice réel, les
conflits et les regroupements de branches. La suite courante en compte 70.

Les règles confirmées sont actives : TND, STAR_Details, primes avant réassurance,
Transport + Aviation, IRDS + Accidents du travail, Acceptations non-vie exclues.
La documentation complète est dans LOGIQUE_METIER.md.

L'exécution de référence à cette date, `20260917T125647_54b032c5`, produisait
255 écritures de valeurs/formules (pas 255 montants indépendants). Le run courant
de démonstration est `20260924T164906_1b40dd9c`.
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

`ledger_orchestrator.diagnostics` compare les candidats OCR au texte natif et contrôle les familles
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

Le mode `ledger_orchestrator.ocr_probe --raw` reconstitue les bandes d'images qui se chevauchent
avec une ligne. AC322 peut ainsi être examiné, mais les lectures anglaise et
française divergent encore. Aucun assouplissement des règles d'admission.
