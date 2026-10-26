# Documentation de Coopace

Ce dossier rassemble les décisions, les procédures et les limites du projet. Le [périmètre produit](PRODUCT.md) et la [feuille de route](ROADMAP.md) décrivent l'état courant ; les bilans datés conservent le contexte de leur rédaction.

## Comprendre et développer le projet

| Document | Contenu |
| --- | --- |
| [PRODUCT.md](PRODUCT.md) | Produit final visé, fonctions disponibles et critères de réussite. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Responsabilités des composants, dépendances et rangement du code. |
| [ROADMAP.md](ROADMAP.md) | Progression par étapes et validations restantes. |
| [TECH_STACK.md](TECH_STACK.md) | Choix de Go et Kotlin, outils et décisions différées. |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Installation locale, commandes, compilation et tests. |
| [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md) | Compilation Windows et vérifications natives restant à effectuer. |

## Fonctions du prototype

| Document | Fonction et limites |
| --- | --- |
| [OBSERVATIONS.md](OBSERVATIONS.md) | Compteurs locaux par interface sous Linux. |
| [LATENCY.md](LATENCY.md) | Établissement TCP, export local et protocole de référence. |
| [IDENTITY_AND_GROUP.md](IDENTITY_AND_GROUP.md) | Identités, consentements et contrats du groupe. |
| [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md) | Essai entre deux pairs approuvés, TLS et révocation. |
| [GATEWAY_DIAGNOSTIC.md](GATEWAY_DIAGNOSTIC.md) | Inventaire de passerelle en lecture seule et préparation des expériences. |

## Bilans datés

La [revue du 26 octobre 2026](REVIEW_2026-10-26.md) consigne le démarrage et la cohérence avec le rapport V5, avant le développement du diagnostic de l'étape 4.1. Elle ne remplace pas l'état courant du produit.

Les README des [applications agent](../apps/agent/README.md) et [passerelle](../apps/gateway/README.md), du [noyau](../packages/core/README.md), du [protocole](../packages/protocol/README.md) et des [adaptations Linux](../platforms/linux/README.md) détaillent le code de chaque composant. Le [module ML](../ml/README.md) garde son périmètre futur dans son propre dossier.

Ajouter une procédure technique ici lorsqu'une fonction le nécessite, puis la référencer dans cet index. Garder les détails propres à un composant dans son README et les résultats historiques dans des documents explicitement datés.
