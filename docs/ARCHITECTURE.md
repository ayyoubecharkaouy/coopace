# Architecture initiale

## Périmètre

Cette organisation traduit l'architecture « Edge & Peers » du rapport `RAPPORT_COOPPACE_V5.md` fourni avec l'étude du projet. Elle définit les responsabilités du futur logiciel ; aucune capacité réseau n'est encore implémentée.

CoopPace est un produit composé de plusieurs applications et bibliothèques. Une installation peut réunir plusieurs rôles, par exemple passerelle et agent sur un même PC.

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

Les modules partagés peuvent contenir des spécifications, schémas ou bibliothèques ; leur forme dépendra de la pile technique retenue. Cette arborescence ne suppose pas un langage unique sur toutes les plateformes.

## Couverture et plateformes

- Les agents Windows, Linux et Android sont des cibles du produit. Aucun PC Linux n'est requis pour appartenir au groupe.
- La passerelle Linux/OpenWrt est la voie proposée dans le rapport pour réutiliser CAKE/SQM.
- Une passerelle Windows est envisageable, avec un moteur adapté à Windows. Sa faisabilité détaillée et ses performances restent à valider ; elle ne doit pas être présentée comme équivalente à CAKE sur la seule base de WFP ou des politiques QoS.
- Une passerelle Android ne fait pas partie du périmètre initial.
- Une installation sans passerelle CoopPace ne peut pas promettre une gestion globale des files du foyer.
- Même avec des agents sur chaque appareil, le trafic doit traverser le point d'application pour être géré par celui-ci.

## Contraintes des futures interventions

Toute modification réseau devra annoncer ses permissions, vérifier les capacités locales et disposer d'une restauration adaptée au risque. Les données collectées seront minimales, locales par défaut, sans interception TLS ni journalisation des contenus.

Les fonctions de relais exigeront un consentement distinct. Elles ne seront automatisées qu'après comparaison avec un chemin manuel et vérification du bénéfice collectif.

## Décisions encore ouvertes

- Langages, outils de compilation et packaging de chaque application.
- Premier système et première fonction à implémenter.
- Contrats des adaptations système et séparation des privilèges.
- Découverte, authentification des membres et stockage local.
- Méthode de mesure et critères d'acceptation du premier prototype.
