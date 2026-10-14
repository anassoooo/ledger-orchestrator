# Prochaines étapes et critères d'acceptation

## Socle livré le 2 octobre

Les profils versionnés, les adresses explicites, la sélection API/CLI, les faits
financiers et la non-régression réelle sont implémentés. Le moteur Excel est testé
sur un profil fictif différent de STAR. La qualification d'autres extracteurs reste
un travail distinct, portant sur des documents réels.

## 1. Référence métier et recette STAR

Préparer un échantillon de contrôle comprenant texte natif, OCR, comparatifs,
zéros publiés, détails, totaux et contradictions. La revue humaine doit vérifier
la sémantique, la période et la source, pas seulement les chiffres.

**Acceptation :** décisions attribuées au relecteur, preuves localisées,
écarts expliqués ; les cas non tranchés restent ouverts. La réussite du test de
non-régression ne remplace pas cette référence indépendante.

## 2. Intégration ASTREE récent

L'extracteur candidat ASTREE 2023–2025, l'annexe partielle et un export de revue
existent dans le dossier local. Résoudre les correspondances IRDS/Groupe et le
périmètre des acceptations, qualifier la base de primes et les règles d'arrondi,
puis établir les correspondances cibles Excel avec le relecteur.

**Acceptation :** chaque valeur admise possède une preuve complète, aucune écriture
conflictuelle silencieuse ; revue indépendante, exécution complète de bout en bout,
mesure des écarts et non-régression STAR réussies avant toute activation.

## 3. Famille historique ASTREE 2021–2022

L'inspection ciblée confirme des colonnes et des lignes différentes du reader
récent. AC520 est absent, AC550 est vide, PA350 est un zéro publié et l'écart du
sous-total d'actif 2022 vaut 1 TND. L'inspection visuelle 2021 suggère la même
famille générale, sans qualification machine des colonnes ni extraction. Mesurer
chaque exercice, puis concevoir un lecteur à manifeste explicite sans changer la
porte d'admission récente.

**Acceptation :** état blanc/zéro fidèle à la publication, toutes les lignes
identifiées, contrôles actif/passif documentés pour chaque année, écart de 1 TND
expliqué et revue indépendante avant toute qualification d'exercice.

## 4. Extension documentaire et COMAR

Étendre progressivement aux exercices disponibles, puis à COMAR, CTAMA et ZITOUNA
TAKAFUL selon leurs spécificités. Implémenter les conversions d'unités avec le montant
PDF original, le coefficient et le résultat. Qualifier séparément chaque famille
de mise en page et chaque périmètre comptable.

**Acceptation :** disponibilité et qualification distinctes ; aucun document manquant
reconstitué par supposition. L'inventaire local du 2 octobre contient ASTREE, COMAR
et ZITOUNA TAKAFUL 2011–2025, STAR 2011–2012 et 2014–2025, CTAMA 2018/2020. Aucun
PDF n'est présent dans le dossier MAE. Ces années viennent des noms de fichiers et
restent à confirmer dans les documents.

## 5. Résolution humaine

Ajouter une proposition chiffrée sourcée, sa décision motivée, de nouveaux contrôles
et la génération d'une nouvelle version du classeur avec comparaison avant/après.

**Acceptation :** historique intact, auteur/date/preuve, conflits explicitement
arbitrés, impossibilité de contourner un contrôle par une simple action d'interface.

## 6. Assistance locale

Installer et mesurer le modèle local, d'abord pour expliquer les rapports, puis
pour proposer des correspondances ambiguës. Utiliser exclusivement les documents
fournis et les faits du traitement.

**Acceptation :** réponses sourcées, abstention testée, temps/mémoire mesurés sur la
machine, aucune admission comptable décidée par le LLM seul.
