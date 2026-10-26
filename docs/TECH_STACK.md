# Choix techniques — étape 2.1

Date : 25 octobre 2026.

État : choix retenus pour le premier prototype. Aucun outil, paquet ou programme n'est installé ou implémenté par cette décision.

## Besoins qui guident le choix

- Développer progressivement un agent Linux et Windows avec un noyau commun.
- Préparer la coordination réseau et les adaptations propres aux systèmes.
- Distribuer à terme des exécutables adaptés au système de l'utilisateur.
- Conserver une intégration Android native pour les permissions et services mobiles.
- Réutiliser les moteurs réseau existants ; le noyau applicatif ne remplace pas le gestionnaire de files du système.

## Décisions

| Partie | Choix | Portée |
| --- | --- | --- |
| `packages/core` | Go | Modèles et règles métier partagés entre les applications de bureau. |
| `apps/agent` | Go pour Linux et Windows | Commande locale `coopace status` ; intégration comme service plus tard. |
| `apps/gateway` | Go pour l'orchestration | Pilotage des adaptations du système, avec validation séparée de chaque moteur réseau. |
| `platforms/linux`, `platforms/windows` | Adaptateurs Go en espace utilisateur | Appels système et intégrations à préciser par fonction. |
| `packages/protocol` | Contrats JSON versionnés, indépendants du langage | Encodage Go avec la bibliothèque standard ; contrats mobiles à valider avec Kotlin. |
| Intégration Android | Kotlin et outils Android natifs | Permissions, cycle de vie et services ; aucun projet Android créé à cette étape. |
| `apps/dashboard` | Interface web locale ; framework différé | Le choix du framework attend les premiers besoins d'interface. |
| `ml/` | Python envisagé ; bibliothèques différées | Recherche, entraînement hors ligne et évaluation ; export et inférence à déterminer après validation. |

JSON est le format des contrats réseau v2 implémentés aux étapes 3.3/3.4, distincts de l'export local de latence v1. Le transport TLS 1.3 mutuel utilise la bibliothèque standard ; voir [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md). Aucun service réseau permanent n'est fourni.

## Pourquoi Go pour le premier agent

Go compile en code natif et inclut son support d'exécution dans le programme. Cela convient à notre objectif de distribuer un exécutable de bureau sans demander l'installation d'une machine virtuelle dédiée. Les dépendances natives éventuelles devront néanmoins être vérifiées au packaging. Voir la [FAQ officielle Go](https://go.dev/doc/faq#runtime).

Pour ce projet, nous retenons Go comme compromis entre développement progressif, code commun Linux/Windows et outils intégrés de compilation, formatage et test. La [commande officielle `go`](https://pkg.go.dev/cmd/go) fournit ces outils. Ce choix ne démontre aucun gain de performance réseau.

Le premier agent utilise uniquement la bibliothèque standard et le noyau du projet. Une dépendance externe sera ajoutée lorsqu'une fonction concrète la justifiera.

| Autre option envisagée | Motif du choix pour Coopace |
| --- | --- |
| Rust | Reste une option pour un composant spécialisé. Nous privilégions Go pour limiter la complexité initiale du service applicatif. |
| Python | Convient aux scripts et aux futures expériences de recherche. Nous privilégions une chaîne Go pour le noyau et la distribution des agents de bureau. |

Ces appréciations concernent les besoins actuels du projet ; elles ne constituent pas un classement général des langages.

## Intégrations propres aux systèmes

### Linux et OpenWrt

Le premier développement et les premiers essais locaux se feront sous Linux. La cible Windows sera prévue dès le noyau commun ; une compilation Windows et des essais sur Windows resteront deux validations distinctes.

CAKE/SQM reste une intégration future du moteur Linux. Le packaging OpenWrt sera évalué sur une cible matérielle précise ; choisir Go ne suffit pas à garantir la compatibilité et le coût mémoire sur chaque routeur.

### Windows

Go concerne le programme en espace utilisateur. Le choix du langage ne fournit ni une passerelle fonctionnelle ni un équivalent de CAKE.

Les appels aux API Windows seront isolés dans l'adaptation Windows. Microsoft recommande d'utiliser les fonctions WFP existantes en espace utilisateur lorsqu'elles suffisent, et de réserver un pilote aux traitements qui l'exigent. Un éventuel pilote sera un composant séparé avec sa propre chaîne de développement. Voir les [considérations Microsoft pour les pilotes WFP](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/callout-driver-programming-considerations).

### Android

Kotlin est retenu pour la couche applicative native et l'accès aux services Android. Voir la [documentation Android pour Kotlin](https://developer.android.com/kotlin).

Le noyau Go ne sera pas supposé directement importable depuis Kotlin. Go Mobile propose des liaisons vers Java et des bibliothèques Android ; leur adéquation à nos modèles, au cycle de vie et au packaging devra être démontrée par un prototype. Voir la [documentation Go Mobile](https://go.dev/wiki/Mobile).

Le mécanisme de réutilisation du noyau sur Android reste ouvert jusqu'à cette validation. Le protocole versionné restera le contrat d'interopérabilité entre appareils. L'organisation des futurs points d'entrée Android et du projet Gradle sera définie pendant l'étape mobile.

## Organisation et versions des outils

Le code Go utilise un seul module, avec un `go.mod` à la racine du dépôt, en conservant les dossiers existants. Plusieurs répertoires métier ne nécessitent pas plusieurs modules Go. Le chemin `github.com/ayyoubecharkaouy/coopace` est aligné sur le dépôt distant. Voir le [guide officiel d'organisation d'un module](https://go.dev/doc/modules/layout).

À l'étape 2.2, Go 1.27.3 est retenu d'après le [catalogue officiel](https://go.dev/dl/?mode=json) et enregistré dans `.go-version` et `go.mod`. Cette version est installée localement et validée sous Linux x86_64 : formatage, tests, analyse statique et compilation du noyau réussissent. Les commandes sont décrites dans [DEVELOPMENT.md](DEVELOPMENT.md).

Le script `scripts/go.sh` utilise le SDK local sans modifier le `PATH` du terminal. Le script d'installation conserve les téléchargements interrompus pour permettre leur reprise. La [documentation d'installation Go](https://go.dev/doc/install) couvre également l'installation système sous Linux et Windows.

## Suite immédiate

Les étapes 2.2 à 3.4 livrent le socle, les mesures, les fondations d'identité et un premier échange authentifié Linux. Ed25519 et SHA-256 de la bibliothèque standard sont retenus pour l'identité ; TLS 1.3 mutuel est intégré à l'étape 3.4 et testé en mémoire ; la validation TCP réelle reste à confirmer. Le stockage persistant de clé est activé sous Linux seulement, car les permissions doivent être adaptées au système. La collecte des compteurs et le stockage protégé Windows restent à implémenter ; son exécution native reste à consigner selon [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md).

Le transport du prototype utilise TLS mutuel et son état local est stocké dans des fichiers privés Linux. Le stockage protégé sur les autres systèmes, le framework web, un éventuel tunnel et l'inférence ML restent à préciser aux étapes correspondantes.

L'étape 4.1 ajoute `coopace-gateway inspect`, une application Go séparée pour le diagnostic local Linux. Elle utilise la bibliothèque standard et les outils `ip`/`tc` présents pour des lectures bornées, sans nouvelle dépendance Go ni installation automatique. Son [périmètre](GATEWAY_DIAGNOSTIC.md) ne valide pas encore le moteur de passerelle ou la restauration.

Le périmètre du futur module ML est documenté dans [`ml/README.md`](../ml/README.md).
