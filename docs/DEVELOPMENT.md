# Préparation du développement Go

## État de l'étape 2.2

L'étape 2.2 est validée sous Linux x86_64 avec Go 1.27.3, installé localement à partir de l'archive officielle vérifiée. Le module Go et les premiers modèles métier sont présents, avec leurs tests.

Les commandes `go fmt ./...`, `go test ./...`, `go vet ./...` et `go build ./...`, exécutées via `scripts/go.sh`, réussissent. Aucun programme agent n'est encore disponible ; `coopace status` appartient à l'étape 2.3. L'exécution native sous Windows et Android reste à vérifier.

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

## Vérifications du noyau

Une fois Go disponible :

```sh
sh scripts/go.sh fmt ./...
sh scripts/go.sh test ./...
sh scripts/go.sh vet ./...
sh scripts/go.sh build ./...
git diff --check
```

Les tests vérifient les descriptions valides Linux, Windows et Android, les rôles combinés, le rejet des données incohérentes et l'absence de modification des données par la validation. La présence d'une description Android dans un test ne valide pas une application Android.

`go build ./...` vérifie actuellement une bibliothèque ; il ne produit pas d'application utilisateur. Les tests s'exécutent localement, sans accès au routeur et sans modifier le réseau.

Les tests de régression du script d'installation fonctionnent sans Go et sans réseau, avec Python 3 et de petites archives de test :

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

Ils vérifient la conservation et la reprise d'un téléchargement interrompu, la réutilisation d'une archive vérifiée et le refus d'une archive corrompue. Ils ne valident pas le téléchargement réel du SDK ni le noyau Go.

## Sous Windows

Installer Go 1.27.3 ou une version compatible plus récente depuis la [documentation officielle](https://go.dev/doc/install), puis ouvrir un terminal PowerShell à la racine du dépôt :

```powershell
go version
go fmt ./...
go test ./...
go vet ./...
go build ./...
```

Ces commandes utilisent les emplacements de cache par défaut de l'installation Windows. Les scripts `.sh` ne sont pas nécessaires sur cette plateforme.

Une validation réelle sous Windows devra être consignée séparément. Elle ne peut pas être déduite d'une compilation croisée depuis Linux.

## Organisation du code actuel

Les fichiers de `packages/core` décrivent l'appareil, le système, les rôles et les capacités. Leurs règles et limites sont précisées dans le [README du noyau](../packages/core/README.md). Les messages JSON, la découverte et l'authentification seront développés dans les étapes suivantes.
