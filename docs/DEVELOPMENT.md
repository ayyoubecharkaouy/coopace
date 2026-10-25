# Préparation du développement Go

## État de l'étape 2.2

Le module Go et les premiers modèles métier sont présents, avec leurs tests. L'installation du SDK et l'exécution des vérifications restent à valider : l'environnement de travail ne dispose pas de Go et ne peut pas résoudre `go.dev` pour télécharger l'archive.

La syntaxe des scripts shell et les différences Git ont été vérifiées. Cela ne remplace pas une compilation ni une exécution des tests Go. Aucun programme agent n'est encore disponible ; `coopace status` appartient à l'étape 2.3.

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
