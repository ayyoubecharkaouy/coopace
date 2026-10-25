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

État actuel : **non effectué**.

Pour chaque PC testé, noter la version de Windows, l'architecture, l'empreinte du binaire et les résultats des commandes avec leurs codes de sortie. Si le SDK Go et les sources sont disponibles sur ce PC, `go test ./...` et `go vet ./...` peuvent compléter ce contrôle ; leur résultat doit être distingué du simple lancement de l'exécutable.

Mettre ensuite à jour cette section, l'[état produit](PRODUCT.md) et la [feuille de route](ROADMAP.md). Les instructions générales sont dans [DEVELOPMENT.md](DEVELOPMENT.md).
