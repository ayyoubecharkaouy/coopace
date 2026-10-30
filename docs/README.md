# Documentation de Coopace

Ce dossier rassemble les décisions, les procédures et les limites du projet. Le [périmètre produit](PRODUCT.md) et la [feuille de route](ROADMAP.md) décrivent l'état courant ; les bilans datés conservent le contexte de leur rédaction. Pour connaître ce qui fonctionne aujourd'hui, commencer par ces deux documents. Pour reproduire un essai, suivre son protocole ; son compte rendu décrit uniquement l'exécution consignée.

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

Le [protocole de référence initiale](GATEWAY_BASELINE.md) décrit l’export JSON du diagnostic et la préparation de l’étape 4.2. Le [modèle d’expérience passerelle](templates/GATEWAY_EXPERIMENT.md) est à copier dans un dossier local pour renseigner le scénario ; il ne contient aucune mesure réelle.

Le [laboratoire Linux virtuel](VIRTUAL_LAB.md) fournit un scénario concret pour préparer le point de passage IPv4, avec prévisualisation, création explicite et nettoyage de ressources propres. Un [premier essai natif ICMP/TCP du 29 octobre](VALIDATION_VIRTUAL_LAB_2026-10-29.md) est consigné, avec inventaire complet, cinq connexions réussies sans échec et nettoyage normal. Les références WAN restent à recueillir.

Le [premier transfert synthétique borné](VIRTUAL_LOAD.md) définit ensuite `run-load`, son volume, son plafond moyen, ses délais et ses critères. Les [premières observations natives](VALIDATION_VIRTUAL_LOAD_2026-10-29.md) confirment 8 Mio transférés et reçus, avec nettoyage normal ; le code exact `0` est conservé.

Les [séries sans et avec transfert](VIRTUAL_SERIES.md) définissent `run-series`, trois paires de mesures, leur ordre, le contrôle du recouvrement et le rapport groupé. Un [premier essai natif et son analyse descriptive](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) sont consignés : 60 réussites sans échec, trois transferts complets et recouvrement conforme.

Le [protocole de goulot virtuel contrôlé](VIRTUAL_BOTTLENECK.md) fixe la prochaine expérience : TBF/FIFO à 4 Mbit/s dans la passerelle neuve, critères de congestion, mesures à compléter et périmètre de nettoyage. La [campagne de trois paires](LAB_CAMPAIGN.md) est maintenant implémentée et testée avec des commandes réseau simulées ; son [contrôle de panne et sa première collecte native](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) sont validés : 60 connexions réussies, trois réceptions complètes, congestion observée selon v1 et nettoyage confirmé.

Le [superviseur indépendant du laboratoire](LAB_GUARD.md) prépare ce nettoyage avec deux contrôles ciblés : fin normale et mort forcée du pilote. Les tests utilisent des espaces simulés et de vrais processus ; les [deux premiers contrôles natifs sont validés](VALIDATION_LAB_GUARD_2026-10-29.md). L'intégration à la campagne de mesures avec file active est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1.

Le [cycle de vie de la file TBF](LAB_QUEUE.md) est implémenté sous ce superviseur : prévisualisation, création et relecture sur lien désactivé, puis nettoyage après fin normale ou mort forcée du pilote. Les [premiers contrôles natifs](VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés, avec revérification des modes sans file et paramètres TBF effectifs conformes. La campagne de trois paires avec goulot est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1.

L'[instrumentation de réception et de file](LAB_INSTRUMENTATION.md) définit le JSON optionnel du récepteur, les compteurs cumulés, les jauges instantanées et les différences indisponibles. Le code et les tests en mémoire ou simulés sont livrés ; les [premiers contrôles natifs](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) sont validés pour la réception locale et les statistiques sur liens désactivés. Le [contrôle fonctionnel du chemin actif](LAB_ACTIVE.md) est maintenant implémenté avec un seul transfert, dix sondes, lectures périodiques et récupération des outils après mort forcée. Sa [première validation native](VALIDATION_LAB_ACTIVE_2026-10-30.md) confirme réception complète, dix connexions réussies, collecte et nettoyage dans les deux modes ; la campagne de trois paires est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1.

Le [protocole comparatif TBF/CAKE statique v1](CAKE_COMPARISON.md) fixe trois blocs alternés, six campagnes neuves, paramètres et critères de décision avant collecte. Il distingue validité technique, charge qualifiée, garde-fous et amélioration observée. L'adaptation CAKE et le pilote comparatif ne sont pas encore implémentés ; aucun essai CAKE n'est réalisé.

## Bilans datés

La [revue du 29 octobre 2026](REVIEW_2026-10-29.md) revérifie le projet depuis le démarrage, consigne le correctif de nettoyage du laboratoire et définit les validations nécessaires pour poursuivre l'étape 4.2.

La [revue du 26 octobre 2026](REVIEW_2026-10-26.md) consigne le démarrage et la cohérence avec le rapport V5, avant le développement du diagnostic de l'étape 4.1. Elle ne remplace pas l'état courant du produit.

Les README des [applications agent](../apps/agent/README.md) et [passerelle](../apps/gateway/README.md), du [noyau](../packages/core/README.md), du [protocole](../packages/protocol/README.md) et des [adaptations Linux](../platforms/linux/README.md) détaillent le code de chaque composant. Le [module ML](../ml/README.md) garde son périmètre futur dans son propre dossier.

Ajouter une procédure technique ici lorsqu'une fonction le nécessite, puis la référencer dans cet index. Garder les détails propres à un composant dans son README et les résultats historiques dans des documents explicitement datés. Après une validation, actualiser les états courants et la prochaine activité des protocoles concernés, sans réécrire les mesures ni les copies de protocoles figées dans `.local/experiments/`. Distinguer systématiquement compilation, tests en mémoire ou simulés, exécution native, et bénéfice réseau démontré.
