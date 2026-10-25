# Architecture initiale

## Périmètre

Cette organisation traduit l'architecture « Edge & Peers » du rapport historique `RAPPORT_COOPPACE_V5.md`, rédigé sous l'ancien nom du projet et fourni avec l'étude. Elle définit les responsabilités du futur logiciel ; aucune capacité réseau n'est encore implémentée.

Coopace est un produit composé de plusieurs applications et bibliothèques. Une installation peut réunir plusieurs rôles, par exemple passerelle et agent sur un même PC.

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

Les applications utiliseront les contrats partagés et les adaptations correspondant au système. Le noyau métier doit rester indépendant des API du système et du tableau de bord. Le format des messages sera défini avant d'implémenter des clients dans plusieurs langages.

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

Les fonctions de relais exigeront un consentement distinct. Elles ne seront automatisées qu'après comparaison avec un chemin manuel et vérification du bénéfice collectif.

## Décisions encore ouvertes

- Packaging de chaque application et validation effective sur les systèmes cibles.
- Détails de la commande locale `coopace status`, avec premiers essais sous Linux et cible Windows.
- Réutilisation du noyau Go dans l'application Android Kotlin.
- Contrats des adaptations système et séparation des privilèges.
- Découverte, authentification des membres et stockage local.
- Méthode de mesure et critères d'acceptation du premier prototype.
