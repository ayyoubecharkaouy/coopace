# Architecture et organisation du projet

## Périmètre

Cette organisation traduit l'architecture « Edge & Peers » du rapport historique `RAPPORT_COOPPACE_V5.md`, rédigé sous l'ancien nom du projet et fourni avec l'étude. Elle définit les responsabilités et limites du logiciel ; l'état réellement implémenté est recensé dans [PRODUCT.md](PRODUCT.md).

Coopace est un produit composé de plusieurs applications et bibliothèques. Une installation peut réunir plusieurs rôles, par exemple passerelle et agent sur un même PC.

Le [périmètre produit et ses critères de réussite](PRODUCT.md) servent de référence pour les priorités. Les applications et capacités décrites ci-dessous sont des responsabilités cibles ; leur présence dans l'arborescence ne signifie pas qu'elles sont implémentées.

Les [choix techniques de l'étape 2.1](TECH_STACK.md) retiennent Go pour le noyau et les applications Linux/Windows, et Kotlin pour l'intégration Android. La réutilisation du noyau Go sur Android reste à valider.

## Applications

| Module | Responsabilité |
| --- | --- |
| `apps/gateway` | Collecter les mesures de la passerelle, appliquer des politiques réseau autorisées et restaurer la configuration précédente. |
| `apps/agent` | Faire participer un appareil volontaire au groupe, fournir les mesures disponibles et exécuter uniquement les actions autorisées localement. |
| `apps/dashboard` | Présenter les appareils, les mesures, les capacités et les actions, avec activation et annulation explicites. |

La passerelle est un point de passage des données. Ce rôle ne lui attribue pas automatiquement celui de chef du protocole coopératif. Le mécanisme de découverte et de coordination reste à spécifier.

## Code partagé et adaptations système

| Module | Responsabilité |
| --- | --- |
| `packages/core` | Modèles métier, capacités, consentements, décisions bornées, abstention et règles d'évaluation indépendantes des systèmes. |
| `packages/protocol` | Définition versionnée des messages et de leur validation : identité, capacités, mesures et propositions d'actions. |
| `platforms/linux` | Compteurs et inventaire Linux, avec lecture des files par `tc` ; modification des files et intégration CAKE/SQM futures. Compatibilité OpenWrt à vérifier selon le matériel et le packaging. |
| `platforms/windows` | Adaptations réseau Windows pour l'agent et étude d'une passerelle Windows. |
| `platforms/android` | Adaptations de l'agent Android, sous les contraintes de permissions et de cycle de vie du système. |

Les applications assemblent les contrats partagés et les adaptations correspondant au système. Le noyau métier reste indépendant des API du système et du tableau de bord. Le format des messages v2 est défini ; son interopérabilité devra être vérifiée lors de l'implémentation des clients dans d'autres langages.

Le noyau partagé sera une bibliothèque Go pour les applications de bureau. Les contrats du protocole utiliseront des messages JSON versionnés et resteront indépendants du langage. Cette arborescence ne suppose pas un langage unique sur toutes les plateformes.

Les composants de l'arborescence sont des unités de responsabilité. Côté Go, le dépôt possède un seul module défini par `go.mod`, et plusieurs paquets ; les dossiers `apps`, `packages` et `platforms` ne nécessitent pas de modules Go séparés. Les répertoires réservés à Windows, Android, au tableau de bord et au ML gardent leur README tant que leur implémentation n'a pas commencé.

## Règles de dépendance et de rangement

| Emplacement | Dépendances et limites |
| --- | --- |
| `packages/core` | Ne dépend ni des applications, ni du protocole réseau, ni des adaptations système. |
| `internal/strictjson` | Contrôles JSON partagés en Go, avec la bibliothèque standard seule ; aucun format métier ni accès système. |
| `packages/protocol` | Définit les messages échangés. Ne dépend ni des applications ni des adaptations système. |
| `platforms/<système>` | Implémente les opérations du système derrière les contrats définis côté noyau. Ne dépend ni des applications ni des adaptations d'un autre système. |
| `apps/agent`, `apps/gateway` | Assemblent le noyau, le protocole et les adaptations compatibles avec le système courant. |
| `apps/dashboard` | Utilise le contrat de l'API exposée par les applications. Ne charge pas les adaptations réseau privilégiées. |

Un message réseau et un modèle métier ont des responsabilités distinctes. Leur conversion se fait à la frontière applicative ; elle ne doit pas introduire une dépendance circulaire entre `core` et `protocol`.

La structure est organisée par responsabilité, puis par système : une règle d'évaluation commune va dans `packages/core`, une mesure propre à Windows dans `platforms/windows`, et leur orchestration dans l'application concernée. La logique commune ne doit pas être dupliquée dans chaque adaptation.

Les tests propres à un module seront placés avec ce module, selon les conventions de la pile choisie. Un répertoire de tests entre plusieurs composants ne sera ajouté que lorsqu'un scénario d'intégration le nécessitera.

Le découpage des fichiers suit aussi les responsabilités :

- Les modèles et règles partagés restent dans `packages/core`, avec notamment `identity.go` pour l'empreinte publique et `consent.go` pour les autorisations de groupe.
- Les messages échangés restent dans `packages/protocol`. Les rapports locaux propres à une application restent dans ses paquets `internal`.
- Dans la CLI de l'agent, `cli.go` répartit les commandes ; `observe.go` contient l'orchestration et l'affichage de l'observation, comme les fichiers dédiés à la latence, à l'identité et au groupe.
- L'inventaire Linux sépare `gateway.go` pour la collecte, `gateway_parse.go` pour le décodage pur et `gateway_linux.go` pour les accès système et processus externes. Les tests correspondants restent à côté de ces fichiers ; les suffixes et contraintes de compilation distinguent les sources natives.

Le préfixe commun des fichiers regroupe une fonctionnalité dans son paquet. Créer un sous-paquet seulement lorsqu'une responsabilité ou une dépendance distincte le justifie ; les modèles, parseurs et rapports n'ont pas besoin d'un dossier global commun. Les fichiers générés et états locaux restent dans les emplacements exclus de Git, notamment `.local/` et `.cache/`.

Le contrôle des clés JSON et des limites est factorisé dans `internal/strictjson`, partagé par le protocole et la lecture des rapports TCP. Les schémas, leurs champs requis et les conversions restent dans leurs composants respectifs. Le comparateur de rapports appartient à `apps/agent/internal/latency` et sa commande à la CLI de l'agent ; il n'ouvre aucune connexion.

Les scénarios de laboratoire restent dans `scripts`, séparés des applications distribuées et des adaptations de production. `lab-network.sh` prépare uniquement des espaces réseau Linux neufs ; ses tests utilisent de faux outils dans `scripts/tests`. Le sous-dossier `scripts/lab-tcp` contient une cible TCP bornée en Go et ses tests ; le mode `run-tcp` l'associe à la mesure existante de l'agent, sans importer son code interne ni générer de charge. `scripts/lab-load` contient l'émetteur/récepteur de données synthétiques utilisé par `run-load`, avec ses propres limites et tests ; il ne dépend pas des applications. Ces outils ne sont pas un moteur de passerelle, et le diagnostic de l'application conserve son mode lecture seule. Voir [VIRTUAL_LAB.md](VIRTUAL_LAB.md) et [VIRTUAL_LOAD.md](VIRTUAL_LOAD.md).

`scripts/lab-series.py` orchestre les outils et la CLI de l'agent par arguments explicites, sans shell ni import des paquets internes applicatifs. Il vérifie les horodatages de charge et appelle le comparateur existant sur des rapports temporaires privés. Ses tests Python restent dans `scripts/tests`. Le shell possède les espaces et le PID de ce pilote ; le pilote possède et arrête ses processus avant le nettoyage des espaces. Voir [VIRTUAL_SERIES.md](VIRTUAL_SERIES.md).

`scripts/lab-guard.py` fournit séparément le [superviseur indépendant](LAB_GUARD.md) : il possède trois espaces neufs et un groupe de processus distinct, puis récupère le pilote et ses descendants avant de retirer les espaces. Ses premiers contrôles sans file sont validés en natif. Le module voisin `scripts/lab_queue.py` vérifie le [cycle de vie d'une file TBF sur lien désactivé](LAB_QUEUE.md), sous ce même superviseur ; ses [premiers contrôles natifs](VALIDATION_LAB_QUEUE_2026-10-29.md) sont également validés. Les commandes historiques de `lab-network.sh` restent distinctes. `scripts/lab-active.py` et le module voisin `lab_active.py` réutilisent ce superviseur et les outils de processus de `lab-series.py` pour un [contrôle fonctionnel actif](LAB_ACTIVE.md), avec un seul transfert, des sondes et des statistiques périodiques. Ce contrôle est testé avec des outils simulés et sa [première validation native](VALIDATION_LAB_ACTIVE_2026-10-30.md) est consignée ; la [campagne de trois paires](LAB_CAMPAIGN.md) est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1. Python 3 et sa bibliothèque standard sont utilisés pour ces pilotes et les tests de développement ; ils ne sont pas une dépendance d'exécution des applications Go et ne constituent pas une implémentation du ML.

Les futurs services privilégiés et clients mobiles pourront nécessiter leurs propres points d'entrée ou paquets. Leur découpage sera décidé avec le packaging ; les dossiers actuels décrivent les responsabilités, pas un nombre imposé de processus ou d'installateurs.

Dans `scripts/lab-load`, `receive.go` mesure maintenant la réception et prépare son JSON optionnel ; `transfer.go` conserve l'émission et les utilitaires communs. `lab_queue.py` sépare les compteurs cumulés des jauges instantanées et invalide une différence lorsque les compteurs diminuent. Ces [mesures de laboratoire](LAB_INSTRUMENTATION.md) restent locales, indépendantes des formats du groupe ; leur [première validation native](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) est consignée pour la réception en boucle locale et les statistiques sur liens désactivés. Leur intégration au contrôle fonctionnel actif est [validée en natif](VALIDATION_LAB_ACTIVE_2026-10-30.md) pour un transfert ; la [campagne de trois paires](LAB_CAMPAIGN.md) est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1.

`scripts/lab-campaign.py` et `lab_campaign.py` réutilisent ce superviseur, la topologie et la mesure loaded de `lab_active.py`. Le pilote garde un unique groupe pendant six phases et attend les accusés sur stdin ; le superviseur capture la file, contrôle son vidage et compare les fichiers avec la CLI existante avant d'autoriser la suite. Les fichiers de preuves sont créés exclusivement dans le dossier d'expérience et restent en cas d'échec. Les modes précédents gardent stdin fermé. Voir [LAB_CAMPAIGN.md](LAB_CAMPAIGN.md).

`scripts/lab-cake.py` et `lab_cake.py` ajoutent séparément le [contrôle CAKE DOWN](LAB_CAKE.md). Ils réutilisent le superviseur, la préparation neutre `QueueCheck.prepare_link`, les commandes bornées et les différences de compteurs de `lab_queue.py`. La validation des options, du producteur JSON et des statistiques CAKE reste dans `lab_cake.py` ; elle n'utilise pas le validateur TBF. Le [premier contrôle natif CAKE DOWN](VALIDATION_LAB_CAKE_2026-10-30.md) est validé ; le [contrôle fonctionnel CAKE actif](LAB_CAKE_ACTIVE.md) réutilise maintenant l'activation commune et le même pilote de transfert ; sa [première validation native](VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md) est consignée. Son module `lab_cake_active.py` raccorde le validateur CAKE et conserve un journal de relevés exclusif hors de la réservation jetable ; son entrée `lab-cake-active.py` reste séparée des commandes TBF.

La [campagne CAKE de trois paires](LAB_CAKE_CAMPAIGN.md) conserve son entrée `lab-cake-campaign.py` et son module `lab_cake_campaign.py`. Elle raccorde `CakeCheck` à la classe commune `Passage` et réutilise le pilote et la coordination de `lab_campaign.py`. Les décisions de charge CAKE restent séparées de la qualification TBF ; l’extension du moteur commun conserve son comportement TBF par défaut. Toutes les lectures CAKE sont journalisées hors réservation. Les tests sont simulés ; la validation native de cette campagne reste à réaliser.

À l'étape 4.1, `apps/gateway/cmd/coopace-gateway` fournit une commande distincte de l'agent : `inspect`, en lecture seule sous Linux. Ses paquets internes orchestrent les lectures de `platforms/linux` et utilisent les modèles d'inventaire du noyau. Aucun paquet interne d'une application n'est importé par l'autre. Ce découpage prépare les rôles ; il ne démarre pas un service privilégié et ne fixe pas le nombre d'installateurs du produit final. Voir [GATEWAY_DIAGNOSTIC.md](GATEWAY_DIAGNOSTIC.md).

La première observation suit ce découpage : compteurs lus par l'adaptation Linux, différences calculées dans le noyau sans accès système, puis orchestration et affichage par l'agent. Les modèles et horodatages locaux sont convertis vers les contrats réseau par l’agent. Voir [OBSERVATIONS.md](OBSERVATIONS.md).

La mesure TCP de l'étape 3.2 utilise la bibliothèque réseau portable de Go dans l'agent, vers une cible explicite. Les statistiques restent pures dans le noyau. Son JSON versionné est un format local de conservation, distinct du protocole du groupe. Voir [LATENCY.md](LATENCY.md).

À l'étape 3.3, les premiers contrats du groupe sont définis dans `packages/protocol` et convertis vers le noyau par `apps/agent/internal/group`. La génération et le stockage privé de l'identité relèvent de l'agent ; le noyau calcule seulement l'empreinte publique et valide le consentement, sans I/O. Les [fondations d'identité et de groupe](IDENTITY_AND_GROUP.md) définissent ces frontières. À l'étape 3.4, l'agent ajoute l'approbation et le consentement persistés, TLS mutuel et un échange borné ; le protocole v2 fournit le cadrage et l'ordre des messages sans I/O réseau. Voir [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md).

## Module ML facultatif

Le dossier [`ml/`](../ml/README.md) est réservé aux futures expériences, à l'entraînement et à l'évaluation des modèles. Le noyau, les agents et la passerelle doivent fonctionner sans ce module et sans dépendance aux outils d'entraînement.

Les prédictions seront des entrées facultatives pour la décision applicative. Les garde-fous déterministes conserveront le contrôle des interventions. L'export des modèles et l'intégration de l'inférence restent à spécifier après validation scientifique.

## Couverture et plateformes

- Les agents Windows, Linux et Android sont des cibles du produit. Aucun PC Linux n'est requis pour appartenir au groupe.
- La passerelle Linux/OpenWrt est la voie proposée dans le rapport pour réutiliser CAKE/SQM.
- Une passerelle Windows est envisageable, avec un moteur adapté à Windows. Sa faisabilité détaillée et ses performances restent à valider ; elle ne doit pas être présentée comme équivalente à CAKE sur la seule base de WFP ou des politiques QoS.
- Une passerelle Android ne fait pas partie du périmètre initial.
- Une installation sans passerelle Coopace ne peut pas promettre une gestion globale des files du foyer.
- Même avec des agents sur chaque appareil, le trafic doit traverser le point d'application pour être géré par celui-ci.

## Contraintes des futures interventions

Toute modification réseau devra annoncer ses permissions, vérifier les capacités locales et disposer d'une restauration adaptée au risque. Les données collectées seront minimales, locales par défaut, sans interception TLS ni journalisation des contenus.

Avant toute automatisation, la restauration devra pouvoir fonctionner même si le processus de pilotage est interrompu. Le comportement en cas de panne devra être explicite : maintien du passage du trafic ou blocage selon la politique choisie, avec vérification d'IPv6 et du DNS.

Les fonctions de relais exigeront un consentement distinct. Elles ne seront automatisées qu'après comparaison avec un chemin manuel et vérification du bénéfice collectif.

## Décisions encore ouvertes

- Packaging de chaque application et validation effective sur les systèmes cibles.
- Réutilisation du noyau Go dans l'application Android Kotlin.
- Contrats des adaptations système et séparation des privilèges.
- Découverte, groupe à plusieurs pairs, renouvellement des certificats et stockage protégé de clé sur les autres systèmes.
- Mesures complémentaires et critères du premier prototype de passerelle réelle ; la méthode TCP et les paramètres du goulot synthétique sont déjà documentés.
