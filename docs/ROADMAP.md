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

État : terminée pour le socle, le lancement Linux et la compilation Windows amd64. L'exécution native Windows reste à consigner avant de déclarer cette cible testée à l'exécution.

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

État : terminée pour la compilation Windows amd64 et le lancement Linux ; vérification native Windows non effectuée.

Documenter et vérifier le lancement sous Linux ainsi que la compilation pour Windows. Distinguer la réussite de compilation d'une validation réelle sur un appareil Windows.

La compilation et l'analyse statique ciblant Windows réussissent. Le format PE32+ x86-64 et les métadonnées de compilation ont été contrôlés. Un exécutable de développement et son empreinte SHA-256 sont disponibles dans `.local/bin/`. La [procédure de validation Windows](WINDOWS_VALIDATION.md) décrit les commandes à exécuter sur un PC x64 et les résultats à consigner.

## Étape 3 — Groupe et observations

État : premier échange Linux implémenté à l'étape 3.4, avec admission persistée et TLS mutuel testés en mémoire. Validation TCP réelle de cet échange à confirmer ; les mesures locales des étapes précédentes restent disponibles.

Commencer par définir et instrumenter les mesures locales utiles, avec leurs limites et une référence avant intervention. Spécifier ensuite les messages, l'identité et l'adhésion autorisée au groupe. Établir un échange minimal entre deux instances et une première vue des observations. L'élargissement à toutes les plateformes et la coordination avancée attendront la validation du prototype de passerelle.

Validation : provenance et limites des mesures connues, adhésion explicite, échanges authentifiés, traitement des messages invalides et déconnexion propre. Un groupe complet n'est pas requis pour commencer l'étude du moteur de passerelle.

### 3.1 — Compteurs locaux en lecture seule

État : terminée sous Linux ; collecte Windows non implémentée.

Livrés : commande `coopace observe`, lecture des octets RX/TX par interface, calcul sur deux lectures et durée effectivement mesurée. Les interfaces apparues, disparues et les compteurs en baisse rendent les taux indisponibles au lieu de produire des zéros trompeurs.

Les tests, l'analyse statique et la compilation passent sous Linux, ainsi que la compilation Windows avec une collecte explicitement indisponible sur cette cible. Le lancement réel a été vérifié dans un espace réseau où seule `lo` était visible. Voir la [provenance, les unités et les limites](OBSERVATIONS.md).

### 3.2 — Latence et référence avant intervention

État : terminée pour la mesure d'établissement TCP, l'export local et le protocole de référence. Connexion locale réelle validée sous Linux ; mesure WAN et exécution native Windows non validées.

Définir les cibles et la méthode de mesure de latence, les limites de l'observation, les scénarios au repos/sous charge et les conditions d'une référence reproductible. Définir les formats de conservation nécessaires avant d'implémenter l'export. L'observation des compteurs seule ne permet pas de conclure à une congestion.

Livrés : commande `coopace latency` avec cible IP:port obligatoire, essais bornés et annulables, percentiles des seules connexions réussies et rapport JSON local v1. Les échecs ne sont assimilés ni à des durées nulles ni à des pertes de paquets. Le [protocole de référence](LATENCY.md) définit les conditions déclarées au repos/sous charge, les unités et les limites de comparaison. Les tests déterministes et le test TCP en boucle locale passent sous Linux ; ce dernier a été exécuté depuis le terminal utilisateur, les sockets étant interdites dans l'environnement isolé de l'agent de développement.

### 3.3 — Identité et contrats du groupe

État : fondations terminées pour l'identité persistante Linux, le modèle de consentement et les contrats validés hors réseau. TLS ajouté ensuite à l'étape 3.4 ; stockage protégé Windows non implémenté.

Définir l'identité persistante, le consentement d'adhésion, les messages versionnés et l'authentification des échanges. Étudier l'adaptation des mesures aux autres plateformes selon leurs capacités réelles.

Livrés : `identity init/show` avec dossier explicite et clé privée locale, empreinte publique liée à la clé Ed25519, consentements distincts, contrats JSON v1 bornés et validateur de session lié à un pair attendu. La v1 historique est remplacée par la v2 à l’étape 3.4 avec TLS mutuel ; le validateur seul ne constitue pas une authentification. Voir [IDENTITY_AND_GROUP.md](IDENTITY_AND_GROUP.md).

