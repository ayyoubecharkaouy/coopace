# Noyau métier

État : premiers modèles et tests écrits à l'étape 2.2. Compilation et exécution des tests en attente de disponibilité de Go dans l'environnement de travail.

Ce module accueille les modèles et règles communs. Le premier périmètre comprend les appareils, les rôles et les capacités. Les consentements, mesures et décisions seront ajoutés progressivement.

Il est développé en Go et reste indépendant des API réseau propres aux systèmes et du tableau de bord. Les applications Linux et Windows partageront cette bibliothèque. Sa réutilisation sur Android nécessite une validation séparée, décrite dans les [choix techniques](../../docs/TECH_STACK.md).

## Modèles présents

| Type | Signification |
| --- | --- |
| `DeviceID` | Identifiant local opaque ; sa génération et sa persistance seront définies ultérieurement. |
| `OperatingSystem` | Plateforme cible : `linux`, `windows` ou `android`. |
| `Role` | Rôle `agent` ou `gateway` ; un appareil peut cumuler les deux. |
| `Capability` | Aptitude technique déclarée : observation locale, gestion du trafic de la passerelle ou relais. |
| `Device` | Description d'un appareil et validation de sa cohérence. |

Le tableau de bord est une interface, pas un rôle de membre du groupe. Le relais est une capacité, pas un rôle qui autorise automatiquement l'utilisation de l'appareil.

## Validation

`Device.Validate()` vérifie :

- un identifiant non vide, sans espace ni caractère de contrôle ;
- un nom non blanc et sans caractère de contrôle, avec prise en charge des noms Unicode ;
- un système connu et au moins un rôle connu ;
- l'absence de doublons dans les rôles et capacités, et l'absence de capacités inconnues ;
- la présence du rôle `gateway` lorsque la gestion du trafic de passerelle est déclarée.

Une liste de capacités vide est valide lorsque leur évaluation n'a pas encore eu lieu. Aucune capacité n'est déduite automatiquement du seul nom du système.

La validation ne modifie pas la description et ne réalise aucune opération réseau. Elle doit être appelée à nouveau après modification des champs. Déclarer une capacité ne prouve ni sa disponibilité réelle ni le consentement de l'utilisateur ; ces vérifications appartiendront aux intégrations et aux règles d'autorisation.

Les champs métier ne définissent pas le futur format JSON : les contrats des messages et leur conversion resteront séparés dans `packages/protocol` et les applications.

Voir les [instructions de préparation et de vérification](../../docs/DEVELOPMENT.md).
