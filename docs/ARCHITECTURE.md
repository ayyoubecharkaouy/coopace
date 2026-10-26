# Architecture initiale

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
| `platforms/linux` | Adaptations réseau Linux, notamment les intégrations futures avec `tc` et CAKE/SQM. Compatibilité OpenWrt à vérifier selon le matériel et le packaging. |
| `platforms/windows` | Adaptations réseau Windows pour l'agent et étude d'une passerelle Windows. |
| `platforms/android` | Adaptations de l'agent Android, sous les contraintes de permissions et de cycle de vie du système. |

Les applications assemblent les contrats partagés et les adaptations correspondant au système. Le noyau métier reste indépendant des API du système et du tableau de bord. Le format des messages v2 est défini ; son interopérabilité devra être vérifiée lors de l'implémentation des clients dans d'autres langages.

Le noyau partagé sera une bibliothèque Go pour les applications de bureau. Les contrats du protocole utiliseront des messages JSON versionnés et resteront indépendants du langage. Cette arborescence ne suppose pas un langage unique sur toutes les plateformes.

## Règles de dépendance et de rangement

| Emplacement | Dépendances et limites |
| --- | --- |
| `packages/core` | Ne dépend ni des applications, ni du protocole réseau, ni des adaptations système. |
| `packages/protocol` | Définit les messages échangés. Ne dépend ni des applications ni des adaptations système. |
| `platforms/<système>` | Implémente les opérations du système derrière les contrats définis côté noyau. Ne dépend ni des applications ni des adaptations d'un autre système. |
| `apps/agent`, `apps/gateway` | Assemblent le noyau, le protocole et les adaptations compatibles avec le système courant. |
| `apps/dashboard` | Utilise le contrat de l'API exposée par les applications. Ne charge pas les adaptations réseau privilégiées. |

Un message réseau et un modèle métier ont des responsabilités distinctes. Leur conversion se fait à la frontière applicative ; elle ne doit pas introduire une dépendance circulaire entre `core` et `protocol`.

La structure est organisée par responsabilité, puis par système : une règle d'évaluation commune va dans `packages/core`, une mesure propre à Windows dans `platforms/windows`, et leur orchestration dans l'application concernée. La logique commune ne doit pas être dupliquée dans chaque adaptation.

Les tests propres à un module seront placés avec ce module, selon les conventions de la pile choisie. Un répertoire de tests entre plusieurs composants ne sera ajouté que lorsqu'un scénario d'intégration le nécessitera.

Les futurs services privilégiés et clients mobiles pourront nécessiter leurs propres points d'entrée ou paquets. Leur découpage sera décidé avec le packaging ; les dossiers actuels décrivent les responsabilités, pas un nombre imposé de processus ou d'installateurs.

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
- Méthode de mesure et critères d'acceptation du premier prototype.
