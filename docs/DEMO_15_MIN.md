# Démonstration LedgerOrchestrator — 15 minutes

## Objectif

Montrer un MVP local qui extrait des données financières depuis des PDF, applique des règles métier, remplit un classeur contrôlé et produit une piste d'audit. La démonstration doit insister sur la fiabilité et la prudence comptable, pas sur le volume de cellules rempli.

Message principal : le système écrit une valeur uniquement lorsqu'elle est suffisamment prouvée. Une donnée ambiguë reste vide et devient un cas de revue.

## Fichiers à préparer

Ouvrir avant l'appel, sans les partager à l'écran avant le moment prévu :

- `outputs/20260917T125647_54b032c5/STAR_consolide.xlsx`
- `outputs/20260917T125647_54b032c5/anomalies.csv`
- `outputs/20260917T125647_54b032c5/cellules_a_revoir.csv`
- `outputs/20260917T125647_54b032c5/preview_TAF_G1.png`
- `outputs/20260917T125647_54b032c5/preview_TAF_G3.png`
- le dépôt GitHub : <https://github.com/anassoooo/ledger-orchestrator>

Ne pas lancer l'OCR complet pendant les 15 minutes. Le traitement de plusieurs PDF est volontairement séparé de la consultation des résultats. Utiliser le run déjà produit et vérifié.

## Déroulé minute par minute

### 0:00–1:30 — Besoin

Dire :

> Le besoin est de transformer des états financiers PDF hétérogènes en données Excel exploitables. Le risque principal n'est pas seulement une mauvaise lecture OCR. Il faut aussi identifier l'exercice, l'unité, la bonne rubrique, les regroupements comptables et les incohérences de la source.

Présenter le périmètre validé : STAR, exercices 2023 à 2025, feuilles `TAF_G1` et `TAF_G3`.

### 1:30–3:30 — Architecture

Afficher le schéma du README :

1. contrôle du document, de l'entreprise et de l'exercice ;
2. extraction native ou OCR ciblé ;
3. correspondance avec le dictionnaire métier ;
4. contrôles comptables et contrôle des preuves ;
5. écriture Excel et recalcul LibreOffice ;
6. rapport d'anomalies et file de revue humaine.

Préciser que le noyau déterministe est opérationnel. L'orchestrateur multi-agent explicite est la prochaine couche, autour de composants déjà séparés par responsabilité.

### 3:30–5:00 — Démarrage local

Dans PowerShell, depuis la racine du projet :

```powershell
.\scripts\demo_check.ps1
```

Montrer le résultat de santé :

```text
API status : ok
Local only : True
```

Message à faire passer : les PDF, le classeur et les résultats restent sur la machine. Le moteur ne consulte pas Internet et n'envoie pas les documents à une API externe.

### 5:00–8:00 — Résultat TAF_G3

Dans Excel, ouvrir `TAF_G3` et se placer sur les colonnes 2023 à 2025, plage `O4:Q12`.

Montrer :

- les cinq branches non-vie ;
- la branche Vie ;
- les formules des totaux, en particulier `O9`, `P9` ou `Q9` ;
- la conservation des années dans le classeur consolidé.

Expliquer les règles métier :

- Transport inclut Aviation ;
- IRDS inclut Accidents du travail ;
- les Acceptations non-vie sont conservées dans les preuves, mais exclues du total cible des cinq branches ;
- les totaux sont recalculés à partir des détails validés.

Résultat à annoncer : `TAF_G3` contient 9 cellules cibles sur 9 pour chacun des trois exercices.

### 8:00–11:00 — Résultat TAF_G1

Dans `TAF_G1`, montrer les colonnes 2023 à 2025.

Exemples simples :

- `D54` : montant 2024 extrait ;
- `D99` : total actif 2024 calculé ;
- `L90` : total capitaux propres et passif 2024 ;
- `D99 = L90 = 1 571 835 370 TND`.

Afficher la formule d'un total pour montrer que le système ne copie pas aveuglément un total publié. Il le recalcule uniquement si toutes les composantes nécessaires sont présentes.

Couverture actuelle :

| Exercice | TAF_G1 | TAF_G3 |
| --- | ---: | ---: |
| 2023 | 74 / 81 | 9 / 9 |
| 2024 | 74 / 81 | 9 / 9 |
| 2025 | 58 / 81 | 9 / 9 |

Présenter cette couverture comme un indicateur de cellules cibles justifiées, pas comme un taux d'exactitude global.

