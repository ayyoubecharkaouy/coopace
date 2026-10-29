# Préparation du développement Go

## État des étapes 2.2 à 4.2

L'étape 2.2 est validée sous Linux x86_64 avec Go 1.27.3, installé localement à partir de l'archive officielle vérifiée. Le module Go et les premiers modèles métier sont présents, avec leurs tests.

L'étape 2.3 ajoute le premier agent local. Les commandes de formatage, de test et d'analyse statique réussissent, ainsi que la compilation du binaire et son lancement sous Linux. À l'étape 2.4, la compilation et l'analyse statique pour Windows amd64 sont également validées. L'exécution native Windows reste à effectuer selon [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md) ; l'application Android sera développée ultérieurement.

L'étape 3.1 ajoute `coopace observe` et les premiers taux de trafic par interface sous Linux. Les [observations locales](OBSERVATIONS.md) décrivent les sources, les unités, les tests et la portée limitée de l'essai réel. La collecte des compteurs Windows reste non implémentée.

L'étape 3.2 ajoute `coopace latency`, les statistiques de durée TCP et un export JSON local v1. Les tests déterministes passent dans l'environnement isolé ; le test TCP réel en boucle locale a été exécuté avec succès depuis le terminal utilisateur sous Linux. Voir [LATENCY.md](LATENCY.md) pour reproduire le test, choisir une cible et établir une référence.

