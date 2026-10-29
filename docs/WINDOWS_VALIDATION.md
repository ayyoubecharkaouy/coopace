# Validation du premier agent Windows

## État de l'étape 2.4

La compilation croisée et l'analyse statique pour **Windows amd64** réussissent avec Go 1.27.3 depuis Linux x86_64. Le fichier produit est un exécutable console PE32+ x86-64 ; ses métadonnées confirment `GOOS=windows`, `GOARCH=amd64` et `CGO_ENABLED=0`.

Le lancement Linux de `coopace status` est également vérifié. L'exécutable Windows n'a pas encore été lancé sur un PC Windows : la validation native ci-dessous reste à effectuer avant de déclarer cette cible testée à l'exécution.

Ce résultat concerne uniquement l'agent local. Il ne valide pas une passerelle, un service Windows, le routage ou la gestion des files.

## Reproduire la compilation depuis Linux

Depuis la racine du dépôt :

```sh
mkdir -p .local/bin
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 sh scripts/go.sh build -trimpath -o .local/bin/coopace-windows-amd64.exe ./apps/agent/cmd/coopace
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 sh scripts/go.sh vet ./...
sh scripts/go.sh version -m .local/bin/coopace-windows-amd64.exe
sha256sum .local/bin/coopace-windows-amd64.exe > .local/bin/coopace-windows-amd64.exe.sha256
```

Le fichier `.sha256` correspond au binaire de cette compilation et doit être régénéré après chaque nouvelle compilation. Les artefacts restent dans `.local/`, exclu de Git. Il s'agit d'une version de développement, pas d'un installateur publié.

## Tester sur un PC Windows x64

Copier `coopace-windows-amd64.exe` et son fichier `.sha256` sur le PC Windows, puis ouvrir PowerShell dans leur dossier. Go n'est pas nécessaire pour lancer cet exécutable.

Vérifier que l'empreinte affichée correspond à celle du fichier `.sha256` :

```powershell
Get-FileHash .\coopace-windows-amd64.exe -Algorithm SHA256
Get-Content .\coopace-windows-amd64.exe.sha256
```

Lancer le statut puis consulter immédiatement son code de sortie :

```powershell
.\coopace-windows-amd64.exe status
$LASTEXITCODE
```

Résultat attendu :

```text
Coopace dev
Système : windows
Architecture : amd64
Rôle : agent
État : local (hors groupe)
```

Le code attendu est `0`. Vérifier aussi la lisibilité des accents et la fin normale du programme après l'affichage.

Tester l'aide :

```powershell
.\coopace-windows-amd64.exe --help
$LASTEXITCODE
```

Le programme doit afficher l'aide et retourner `0`. Sans argument, il doit également afficher l'aide et retourner `0`.

Tester les arguments invalides :

```powershell
.\coopace-windows-amd64.exe inconnue
$LASTEXITCODE
.\coopace-windows-amd64.exe status extra
$LASTEXITCODE
```

Chaque commande doit afficher une erreur et retourner `2`.

Depuis l'étape 3.1, la commande d'observation est réservée à Linux. Avec le binaire reconstruit à cette étape, vérifier également :

```powershell
.\coopace-windows-amd64.exe observe
$LASTEXITCODE
```

Le résultat attendu est un message indiquant que l'observation du trafic n'est pas disponible sur Windows et le code `1`, sans mesures de remplacement. Ce comportement reste à confirmer sur Windows ; sa compilation est vérifiée depuis Linux.

## Consigner le résultat natif

Depuis l'étape 3.3, `identity --help` est disponible dans le binaire Windows, mais `identity init/show/export-cert --state-dir DOSSIER` doit retourner une erreur d'indisponibilité avant toute création de clé. Le stockage protégé natif n'est pas implémenté : les modes de fichier Linux ne sont pas considérés comme une protection des ACL Windows. Les contrats v2 et le moteur TLS compilent. Les opérations `group configure/show/revoke/listen/exchange` restent indisponibles sur Windows faute de stockage d'identité protégé ; leur exécution Linux ne valide pas cette cible. `group --help` reste accessible.

Depuis l'étape 3.2, le binaire comprend aussi `latency`. L'aide ne nécessite aucune connexion :

```powershell
.\coopace-windows-amd64.exe latency --help
$LASTEXITCODE
```

Le code attendu est `0`. Le lancement sans cible (`latency` seul) doit retourner `2` et ne provoquer aucun essai réseau. Pour tester une véritable connexion, choisir ensuite une IP:port de service TCP accessible et suivre [LATENCY.md](LATENCY.md). Cette mesure est compilée pour Windows mais reste non validée à l'exécution sur cette plateforme.

État actuel : **non effectué**.

La comparaison `latency compare --idle FICHIER --loaded FICHIER` compile également pour Windows et utilise seulement des fichiers locaux. Ses tests sont exécutés sous Linux ; son lancement natif Windows reste à vérifier. Elle ne dépend ni du stockage d'identité ni du diagnostic Linux.

Pour chaque PC testé, noter la version de Windows, l'architecture, l'empreinte du binaire et les résultats des commandes avec leurs codes de sortie. Si le SDK Go et les sources sont disponibles sur ce PC, `go test ./...` et `go vet ./...` peuvent compléter ce contrôle ; leur résultat doit être distingué du simple lancement de l'exécutable.

Mettre ensuite à jour cette section, l'[état produit](PRODUCT.md) et la [feuille de route](ROADMAP.md). Les instructions générales sont dans [DEVELOPMENT.md](DEVELOPMENT.md).

## Diagnostic de passerelle de l'étape 4.1

Une commande distincte existe sous Linux : `coopace-gateway inspect`. Sa compilation Windows amd64 et son analyse statique réussissent, mais son adaptateur de collecte Windows n'est pas implémenté. Cela ne valide pas une passerelle Windows.

Depuis Linux :

```sh
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 sh scripts/go.sh build -trimpath -o .local/bin/coopace-gateway-windows-amd64.exe ./apps/gateway/cmd/coopace-gateway
sha256sum .local/bin/coopace-gateway-windows-amd64.exe > .local/bin/coopace-gateway-windows-amd64.exe.sha256
```

Sur Windows, après contrôle de l'empreinte :

```powershell
.\coopace-gateway-windows-amd64.exe --help
$LASTEXITCODE
.\coopace-gateway-windows-amd64.exe inspect
$LASTEXITCODE
```

L'aide doit retourner `0` ; `inspect` doit indiquer l'indisponibilité et retourner `1`, sans faux inventaire vide. Cet essai natif reste à consigner séparément de la compilation. L’option `inspect --json` compile aussi ; elle conserve le refus de collecte Windows avec le code `1`, sans inventaire JSON de remplacement.