### 11:00–13:00 — Anomalie réelle et prudence métier

Ouvrir `anomalies.csv` et filtrer `type = notes_arithmetic_mismatch`.

Montrer le cas 2025 :

- rubrique `AC613`, écart arithmétique de `900 TND` ;
- rubrique `AC62`, écart correspondant de `-900 TND` ;
- cellules `C84` et `C85` laissées vides dans `TAF_G1` ;
- les totaux dépendants restent bloqués au lieu d'être calculés sur une base incomplète.

Dire :

> C'est le comportement recherché. Pour une donnée financière, une cellule vide accompagnée d'une anomalie est plus fiable qu'un montant automatiquement forcé.

Montrer ensuite `cellules_a_revoir.csv` pour expliquer que la revue humaine est ciblée et documentée.

### 13:00–14:15 — Qualité technique

Afficher rapidement GitHub :

- dépôt public sans PDF ni Excel confidentiel ;
- Docker, commande et API locale ;
- 53 tests automatisés ;
- CI GitHub réussie ;
- documentation de la logique métier.

Ne pas passer du temps à parcourir le code ligne par ligne.

### 14:15–15:00 — Conclusion

Dire :

> Le prototype prouve que la chaîne complète est réalisable : extraction, contrôle, Excel et audit. La prochaine étape n'est pas de remplir davantage à tout prix. Elle consiste à valider les cas restants, formaliser les profils d'autres entreprises et ajouter l'orchestrateur multi-agent autour de ce noyau contrôlé.

Demander la priorité pour la suite : approfondir STAR, ajouter une deuxième entreprise ou commencer l'orchestration multi-agent.

## Questions probables

### « Est-ce déjà un système multi-agent ? »

Le noyau est actuellement composé de modules spécialisés et testés. Le véritable orchestrateur multi-agent, chargé de distribuer les tâches et de consolider les décisions, reste à implémenter. Les contrôles comptables resteront déterministes même après son ajout.

### « Pourquoi faut-il encore une revue humaine ? »

Les PDF financiers contiennent des scans, des changements de mise en page, des arrondis et parfois des incohérences internes. La revue humaine intervient uniquement sur les cas signalés ; elle ne reprend pas tout le travail.

### « Peut-on traiter toutes les entreprises ? »

L'architecture est prévue pour des profils configurables, mais seule STAR 2023–2025 est validée aujourd'hui. Chaque nouvelle entreprise exige un dictionnaire, un profil de document et un jeu de référence contrôlé.

### « Quel est le taux de précision ? »

Ne pas annoncer un taux global sans jeu de vérité terrain validé. Donner la couverture des cellules cibles et montrer les contrôles réussis, les preuves et les anomalies. La mesure de précision sera possible après validation manuelle d'un corpus de référence.

### « Pourquoi une semaine ne suffit-elle pas pour tout généraliser ? »

Une semaine suffit pour construire un MVP démontrable. Une généralisation fiable nécessite plusieurs formats, un corpus de référence validé, des règles métier confirmées et des tests de non-régression. Ce sont ces éléments qui transforment un prototype en produit fiable.

## Points à éviter

- Ne pas dire que toutes les entreprises et toutes les années sont déjà prises en charge.
- Ne pas présenter l'architecture cible comme un orchestrateur multi-agent déjà terminé.
- Ne pas qualifier les cellules vides d'échecs : elles représentent des décisions de prudence documentées.
- Ne pas ouvrir les PDF d'autres entreprises pendant cette démonstration STAR.
- Dans `TAF_G3`, rester centré sur 2023–2025. Les zéros visibles sur certains totaux historiques proviennent du modèle Excel préexistant et ne sont pas des extractions du moteur.

## Plan de secours

Si Docker ne démarre pas : montrer la dernière exécution, le classeur et les CSV déjà générés.

Si Excel ne s'ouvre pas : utiliser `preview_TAF_G1.png` et `preview_TAF_G3.png`.

Si Internet ne fonctionne pas : le dépôt GitHub n'est pas indispensable. Toute la démonstration métier reste locale.

## Checklist avant l'appel

- Docker Desktop démarré.
- Partage d'écran testé.
- Notifications Windows désactivées.
- Zoom Excel lisible et colonnes 2023–2025 visibles.
- PowerShell ouvert à la racine locale du projet.
- `scripts\demo_check.ps1` exécuté une fois.
- Classeur, anomalies et file de revue ouverts.
- GitHub ouvert sur la page du dépôt.
- Préviews disponibles en secours.
