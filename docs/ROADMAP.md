# Développement progressif

Chaque étape doit produire un résultat vérifiable avant d'étendre le périmètre. Ce document décrit une progression ; il n'autorise pas à implémenter toutes les étapes d'un seul coup.

Les [objectifs produit et critères de réussite](PRODUCT.md) fixent la direction. Les étapes 1 et 2 préparent le socle logiciel ; elles ne démontrent aucun gain réseau. Après ce socle, l'instrumentation et un premier moteur de passerelle mesurable priment sur l'élargissement du groupe, une interface complète ou le ML.

## Étape 1 — Organisation du dépôt

État : réalisée lors de l'initialisation.

- Dépôt Git local et branche `main`.
- Répertoires des applications, du code partagé et des adaptations système.
- Documentation des responsabilités, limites et décisions ouvertes.
- Configuration de base des fichiers et exclusions Git.

Validation : fichiers suivis par Git, différences sans erreurs d'espacement et premier commit local.

## Étape 2 — Premier programme minimal

État : en cours ; choix techniques, modèles de base et premier agent local validés sous Linux. La validation de la cible Windows reste à effectuer à l'étape 2.4.

Choisir et documenter la pile technique et la première plateforme. Définir les premiers modèles d'appareil, de rôle et de capacité, puis créer un point d'entrée minimal capable d'afficher son état local. Cette étape ne modifiera pas le routage ni les politiques du système.

Validation : démarrage reproductible et vérification des modèles effectivement utilisés.

### 2.1 — Choix techniques

État : terminée.

Go pour le noyau et les agents Linux/Windows, Kotlin pour l'intégration Android, contrats JSON versionnés pour le futur protocole. Premiers essais sous Linux, avec cible Windows. Le framework web et la réutilisation du noyau sur Android restent à valider au moment concerné.

Livrable : [décision technique documentée et sourcée](TECH_STACK.md). Aucun code ni outillage installé à cette sous-étape.

### 2.2 — Outillage et modèles de base

État : terminée, validée sous Linux x86_64 avec Go 1.27.3.

Préparer une version stable de Go, créer un module unique à la racine et définir les modèles d'appareil, de rôle et de capacité dans `packages/core`. Vérifier leurs contraintes utiles avant de les intégrer à l'agent.

Livrés : `.go-version`, `go.mod`, scripts d'installation locale et de lancement de Go, modèles avec validation et tests du noyau. L'installation du SDK est confirmée ; le formatage, les tests, l'analyse statique et la compilation réussissent. Les [instructions de développement](DEVELOPMENT.md) décrivent les commandes reproductibles et la portée de cette validation.

### 2.3 — Commande locale de l'agent

État : terminée, validée sous Linux x86_64 avec Go 1.27.3.

Créer `coopace status` avec affichage de la version, du système détecté et de l'état local. Cette commande ne rejoindra aucun groupe et ne modifiera pas la configuration réseau.

Livrés : point d'entrée de l'agent, collecte de l'état local, commandes `status` et d'aide, gestion des erreurs et tests. Le lancement via Go et celui du binaire compilé ont été vérifiés, ainsi que les codes de sortie pour l'aide et les arguments invalides.

### 2.4 — Validation du premier programme

État : à faire pour la cible Windows ; le lancement Linux est déjà vérifié à l'étape 2.3.

Documenter et vérifier le lancement sous Linux ainsi que la compilation pour Windows. Distinguer la réussite de compilation d'une validation réelle sur un appareil Windows.

## Étape 3 — Groupe et observations

État : à faire.

Commencer par définir et instrumenter les mesures locales utiles, avec leurs limites et une référence avant intervention. Spécifier ensuite les messages, l'identité et l'adhésion autorisée au groupe. Établir un échange minimal entre deux instances et une première vue des observations. L'élargissement à toutes les plateformes et la coordination avancée attendront la validation du prototype de passerelle.

Validation : provenance et limites des mesures connues, adhésion explicite, échanges authentifiés, traitement des messages invalides et déconnexion propre. Un groupe complet n'est pas requis pour commencer l'étude du moteur de passerelle.

## Étape 4 — Prototype de passerelle

État : à faire.

Valider sur la plateforme choisie la couverture du trafic, les permissions, les mesures de référence et la restauration. Intégrer un moteur de gestion des files adapté à ce système, puis comparer son résultat à une référence connue.

Commencer par une étude courte du point d'application et des opérations réalisables. La cible Windows doit faire l'objet de cette validation spécifique : une CLI Windows fonctionnelle ne valide pas le moteur de passerelle. La référence Linux/OpenWrt avec CAKE/SQM du rapport reste distincte de cette cible.

Le premier essai utilisera une activation manuelle et bornée. Comparer la configuration initiale, le moteur configuré manuellement et le pilotage Coopace sans ML, selon les [mesures prévues](PRODUCT.md#références-et-mesures-indispensables). Fixer les seuils d'acceptation avant l'expérience.

Validation : couverture mesurée, latence sous charge, débit utile, équité et ressources consommées ; restauration et compatibilité IPv4/IPv6/DNS vérifiées, y compris en cas de panne. Documenter également les scénarios sans bénéfice.

## Étape 5 — Décisions coopératives

État : à faire.

Introduire des décisions déterministes bornées, l'évaluation collective, l'abstention et le retour arrière. Compléter les intégrations des plateformes selon leurs capacités réelles.

Cette automatisation dépend de la validation des mesures et de la restauration à l'étape 4. Si la surcouche n'apporte pas de bénéfice par rapport au moteur existant, conserver l'intégration simple et réévaluer l'automatisation.

## Étapes ultérieures — Relais et ML facultatifs

État : recherche, à réévaluer selon les résultats.

Tester d'abord un tunnel manuel sur un véritable chemin alternatif. Étudier ensuite sa sélection automatique. Le ML ne sera envisagé qu'avec des données autorisées et un bénéfice reproductible face aux solutions existantes.

Le dossier [`ml/`](../ml/README.md) réserve ce module et décrit son périmètre ainsi que ses conditions d'intégration. Son développement reste différé.