### 3.4 — Premier échange entre deux instances

État : implémentée sous Linux et validée en mémoire avec de vraies négociations TLS ; essai TCP réel à confirmer depuis le terminal utilisateur.

Échanger uniquement les observations autorisées dans un groupe minimal authentifié, avec refus des messages invalides et déconnexion propre. Garder l'évaluation du moteur de passerelle indépendante d'une coordination avancée.

Livrés : certificats publics liés à l'identité, approbation explicite d'un pair, consentement persisté, révocation, TLS 1.3 mutuel et cadrage borné. `group listen/exchange` établit un échange unique, avec au plus une observation autorisée par pair et une limite de 30 secondes, puis déconnecte. Les tests vérifient les quatre choix de partage, le refus des mauvais pairs/groupes et l'interruption après révocation. Voir [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md) pour l'essai à deux états Linux et le test TCP en boucle locale. Il n'y a pas de service de groupe permanent. La participation depuis Windows exige son adaptateur natif de stockage protégé.

## Étape 4 — Prototype de passerelle

État : diagnostic Linux, premiers essais synthétiques sans/avec transfert et contrôles natifs du superviseur disponibles. Moteur de files, restauration de passerelle réelle et évaluation du bénéfice sous charge restent à réaliser.

Valider sur la plateforme choisie la couverture du trafic, les permissions, les mesures de référence et la restauration. Intégrer un moteur de gestion des files adapté à ce système, puis comparer son résultat à une référence connue.

Commencer par une étude courte du point d'application et des opérations réalisables. La cible Windows doit faire l'objet de cette validation spécifique : une CLI Windows fonctionnelle ne valide pas le moteur de passerelle. La référence Linux/OpenWrt avec CAKE/SQM du rapport reste distincte de cette cible.