L'étape 3.3 ajoute l'identité persistante sous Linux, le consentement et des contrats JSON validés hors réseau. La [documentation d'identité et de groupe](IDENTITY_AND_GROUP.md) décrit ces fondations. Le stockage de clé privée Windows reste explicitement indisponible.

L'étape 3.4 ajoute l'approbation et le consentement persistés, les certificats publics et un échange TLS mutuel borné. Les tests TLS en mémoire passent ; le test TCP réel est ignoré dans l'environnement isolé et reste à confirmer depuis le terminal utilisateur. Voir [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md) pour les commandes et la portée du prototype Linux.

L'étape 4.1 ajoute l'application passerelle avec un diagnostic Linux en lecture seule : `coopace-gateway inspect`. Les tests et le lancement réel sont vérifiés, avec un inventaire partiel dans l'environnement isolé où Netlink est interdit. Le [diagnostic et ses limites](GATEWAY_DIAGNOSTIC.md) décrivent les lectures, les commandes bornées et les validations encore nécessaires sur le PC utilisateur. Ce programme ne gère pas encore le trafic.

La préparation de l’étape 4.2 ajoute `inspect --json`, l’export d’inventaire local v1 et les métadonnées incorporées à la compilation. Les tests vérifient les valeurs inconnues, les listes vides et la provenance manquante. Le [protocole de référence initiale](GATEWAY_BASELINE.md) prépare le scénario réel, qui reste à compléter et mesurer.

## Version et module

- SDK retenu : **Go 1.27.3**, enregistré dans `.go-version` et comme minimum dans `go.mod`.
- Module unique : `github.com/ayyoubecharkaouy/coopace`, correspondant au dépôt Git distant.
- Dépendances du noyau : bibliothèque standard uniquement. Aucun `go.sum` n'est nécessaire à ce stade.
- Les scripts et les commandes ci-dessous s'exécutent depuis la racine du dépôt.

La version et la somme de contrôle de l'archive Linux proviennent du [catalogue officiel Go](https://go.dev/dl/?mode=json). La [référence `go.mod`](https://go.dev/doc/modules/gomod-ref) explique le chemin du module et la version minimale.

## Installation locale sous Linux x86_64

Prérequis : `sh`, `curl`, `sha256sum`, `tar` et un accès HTTPS aux serveurs de téléchargement Go.

```sh
sh scripts/setup-go.sh
sh scripts/go.sh version
```

Le premier script télécharge l'archive officielle en HTTPS, vérifie son SHA-256 avant extraction et installe le SDK dans `.local/toolchains/go1.27.3/`. Il ne nécessite pas `sudo`, ne modifie pas le système et ne change pas le profil du terminal. Un échec de téléchargement ou de vérification interrompt l'installation.

`scripts/go.sh` utilise ce SDK local en priorité, puis une commande `go` déjà disponible dans le `PATH`. Il conserve les caches dans `.cache/` et `.local/`, exclus de Git. Le changement automatique de version est désactivé ; une installation système trop ancienne devra être mise à jour explicitement.

Le script d'installation prend actuellement en charge Linux x86_64 uniquement. Pour une autre architecture, utiliser la [distribution officielle adaptée](https://go.dev/doc/install).

### Connexion lente ou téléchargement interrompu

Le téléchargement n'a plus de limite totale de cinq minutes. Il s'interrompt si la connexion ne peut pas être établie en 30 secondes ou si le transfert reste sous un octet par seconde pendant deux minutes.

L'archive partielle est conservée dans `.cache/downloads/`. Après une coupure ou une interruption, relancer simplement :

```sh
sh scripts/setup-go.sh
```

Le script demande la reprise au dernier octet reçu avec `curl --continue-at -`. Une archive déjà complète et vérifiée est réutilisée sans téléchargement. Voir la [documentation officielle curl](https://curl.se/docs/manpage.html#-C).

La première version du script supprimait le fichier temporaire après un échec : les données reçues avec cette ancienne version ne peuvent donc pas être reprises. Les nouvelles tentatives conserveront leur progression.

Si le serveur refuse la reprise ou si la somme de contrôle est incorrecte, supprimer uniquement l'archive du cache puis relancer le script pour un téléchargement complet :

```sh
rm -f .cache/downloads/go1.27.3.linux-amd64.tar.gz
sh scripts/setup-go.sh
```

## Lancer le premier agent

Depuis la racine du dépôt, sous Linux :

```sh
sh scripts/go.sh run ./apps/agent/cmd/coopace status
sh scripts/go.sh run ./apps/agent/cmd/coopace observe
sh scripts/go.sh run ./apps/agent/cmd/coopace --help
sh scripts/go.sh run ./apps/agent/cmd/coopace latency --help
sh scripts/go.sh run ./apps/agent/cmd/coopace identity --help
sh scripts/go.sh run ./apps/agent/cmd/coopace group --help
```

Exemple de résultat sous Linux x86_64 :

```text
Coopace dev
Système : linux
Architecture : amd64
Rôle : agent
État : local (hors groupe)
```

`dev` est la version de développement de Coopace, distincte de la version du SDK Go. Le système et l'architecture correspondent à la plateforme de l'exécutable. Ce statut décrit cette exécution locale ; il ne recherche pas un service en arrière-plan, ne crée pas d'identité persistante et ne teste pas l'accès Internet.

Pour compiler un binaire réutilisable :

```sh
mkdir -p .local/bin
sh scripts/go.sh build -o .local/bin/coopace ./apps/agent/cmd/coopace
./.local/bin/coopace status
```

Le binaire est placé dans un dossier exclu de Git. Ses codes de sortie sont `0` pour une réussite, `1` pour une erreur d'exécution ou d'affichage et `2` pour des arguments invalides. Sans argument, il affiche l'aide. `go run` peut présenter une erreur du programme avec son propre code de sortie ; utiliser le binaire pour vérifier les codes exacts.

## Vérifications du noyau et de l'agent

Une fois Go disponible :

```sh
sh scripts/go.sh fmt ./...
sh scripts/go.sh test ./...
sh scripts/go.sh vet ./...
sh scripts/go.sh build ./...
git diff --check
```

Les tests vérifient les descriptions valides Linux, Windows et Android, les rôles combinés, les identifiants et noms Unicode, le rejet des encodages UTF-8 invalides et des données incohérentes, ainsi que l'absence de modification des données par la validation. La présence d'une description Android dans un test ne valide pas une application Android.

Les tests de l'agent vérifient la détection des plateformes ciblées, l'affichage du statut, l'aide, les arguments invalides, la collecte des compteurs sur des données contrôlées et les erreurs de lecture ou d'affichage. Les tests du noyau vérifient aussi les taux, grands compteurs, interfaces apparues/disparues et compteurs en baisse. `go build ./...` vérifie les paquets ; la commande avec `-o` ci-dessus produit le binaire utilisateur. Les tests s'exécutent localement, sans accès au routeur et sans modifier la configuration réseau.

Les tests de latence couvrent les percentiles, valeurs absentes, unités de l'export, options invalides et annulation. Le test d'intégration ouvre uniquement une connexion en boucle locale, sans données applicatives ; il est explicitement ignoré si l'environnement interdit les sockets. Utiliser `-count=1` pour le relancer hors de l'environnement isolé sans réutiliser un résultat de test en cache.

Les tests d'identité utilisent des dossiers temporaires privés. Ils vérifient stabilité, permissions et refus des clés corrompues ou liées par un lien symbolique. Les tests de protocole vérifient les limites, ambiguïtés JSON, identités/groupes attendus et séquences. Pour relancer des essais aléatoires bornés du décodeur, sans connexion réseau :

```sh
sh scripts/go.sh test -parallel=2 -fuzz=FuzzDecode -fuzztime=2s ./packages/protocol
```

Les tests du groupe vérifient de vraies négociations TLS sur `net.Pipe`, les consentements indépendants, les refus d'identité/groupe et la révocation. `TestGroupLoopbackExchange` vérifie aussi le chemin TCP lorsqu'il est autorisé :

```sh
sh scripts/go.sh test -count=1 -v -run '^TestGroupLoopbackExchange$' ./apps/agent/internal/group
```

Les tests de régression du script d'installation fonctionnent sans Go et sans réseau, avec Python 3 et de petites archives de test :

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

Ils vérifient la conservation et la reprise d'un téléchargement interrompu, la réutilisation d'une archive vérifiée et le refus d'une archive corrompue. Ils ne valident pas le téléchargement réel du SDK ni le noyau Go.

La même commande Python inclut les tests de `scripts/lab-network.sh`. Ils copient le script dans des dossiers temporaires et remplacent les outils réseau et contrôles de privilèges par des exécutables simulés. Ils couvrent le ciblage des espaces propres, les erreurs, l'interruption et le nettoyage, sans ressource réseau réelle. Ces tests sont réservés à Linux.

Le [laboratoire virtuel](VIRTUAL_LAB.md) se prévisualise avec `sh scripts/lab-network.sh plan`, sans privilèges. Son mode `run` crée et configure explicitement des ressources temporaires et demande des capacités système ; il est distinct des commandes de diagnostic en lecture seule. L'exécution native reste à consigner et ne fait pas partie des tests automatiques ordinaires.

## Sous Windows

Un exécutable Windows x64 est disponible dans `.local/bin/coopace-windows-amd64.exe`, accompagné de son empreinte SHA-256. La [procédure Windows](WINDOWS_VALIDATION.md) explique comment le compiler depuis Linux et le tester sur un PC Windows sans installer Go.

Pour développer et lancer les tests depuis les sources sur Windows :

Installer Go 1.27.3 ou une version compatible plus récente depuis la [documentation officielle](https://go.dev/doc/install), puis ouvrir un terminal PowerShell à la racine du dépôt :

```powershell
go version
go fmt ./...
go test ./...
go vet ./...
go build ./...
go run ./apps/agent/cmd/coopace status
```

Ces commandes utilisent les emplacements de cache par défaut de l'installation Windows. Les scripts `.sh` ne sont pas nécessaires sur cette plateforme.

Une validation réelle sous Windows devra être consignée séparément. Elle ne peut pas être déduite d'une compilation croisée depuis Linux.

## Lancer le diagnostic de passerelle

L'agent et la passerelle sont deux applications du même module. Depuis le dépôt Linux, sans élévation :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
sh scripts/go.sh build -o .local/bin/coopace-gateway ./apps/gateway/cmd/coopace-gateway
./.local/bin/coopace-gateway --help
```

Les outils `ip` et `tc`, lorsqu'ils sont présents, sont utilisés uniquement pour des requêtes locales d'affichage. Leur absence, un refus Netlink ou une sortie invalide apparaît dans la rubrique concernée. Les tests des parseurs ne nécessitent pas ces outils ; un binaire de test local vérifie les limites de sortie et l'annulation d'un processus.

Le binaire Windows de diagnostic compile aussi mais sa collecte est explicitement indisponible ; voir [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md). Les mesures sous charge, le chemin réel des appareils et la restauration restent à définir avant une intervention.

## Organisation du code actuel

Les fichiers de `packages/core` décrivent l'appareil, le système, les rôles et les capacités. Leurs règles et limites sont précisées dans le [README du noyau](../packages/core/README.md). Les messages JSON sont dans `packages/protocol`, l'authentification et l'approbation dans l'agent ; la découverte reste à développer.

Le point d'entrée de l'agent se trouve dans `apps/agent/cmd/coopace`, avec les commandes dans `apps/agent/internal/cli` et l'état local dans `apps/agent/internal/status`. Voir le [README de l'agent](../apps/agent/README.md).

La collecte des compteurs est orchestrée dans `apps/agent/internal/observe`, avec une source Linux dans `platforms/linux` et des calculs indépendants du système dans `packages/core/traffic.go`. Sous Windows, cette commande renvoie une erreur d'indisponibilité ; voir [OBSERVATIONS.md](OBSERVATIONS.md).

La mesure TCP et l'export local sont dans `apps/agent/internal/latency`, avec les statistiques pures dans `packages/core/latency.go`. La commande impose une cible explicite et ne dépend pas d'un outil `ping` externe.

La comparaison des exports locaux est dans les fichiers `latency/read.go` et `latency/compare.go`, avec une commande dédiée dans `cli/latency_compare.go`. Le contrôle syntaxique JSON commun est dans `internal/strictjson` ; les schémas de rapport et de protocole restent séparés. Voir [LATENCY.md](LATENCY.md#comparer-les-rapports-au-repos-et-sous-charge) pour la comparaison sans connexion.

L'état d'identité est géré par `apps/agent/internal/identity` ; son stockage est activé sous Linux uniquement. `packages/protocol` n'ouvre aucune connexion. `apps/agent/internal/group` convertit les contrats vers le noyau et orchestre profil, consentement persisté, transport TLS et échange borné. Le cadrage et la validation restent dans `packages/protocol`, sans sockets ni stockage.

Le point d'entrée passerelle est `apps/gateway/cmd/coopace-gateway`, avec CLI et orchestration dans ses propres paquets `internal`. Les types d'inventaire sont dans `packages/core/gateway.go` ; les lectures Linux et leurs parseurs sont dans `platforms/linux/gateway*.go`. Cette séparation ne dépend pas des paquets internes de l'agent.
