# Préparation du développement Go

## État des étapes 2.2 à 4.2

L'étape 2.2 est validée sous Linux x86_64 avec Go 1.27.3, installé localement à partir de l'archive officielle vérifiée. Le module Go et les premiers modèles métier sont présents, avec leurs tests.

L'étape 2.3 ajoute le premier agent local. Les commandes de formatage, de test et d'analyse statique réussissent, ainsi que la compilation du binaire et son lancement sous Linux. À l'étape 2.4, la compilation et l'analyse statique pour Windows amd64 sont également validées. L'exécution native Windows reste à effectuer selon [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md) ; l'application Android sera développée ultérieurement.

L'étape 3.1 ajoute `coopace observe` et les premiers taux de trafic par interface sous Linux. Les [observations locales](OBSERVATIONS.md) décrivent les sources, les unités, les tests et la portée limitée de l'essai réel. La collecte des compteurs Windows reste non implémentée.

L'étape 3.2 ajoute `coopace latency`, les statistiques de durée TCP et un export JSON local v1. Les tests déterministes passent dans l'environnement isolé ; le test TCP réel en boucle locale a été exécuté avec succès depuis le terminal utilisateur sous Linux. Voir [LATENCY.md](LATENCY.md) pour reproduire le test, choisir une cible et établir une référence.

