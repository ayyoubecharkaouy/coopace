# Noyau métier

État : modèles d’appareils, observations, statistiques TCP, identité, consentement et inventaire ; première planification CAKE hors ligne ajoutée à la préparation de l’étape 4.2 sous Linux x86_64 avec Go 1.27.3. Le formatage, les tests, l'analyse statique et la compilation passent. L'exécution sur les autres systèmes reste à vérifier.

Ce module accueille les modèles et règles communs : appareils, rôles, capacités, consentements et premières mesures. Une première planification CAKE statique hors ligne est maintenant ajoutée ; les autres décisions restent à développer.

Les modèles `LatencySample`, `LatencySummary` et `LatencyDistribution` ajoutent les statistiques des durées d'établissement TCP. Le calcul des percentiles reste indépendant du mécanisme de mesure et ne déduit aucun diagnostic de congestion.

Il est développé en Go et reste indépendant des API réseau propres aux systèmes et du tableau de bord. Les applications Linux et Windows partageront cette bibliothèque. Sa réutilisation sur Android nécessite une validation séparée, décrite dans les [choix techniques](../../docs/TECH_STACK.md).

## Modèles présents

| Type | Signification |
| --- | --- |
| `DeviceID` | Identifiant indépendant du nom/IP. Les identités de groupe utilisent l'empreinte de clé publique calculée par `DeviceIDForPublicKey`. |
| `OperatingSystem` | Plateforme cible : `linux`, `windows` ou `android`. |
| `Role` | Rôle `agent` ou `gateway` ; un appareil peut cumuler les deux. |
| `Capability` | Aptitude technique déclarée : observation locale, gestion du trafic de la passerelle ou relais. |
| `Device` | Description d'un appareil et validation de sa cohérence. |

Le tableau de bord est une interface, pas un rôle de membre du groupe. Le relais est une capacité, pas un rôle qui autorise automatiquement l'utilisation de l'appareil.

## Validation

`Device.Validate()` vérifie :

- un identifiant en UTF-8 valide, non vide, sans espace ni caractère de contrôle ;
- un nom en UTF-8 valide, non blanc et sans caractère de contrôle, avec prise en charge des noms Unicode ;
- un système connu et au moins un rôle connu ;
- l'absence de doublons dans les rôles et capacités, et l'absence de capacités inconnues ;
- la présence du rôle `gateway` lorsque la gestion du trafic de passerelle est déclarée.

Une liste de capacités vide est valide lorsque leur évaluation n'a pas encore eu lieu. Aucune capacité n'est déduite automatiquement du seul nom du système.

La validation ne modifie pas la description et ne réalise aucune opération réseau. Elle doit être appelée à nouveau après modification des champs. Déclarer une capacité ne prouve ni sa disponibilité réelle ni le consentement de l'utilisateur ; ces vérifications appartiendront aux intégrations et aux règles d'autorisation.

Les champs métier ne définissent pas le format JSON : les contrats des messages et leur conversion restent séparés dans `packages/protocol` et les applications.

Voir les [instructions de préparation et de vérification](../../docs/DEVELOPMENT.md).

## Observations de trafic

`InterfaceCounters` contient des compteurs cumulés d'octets reçus et envoyés par nom d'interface. `MeasureTraffic()` compare deux lectures sur une durée positive et retourne des `InterfaceObservation`, avec un `InterfaceTraffic` uniquement lorsque les taux sont calculables.

Les différences sont calculées avant conversion en taux d'octets par seconde. Les interfaces apparues, disparues et les compteurs en baisse sont explicitement indisponibles. Une activité réellement nulle conserve une mesure à zéro. Les doublons, noms invalides et durées non positives sont rejetés.

Cette fonction ne réalise aucune lecture système et n'additionne pas les interfaces. La collecte, les horodatages et les limites d'interprétation sont décrits dans [OBSERVATIONS.md](../../docs/OBSERVATIONS.md).

## Statistiques de latence

`SummarizeLatency()` calcule min, p50, p95, p99 et max par rang supérieur sur les seuls essais réussis. Les échecs restent comptés séparément et une série sans réussite n'a pas de distribution. Les durées négatives, catégories inconnues et échecs portant une fausse durée sont rejetés. Les données originales ne sont pas modifiées.

Le noyau ne fait aucune connexion et ne définit aucun format JSON. La mesure TCP et l'export local sont orchestrés dans l'agent ; voir [LATENCY.md](../../docs/LATENCY.md).

## Identité et consentement

`DeviceIDForPublicKey` calcule une empreinte SHA-256 à partir des 32 octets publics Ed25519, sans générer ni stocker de secret. `GroupConsent` sépare adhésion, partage des observations et autorisation de relais, tous liés à un groupe et à un appareil. Les permissions sont fausses par défaut ; le partage exige un consentement cohérent et la correspondance du groupe et de l'identité.

La génération/lecture de la clé appartient à l'agent, et l'authentification réseau au transport TLS assemblé par l'agent. Les contrats sont convertis vers `Device` à la frontière applicative pour réutiliser les règles métier. Voir [IDENTITY_AND_GROUP.md](../../docs/IDENTITY_AND_GROUP.md).

Le calcul d'empreinte est dans [identity.go](identity.go), et le modèle de consentement dans [consent.go](consent.go), avec leurs tests respectifs. Cette séparation conserve le même paquet `core` et la même API.

## Inventaire de passerelle

`GatewayReading` conserve explicitement la disponibilité d'une valeur : une donnée inaccessible ne devient pas un booléen faux ou une liste vide. `GatewayInventory` regroupe interfaces, flags de forwarding, capacité observée, outils, routes par défaut et files. Ces types ne détectent ni une interface WAN ni l'aptitude à gérer le réseau ; ils n'effectuent aucun I/O et ne constituent pas une autorisation.

La collecte appartient à l'adaptation Linux, et son affichage à l'application passerelle. Voir [GATEWAY_DIAGNOSTIC.md](../../docs/GATEWAY_DIAGNOSTIC.md).

## Planification CAKE statique hors ligne

`PlanStaticCake` évalue un `CakePlanningInput` et retourne un `CakePlan` : abstention, conservation de la référence déjà conforme ou proposition du profil fixe `cake-ipv4-lab-4mbit-v1`. La proposition exige le laboratoire IPv4 jetable, une file déclarée non configurée et six prérequis confirmés. Une passerelle existante reste hors périmètre ; une file inconnue ou différente n'est jamais remplacée.

Les hypothèses d'entrée ne sont pas des preuves ni des autorisations. La fonction ne collecte rien, ne déduit pas une capacité WAN, ne réalise aucun I/O et ne modifie pas l'entrée. Les modèles ne définissent aucun JSON ; la [commande de simulation de la passerelle](../../docs/GATEWAY_PLANNING.md) fournit maintenant ce raccordement. L’exécution réseau reste à développer. Voir le [contrat, la référence et les limites](../../docs/STATIC_CAKE_PLANNING.md).