Le premier essai utilisera une activation manuelle et bornée. Comparer la configuration initiale, le moteur configuré manuellement et le pilotage Coopace sans ML, selon les [mesures prévues](PRODUCT.md#références-et-mesures-indispensables). Fixer les seuils d'acceptation avant l'expérience.

Validation : couverture mesurée, latence sous charge, débit utile, équité et ressources consommées ; restauration et compatibilité IPv4/IPv6/DNS vérifiées, y compris en cas de panne. Documenter également les scénarios sans bénéfice.

### 4.1 — Diagnostic de la passerelle en lecture seule

État : inventaire Linux implémenté et testé ; rapport partiel dans l'environnement isolé et premier inventaire complet dans la passerelle virtuelle sur le PC utilisateur. L'inventaire du réseau du foyer reste à consigner. Adaptateur Windows non implémenté.

Préciser la plateforme candidate et le chemin du trafic, inventorier les interfaces, le moteur réseau et les permissions, puis indiquer ce qui est effectivement observable ou indisponible. Définir les mesures de référence et les exigences de restauration avant de modifier les files ou le routage. L'essai TCP réel de l'étape 3.4 reste à confirmer séparément ; un groupe complet n'est pas un prérequis à ce diagnostic.

Livrés : application `coopace-gateway inspect`, interfaces, flags de forwarding IPv4/IPv6, capacité effective `CAP_NET_ADMIN`, outils disponibles, routes par défaut et files visibles. Les requêtes sont bornées et en lecture seule ; aucune interface WAN ni aptitude à intervenir n'est déduite automatiquement. Voir [GATEWAY_DIAGNOSTIC.md](GATEWAY_DIAGNOSTIC.md) pour les sources, les limites et le protocole préalable aux interventions.

### 4.2 — Scénario de laboratoire et référence initiale

État : laboratoire Linux virtuel validé en ICMP/TCP, avec inventaire complet, transfert synthétique, séries sans/avec transfert et contrôles séparés du superviseur. Les paramètres et critères du futur goulot virtuel sont définis ; le contrôle fonctionnel actif est validé en natif pour un transfert, et la campagne de trois paires est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1. La topologie du foyer, ses seuils et les références WAN restent à confirmer.

À partir d'un inventaire réel, choisir la plateforme et décrire le chemin du trafic à couvrir. Consigner la configuration initiale, les mesures au repos/sous charge, les seuils d'acceptation et le mécanisme de restauration à développer et tester avant une première modification. La comparaison doit distinguer le moteur configuré manuellement et le pilotage Coopace.

Livrés pour la préparation : `coopace-gateway inspect --json`, valeurs indisponibles explicites, provenance de compilation lorsqu’elle est disponible et [protocole de référence initiale](GATEWAY_BASELINE.md) avec [modèle d’expérience](templates/GATEWAY_EXPERIMENT.md). Ces fichiers ne sont pas une configuration exécutable ni une sauvegarde restaurable. La clôture de l’étape nécessite encore un scénario réel complété et ses mesures ; elle ne peut pas être déduite des tests d’export.

Un outil de comparaison hors ligne est aussi livré : `coopace latency compare --idle FICHIER --loaded FICHIER`. Il valide les rapports TCP locaux v1, recalcule leurs statistiques et affiche les différences descriptives avec les échecs. Les tests sur données contrôlées ne remplacent pas la référence réelle et ne démontrent aucun bénéfice réseau.

Un premier [scénario Linux virtuel](VIRTUAL_LAB.md) est maintenant défini : client, passerelle et serveur dans des espaces réseau neufs, routes spécifiques et sondes ICMP pour vérifier le passage IPv4. `scripts/lab-network.sh plan` le prévisualise ; `run` crée le laboratoire et tente de supprimer ses ressources avant de publier l'inventaire. `run-tcp` prépare cinq tentatives d'établissement TCP avec l'agent et une cible temporaire bornée, sans charge de saturation. Les tests de cycle de vie utilisent des outils simulés et le serveur TCP est testé en mémoire ; son essai en boucle locale peut être ignoré faute de permissions. Le [premier essai natif du 29 octobre](VALIDATION_VIRTUAL_LAB_2026-10-29.md) confirme les contrôles ICMP, cinq connexions TCP réussies sans échec et le nettoyage normal. Les références WAN sous charge et la restauration d'une passerelle réelle restent à valider.

La [revue du 29 octobre 2026](REVIEW_2026-10-29.md) consigne la correction d'une fenêtre d'interruption du nettoyage avant les essais natifs. Les transferts et séries décrits ci-dessous ont ensuite été réalisés ; ce bilan historique ne remplace pas l'état courant de l'étape 4.2.

Un [premier flux synthétique borné](VIRTUAL_LOAD.md) est maintenant préparé avec `run-load` : un transfert client → serveur de 8 Mio, plafond moyen applicatif de 1 Mio/s, délais de 12s en émission et 15s en réception. Les tests en mémoire et simulés couvrent volumes, cadence, erreurs et nettoyage. Un [premier transfert natif](VALIDATION_VIRTUAL_LOAD_2026-10-29.md) a envoyé et reçu les 8 Mio en environ huit secondes avec nettoyage normal ; le code de sortie exact `0` est également conservé. Il n'applique pas de politique de files et ne garantit pas une congestion du réseau virtuel.

Le mode [`run-series`](VIRTUAL_SERIES.md) associe maintenant trois paires sans/avec ce flux sur une même topologie, dans un ordre alterné, avec dix tentatives TCP par série. Il attend la première écriture et impose le recouvrement de la mesure avec la fenêtre d'écritures de charge. Les rapports complets et comparaisons par paire sont regroupés après nettoyage, y compris pour des séries sans réussite. Les tests de processus, de recouvrement et d'interruption passent sans réseau. Le [premier essai natif et son analyse descriptive](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) sont consignés : 60 connexions réussies sans échec, trois transferts complets, recouvrement et nettoyage conformes. Aucune amélioration causale ou saturation n'est déduite de cet essai. Ce résultat permet de préparer une référence avec goulot contrôlé.

Le [protocole de goulot virtuel v1](VIRTUAL_BOTTLENECK.md) fixe maintenant le point d'application, TBF/FIFO à 4 Mbit/s, les paramètres de collecte et les critères distincts de validité technique et de congestion. Il définit le périmètre jetable du nettoyage et les essais de panne requis. Le [contrôle fonctionnel du chemin actif et de la collecte périodique](VALIDATION_LAB_ACTIVE_2026-10-30.md) est maintenant validé en natif pour un transfert ; la [campagne de trois paires](LAB_CAMPAIGN.md) est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1. Les contrôles ciblés de réception et de statistiques sont consignés ci-dessous. Le goulot est maintenant qualifié dans ce laboratoire ; la référence CAKE manuelle reste à comparer.

Le [premier superviseur indépendant](LAB_GUARD.md) fournit deux contrôles sans file : fin normale et mort forcée du pilote, avec récupération de son descendant avant retrait des espaces possédés. Les tests emploient des espaces simulés et de vrais processus/signaux. Les [deux contrôles natifs du 29 octobre](VALIDATION_LAB_GUARD_2026-10-29.md) sont validés : sortie `0`, un descendant récupéré par contrôle, espaces et réservations retirés.

Le [cycle de vie de la file TBF](LAB_QUEUE.md) ajoute `plan-queue`, `check-queue` et `check-queue-crash` au superviseur, avec un module de configuration/relecture séparé. Le lien reste désactivé, sans adresse, route ou mesure de trafic. Les [quatre contrôles natifs du 29 octobre](VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés : deux sans file et deux avec TBF, paramètres effectifs conformes après fin normale ou mort forcée et nettoyage vérifié. Les erreurs d'ajout/relecture restent couvertes par les tests simulés.

Le [rapport optionnel de réception et les statistiques TBF](LAB_INSTRUMENTATION.md) sont maintenant implémentés. Les tests vérifient les fenêtres monotones, EOF, valeurs manquantes, compteurs en baisse et jauges distinctes ; deux contrôles de statistiques sous supervision sont disponibles sur lien désactivé. Les [trois contrôles natifs](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) sont validés : réception TCP locale de 32 785 octets avec JSON, puis quatre lectures TBF à zéro et nettoyage normal ou après mort forcée. Le [contrôle fonctionnel du chemin actif](LAB_ACTIVE.md) raccorde maintenant trois espaces neufs, TBF activé, un transfert de 8 Mio, dix sondes TCP et des lectures périodiques de statistiques. Les tests avec outils simulés et vrais processus couvrent fin normale, mort forcée avec trois descendants récupérés, échéance, erreurs de configuration et de collecte. Sa [première validation native du 30 octobre](VALIDATION_LAB_ACTIVE_2026-10-30.md) confirme les 8 Mio reçus, les dix connexions, la collecte périodique et le nettoyage normal ou après mort forcée. La [campagne des trois paires avec file](LAB_CAMPAIGN.md) intègre maintenant les contrôles ICMP, six phases, trois réceptions, statistiques périodiques et comparaisons strictes. Ses tests couvrent l'orchestration, la qualification, la conservation des preuves et le nettoyage après panne. Le [premier essai natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) valide les six phases, les trois réceptions, les comparaisons et le nettoyage après mort forcée : 60 connexions réussies et congestion observée selon v1. Le [protocole comparatif TBF/CAKE statique v1](CAKE_COMPARISON.md) définit maintenant trois blocs alternés, six campagnes neuves et les critères de latence/débit/échecs. Le [module CAKE et son contrôle de cycle de vie sur lien DOWN](LAB_CAKE.md) sont maintenant implémentés, avec validations spécifiques du producteur JSON, des options et des statistiques. Les tests avec commandes réseau simulées et vrais processus passent. Le [premier contrôle natif](VALIDATION_LAB_CAKE_2026-10-30.md) confirme les deux revérifications TBF et les deux modes CAKE : options/statistiques conformes sur lien DOWN et nettoyage après fin normale ou mort forcée. La prochaine activité est le chemin actif CAKE avec contrôle de panne ; la comparaison reste à développer. Les références du foyer et la restauration réelle restent ouvertes.

## Étape 5 — Décisions coopératives

État : à faire.

Introduire des décisions déterministes bornées, l'évaluation collective, l'abstention et le retour arrière. Compléter les intégrations des plateformes selon leurs capacités réelles.

Cette automatisation dépend de la validation des mesures et de la restauration à l'étape 4. Si la surcouche n'apporte pas de bénéfice par rapport au moteur existant, conserver l'intégration simple et réévaluer l'automatisation.

## Étapes ultérieures — Relais et ML facultatifs

État : recherche, à réévaluer selon les résultats.

Tester d'abord un tunnel manuel sur un véritable chemin alternatif. Étudier ensuite sa sélection automatique. Le ML ne sera envisagé qu'avec des données autorisées et un bénéfice reproductible face aux solutions existantes.

Le dossier [`ml/`](../ml/README.md) réserve ce module et décrit son périmètre ainsi que ses conditions d'intégration. Son développement reste différé.