L'étape 3.3 ajoute l'identité persistante sous Linux, le consentement et des contrats JSON validés hors réseau. La [documentation d'identité et de groupe](IDENTITY_AND_GROUP.md) décrit ces fondations. Le stockage de clé privée Windows reste explicitement indisponible.

L'étape 3.4 ajoute l'approbation et le consentement persistés, les certificats publics et un échange TLS mutuel borné. Les tests TLS en mémoire passent ; le test TCP réel est ignoré dans l'environnement isolé et reste à confirmer depuis le terminal utilisateur. Voir [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md) pour les commandes et la portée du prototype Linux.

L'étape 4.1 ajoute l'application passerelle avec un diagnostic Linux en lecture seule : `coopace-gateway inspect`. Les tests et le lancement réel sont vérifiés, avec un inventaire partiel dans l'environnement isolé où Netlink est interdit, puis un [inventaire complet dans la passerelle virtuelle](VALIDATION_VIRTUAL_LAB_2026-10-29.md). Le [diagnostic et ses limites](GATEWAY_DIAGNOSTIC.md) distinguent cet essai de l'inventaire du foyer encore à recueillir. Ce programme ne gère pas encore le trafic.

L'étape 4.2 ajoute `inspect --json`, l'export d'inventaire local v1 et les métadonnées de compilation, puis les outils de laboratoire décrits ci-dessous. Leurs premiers essais natifs de connectivité, transfert, séries et supervision sont consignés. Le [protocole de référence initiale](GATEWAY_BASELINE.md) reste à compléter pour une passerelle du foyer ; le goulot virtuel, sa collecte et le moteur de files restent à développer.

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

La suite Python de développement se lance sans Go, sans privilèges et sans réseau :

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

Elle regroupe les tests de l'installation et des pilotes de laboratoire. Les tests du script d'installation utilisent de petites archives pour vérifier la reprise d'un téléchargement interrompu, la réutilisation d'une archive vérifiée et le refus d'une archive corrompue. Ils ne valident pas le téléchargement réel du SDK ni le noyau Go.

La même commande Python inclut les tests de `scripts/lab-network.sh`. Ils copient le script dans des dossiers temporaires et remplacent les outils réseau et contrôles de privilèges par des exécutables simulés. Ils couvrent le ciblage des espaces propres, les erreurs, l'interruption et le nettoyage, sans ressource réseau réelle. Ces tests sont réservés à Linux.

Le [laboratoire virtuel](VIRTUAL_LAB.md) se prévisualise avec `sh scripts/lab-network.sh plan`, sans privilèges. Ses modes `run` et `run-tcp` créent et configurent explicitement des ressources temporaires et demandent des capacités système ; ils sont distincts des commandes de diagnostic en lecture seule. `run-tcp` réutilise la CLI de l'agent et la cible bornée de `scripts/lab-tcp`, dont les tests font partie de `go test ./...`. Son test TCP en boucle locale est ignoré si les sockets sont interdites. Les tests Python vérifient aussi l'arrêt du processus serveur avant la suppression de son espace réseau. Le [premier essai natif ICMP/TCP](VALIDATION_VIRTUAL_LAB_2026-10-29.md) est consigné ; l'exécution privilégiée du laboratoire reste distincte des tests automatiques ordinaires.

Le mode [`run-load`](VIRTUAL_LOAD.md) demande les mêmes privilèges et le binaire `coopace-lab-load`, construit avec `sh scripts/go.sh build -o .local/bin/coopace-lab-load ./scripts/lab-load`. Ses tests Go utilisent des connexions en mémoire et font partie de la suite générale ; le test de transfert en boucle locale est ignoré si les sockets sont interdites. La suite Python couvre aussi l'échec de réception et l'arrêt de ce récepteur avant suppression. Les [premières observations natives](VALIDATION_VIRTUAL_LOAD_2026-10-29.md) de ce flux sont consignées, avec le code de sortie exact `0` conservé.

Le mode [`run-series`](VIRTUAL_SERIES.md) réalise la collecte simultanée et répétée avec Python 3 pour son pilote de laboratoire. Recompiler les trois binaires `coopace`, `coopace-lab-tcp` et `coopace-lab-load` avant l'essai, selon le protocole. La suite Python vérifie l'ordre, la conservation des échecs, le recouvrement temporel et les processus locaux sans réseau. Un [premier essai natif](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) est consigné, avec 60 connexions réussies sans échec et les trois recouvrements vérifiés. Le JSON groupé contient les six exports de latence et trois rapports de charge ; il n'est pas une entrée directe de `latency compare`.

Le [protocole de goulot virtuel](VIRTUAL_BOTTLENECK.md) prépare l'expérience suivante, avec une file TBF/FIFO à 4 Mbit/s et des critères fixés avant collecte. Ce document n'est pas une configuration exécutable. Les futurs délais allongés ne doivent pas modifier les paramètres des modes existants ; le nettoyage indépendant et les tests du cycle de vie de la file précèdent cette nouvelle collecte.

Le [superviseur indépendant](LAB_GUARD.md) dispose maintenant de contrôles `check` et `check-crash`, sans file ni trafic. Les tests Python lancent et récupèrent de vrais processus avec des espaces simulés. `python3 -I scripts/lab-guard.py plan` reste sans privilèges ; les [deux premiers contrôles natifs](VALIDATION_LAB_GUARD_2026-10-29.md) sont validés séparément de la suite automatique.

Le [cycle de vie d'une file TBF](LAB_QUEUE.md) ajoute `python3 -I scripts/lab-guard.py plan-queue`, également sans privilèges. `check-queue` et `check-queue-crash` exigent en plus `tc`, créent une file dans la passerelle neuve sur un lien désactivé, puis nettoient. Ils utilisent le module voisin `lab_queue.py` ; leurs [premiers contrôles natifs](VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés avec ceux sans file sur la même révision. Les commandes `lab-network.sh` gardent leurs paramètres et leur cycle de vie.

L'[instrumentation du goulot](LAB_INSTRUMENTATION.md) ajoute `coopace-lab-load receive --json` et les modes `check-queue-stats` / `check-queue-stats-crash`. Le test Go `TestLoopbackSyntheticTransfer` vérifie désormais aussi la sortie JSON de réception et doit passer sans SKIP pour sa validation native. Les tests Python couvrent les compteurs et jauges ; la [première validation native](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) confirme le test TCP local sans SKIP et les deux contrôles avec `tc` réel sur liens désactivés. La collecte périodique et la campagne avec goulot actif restent à développer.

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

Le binaire Windows de diagnostic compile aussi mais sa collecte est explicitement indisponible ; voir [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md). Les références WAN sous charge, le chemin réel des appareils du foyer et la restauration de leur passerelle restent à définir avant une intervention sur ce réseau.

## Organisation du code actuel

Les fichiers de `packages/core` décrivent l'appareil, le système, les rôles et les capacités. Leurs règles et limites sont précisées dans le [README du noyau](../packages/core/README.md). Les messages JSON sont dans `packages/protocol`, l'authentification et l'approbation dans l'agent ; la découverte reste à développer.

Le point d'entrée de l'agent se trouve dans `apps/agent/cmd/coopace`, avec les commandes dans `apps/agent/internal/cli` et l'état local dans `apps/agent/internal/status`. Voir le [README de l'agent](../apps/agent/README.md).

La collecte des compteurs est orchestrée dans `apps/agent/internal/observe`, avec une source Linux dans `platforms/linux` et des calculs indépendants du système dans `packages/core/traffic.go`. Sous Windows, cette commande renvoie une erreur d'indisponibilité ; voir [OBSERVATIONS.md](OBSERVATIONS.md).

La mesure TCP et l'export local sont dans `apps/agent/internal/latency`, avec les statistiques pures dans `packages/core/latency.go`. La commande impose une cible explicite et ne dépend pas d'un outil `ping` externe.

La comparaison des exports locaux est dans les fichiers `latency/read.go` et `latency/compare.go`, avec une commande dédiée dans `cli/latency_compare.go`. Le contrôle syntaxique JSON commun est dans `internal/strictjson` ; les schémas de rapport et de protocole restent séparés. Voir [LATENCY.md](LATENCY.md#comparer-les-rapports-au-repos-et-sous-charge) pour la comparaison sans connexion.

L'état d'identité est géré par `apps/agent/internal/identity` ; son stockage est activé sous Linux uniquement. `packages/protocol` n'ouvre aucune connexion. `apps/agent/internal/group` convertit les contrats vers le noyau et orchestre profil, consentement persisté, transport TLS et échange borné. Le cadrage et la validation restent dans `packages/protocol`, sans sockets ni stockage.

Le point d'entrée passerelle est `apps/gateway/cmd/coopace-gateway`, avec CLI et orchestration dans ses propres paquets `internal`. Les types d'inventaire sont dans `packages/core/gateway.go` ; les lectures Linux et leurs parseurs sont dans `platforms/linux/gateway*.go`. Cette séparation ne dépend pas des paquets internes de l'agent.

## Simuler la planification CAKE

La [commande de simulation](GATEWAY_PLANNING.md) lit un scénario local explicite, sans inventaire ni privilège :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway plan --scenario docs/examples/cake-plan-propose.json
```

Les exemples sont fictifs ; les hypothèses restent déclarées et aucune configuration réseau n’est appliquée. Le scénario strict et le rapport appartiennent à `apps/gateway/internal/planning`, la règle au noyau et la provenance du binaire à `internal/buildinfo`.
