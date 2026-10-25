# Développement progressif

Chaque étape doit produire un résultat vérifiable avant d'étendre le périmètre. Ce document décrit une progression ; il n'autorise pas à implémenter toutes les étapes d'un seul coup.

## Étape 1 — Organisation du dépôt

État : réalisée lors de l'initialisation.

- Dépôt Git local et branche `main`.
- Répertoires des applications, du code partagé et des adaptations système.
- Documentation des responsabilités, limites et décisions ouvertes.
- Configuration de base des fichiers et exclusions Git.

Validation : fichiers suivis par Git, différences sans erreurs d'espacement et premier commit local.

## Étape 2 — Premier programme minimal

État : en cours, choix techniques terminés ; implémentation à faire.

Choisir et documenter la pile technique et la première plateforme. Définir les premiers modèles d'appareil, de rôle et de capacité, puis créer un point d'entrée minimal capable d'afficher son état local. Cette étape ne modifiera pas le routage ni les politiques du système.

Validation : démarrage reproductible et vérification des modèles effectivement utilisés.

### 2.1 — Choix techniques

État : terminée.

Go pour le noyau et les agents Linux/Windows, Kotlin pour l'intégration Android, contrats JSON versionnés pour le futur protocole. Premiers essais sous Linux, avec cible Windows. Le framework web et la réutilisation du noyau sur Android restent à valider au moment concerné.

Livrable : [décision technique documentée et sourcée](TECH_STACK.md). Aucun code ni outillage installé à cette sous-étape.

### 2.2 — Outillage et modèles de base

État : à faire.

Préparer une version stable de Go, créer un module unique à la racine et définir les modèles d'appareil, de rôle et de capacité dans `packages/core`. Vérifier leurs contraintes utiles avant de les intégrer à l'agent.

### 2.3 — Commande locale de l'agent

État : à faire.

Créer `coopace status` avec affichage de la version, du système détecté et de l'état local. Cette commande ne rejoindra aucun groupe et ne modifiera pas la configuration réseau.

### 2.4 — Validation du premier programme

État : à faire.

Documenter et vérifier le lancement sous Linux ainsi que la compilation pour Windows. Distinguer la réussite de compilation d'une validation réelle sur un appareil Windows.

## Étape 3 — Groupe et observations

État : à faire.

Spécifier les messages, l'identité et l'adhésion autorisée au groupe. Établir un échange de mesures minimales entre deux instances, puis élargir aux plateformes retenues. Ajouter une première vue de contrôle.

Validation : adhésion explicite, traitement des messages invalides et déconnexion propre.

## Étape 4 — Prototype de passerelle

État : à faire.

Valider sur la plateforme choisie la couverture du trafic, les permissions, les mesures de référence et la restauration. Intégrer un moteur de gestion des files adapté à ce système, puis comparer son résultat à une référence connue.

Validation : couverture mesurée et comparaison avant/après, y compris en cas de panne.

## Étape 5 — Décisions coopératives

État : à faire.

Introduire des décisions déterministes bornées, l'évaluation collective, l'abstention et le retour arrière. Compléter les intégrations des plateformes selon leurs capacités réelles.

## Étapes ultérieures — Relais et ML facultatifs

État : recherche, à réévaluer selon les résultats.

Tester d'abord un tunnel manuel sur un véritable chemin alternatif. Étudier ensuite sa sélection automatique. Le ML ne sera envisagé qu'avec des données autorisées et un bénéfice reproductible face aux solutions existantes.

Le dossier [`ml/`](../ml/README.md) réserve ce module et décrit son périmètre ainsi que ses conditions d'intégration. Son développement reste différé.
