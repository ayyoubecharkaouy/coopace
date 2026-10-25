# Module Machine Learning de Coopace

État : prévu pour une étape ultérieure, sans implémentation. Ce dossier réserve un espace distinct pour la recherche, l'entraînement et l'évaluation du ML. Il ne contient actuellement aucun dataset ni modèle entraîné.

## Objectifs à évaluer

| Fonction candidate | Question à laquelle le modèle pourrait répondre |
| --- | --- |
| Prédiction du bénéfice d'un relais ou d'une délégation | Le chemin proposé améliorera-t-il suffisamment la connexion de A, en tenant compte du coût pour B et les autres appareils ? |
| Estimation de capacité à court terme | Sur une connexion variable, quel débit utilisable est probable et avec quelle incertitude ? |

Ces fonctions sont des hypothèses à tester. Le ML ne garantit pas un gain et ne crée pas de bande passante supplémentaire.

## Place dans le logiciel

- Les agents et la passerelle doivent fonctionner avec les règles déterministes lorsque le ML est absent ou indisponible.
- Le noyau Go ne dépendra pas des outils Python d'entraînement.
- Un modèle pourra proposer une estimation accompagnée d'une confiance ; les autorisations, limites d'action, décisions d'abstention et restaurations resteront déterministes.
- Le format d'export, le moteur d'inférence et l'interface avec Go seront choisis après validation d'un premier modèle utile.
- Le module n'aura pas d'accès direct aux opérations réseau privilégiées.

Python est envisagé pour les expériences et l'entraînement hors ligne. Les bibliothèques et leurs versions restent à choisir lors du développement de ce module.

## Données et résultats attendus

Les expériences pourront utiliser des mesures autorisées de débit, latence, pertes, qualité radio accessible et charge de la passerelle. La définition des variables, des cibles et des méthodes de collecte devra précéder la constitution du dataset.

Le dataset de base exclura les contenus, URL, noms de sites et identifiants personnels. Les noms d'applications ne seront pas déduits avec certitude de flux chiffrés.

Chaque expérience devra conserver sa configuration, les versions utilisées, la méthode de séparation des données et ses résultats. Les données d'entraînement et d'évaluation devront être séparées par sessions ou environnements pour limiter les fuites entre les deux ensembles.

## Progression prévue

1. Valider l'instrumentation et les décisions sans ML, puis définir une cible mesurable.
2. Constituer des données autorisées, avec un protocole d'évaluation reproductible.
3. Entraîner hors ligne un premier modèle et le comparer aux références pertinentes.
4. Évaluer sur des réseaux ou conditions absents de l'entraînement.
5. Tester en observation seule : enregistrer les propositions sans les appliquer au réseau.
6. Étudier une intégration facultative uniquement si le bénéfice collectif est reproductible.

Pour les files réseau, les références comprendront CAKE statique, qosify et cake-autorate selon le scénario. Pour un relais, comparer le chemin direct, le relais manuel et la sélection déterministe avant de créditer le modèle d'un bénéfice.

Si le ML n'apporte pas d'amélioration utile, son activation restera écartée. La latence, le débit utile, l'équité, les ressources consommées et les mauvaises décisions devront être considérés ensemble.

## Organisation future

Les sous-dossiers de préparation des données, entraînement, évaluation et export seront créés au moment de leur implémentation. Les jeux de données et les modèles volumineux auront une politique de stockage distincte du code, à définir avant leur ajout.

Voir l'[architecture](../docs/ARCHITECTURE.md), la [feuille de route](../docs/ROADMAP.md) et les [choix techniques](../docs/TECH_STACK.md).
