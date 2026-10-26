# Premier échange authentifié — étape 3.4

## Périmètre et validation

Le prototype Linux permet à deux instances de s'approuver mutuellement et d'effectuer **un échange TLS 1.3**, puis de se déconnecter. Chaque instance possède sa propre identité, son certificat et son consentement. Un dossier d'état conserve un seul groupe et un seul pair approuvé ; `configure` remplace explicitement cette configuration.

L'authentification mutuelle et les échanges JSON passent les tests avec de vraies négociations TLS sur des connexions en mémoire. Les quatre combinaisons de consentement au partage sont vérifiées, ainsi que les refus et la révocation. Le test TCP en boucle locale est présent mais ignoré lorsque les sockets sont interdites ; sa validation depuis le terminal Linux utilisateur reste à consigner. Aucune validation LAN, Windows native ou Android n'est revendiquée.

Il n'y a pas encore de découverte automatique, de service permanent, de groupe à plusieurs pairs, de relais ou de gestion des files réseau. Le processus en écoute n'est pas un chef du groupe. Cet échange ne démontre aucun gain de débit ou de latence.

## Essai sur un seul PC Linux

Exécuter les commandes depuis la racine de `coopace`. Deux dossiers simulent deux appareils sans partager de clé privée.

### Préparer les deux identités

```sh
mkdir -p .local/bin .local/group-demo
sh scripts/go.sh build -o .local/bin/coopace ./apps/agent/cmd/coopace
./.local/bin/coopace identity init --state-dir .local/group-demo/a
./.local/bin/coopace identity init --state-dir .local/group-demo/b
./.local/bin/coopace identity export-cert --state-dir .local/group-demo/a > .local/group-demo/a.crt
./.local/bin/coopace identity export-cert --state-dir .local/group-demo/b > .local/group-demo/b.crt
```

`export-cert` écrit uniquement le certificat **public**. Il crée `identity.crt` une fois à partir de la clé existante ; aucune clé n'est créée implicitement et aucun certificat invalide ou expiré n'est remplacé automatiquement. Ne jamais transmettre `identity.key`.

### Approuver les pairs et consentir

Pour cet essai sur un même PC, extraire les empreintes des deux identités locales que l'on vient de créer :

```sh
A_ID="$(./.local/bin/coopace identity show --state-dir .local/group-demo/a | sed -n 's/^Identifiant : //p')"
B_ID="$(./.local/bin/coopace identity show --state-dir .local/group-demo/b | sed -n 's/^Identifiant : //p')"
./.local/bin/coopace group configure --state-dir .local/group-demo/a --group-id essai-local --peer-cert .local/group-demo/b.crt --peer-id "$B_ID" --name appareil-A --join
./.local/bin/coopace group configure --state-dir .local/group-demo/b --group-id essai-local --peer-cert .local/group-demo/a.crt --peer-id "$A_ID" --name appareil-B --join
./.local/bin/coopace group show --state-dir .local/group-demo/a
```

Avec deux appareils réels, échanger seulement les certificats publics et **vérifier les empreintes par un canal indépendant** avant `configure`. Le même nom de groupe ou la présence sur le même Wi-Fi n'accorde aucune confiance. Le certificat importé doit correspondre exactement à l'empreinte attendue. `--join` est obligatoire ; le partage d'observations reste faux sans `--share-observations`. Les choix de partage des deux pairs sont indépendants.

### Effectuer un échange

Dans un premier terminal, depuis le dépôt :

```sh
./.local/bin/coopace group listen --state-dir .local/group-demo/b --listen 127.0.0.1:8766
```

Dès que la ligne `Écoute` apparaît, lancer dans un second terminal, depuis le même dépôt :

```sh
./.local/bin/coopace group exchange --state-dir .local/group-demo/a --target 127.0.0.1:8766
```

Les deux sorties indiquent le pair authentifié, aucune observation envoyée ou reçue, puis la déconnexion. Chaque commande est limitée à 30 secondes, attente comprise ; Ctrl+C annule avec le code 130. Relancer `listen` avant un nouvel échange. Une connexion invalide termine aussi cette écoute unique.

Pour tester le partage, relancer la configuration de A et/ou B avec les mêmes paramètres et `--share-observations`, puis répéter l'écoute et l'échange. Chaque pair autorisé prélève et envoie une observation locale d'environ une seconde. Une adhésion seule ne déclenche aucune collecte. Le nom déclaré est transmis même lorsque les observations sont désactivées.

Le destinataire affiche les différences d'octets par interface, la source, la portée et la fenêtre mesurée. Les valeurs indisponibles restent indisponibles. Ces compteurs incluent potentiellement LAN, boucle locale et trafic de l'échange ; ils ne mesurent ni la capacité Internet ni une congestion. La mesure et l'horloge restent des déclarations du pair authentifié. Les observations reçues ne sont pas enregistrées automatiquement sur disque ; une redirection de la sortie les conserve explicitement.

L'écoute est locale par défaut. Un essai LAN demandera une adresse d'écoute explicite et l'adresse IP numérique réelle du pair ; IPv6 exige des crochets (`[adresse]:port`). Il ne faut pas confondre cet essai avec une validation du routage ou d'un moteur de passerelle.

### Retirer le consentement

```sh
./.local/bin/coopace group revoke --state-dir .local/group-demo/b
./.local/bin/coopace group show --state-dir .local/group-demo/b
```

La révocation persistée désactive adhésion et partage pour B ; ses nouveaux échanges sont refusés. Les opérations actives de B vérifient le fichier avant les messages et le surveillent avec un intervalle de 100 ms, auquel s'ajoutent les délais d'ordonnancement et d'I/O. La détection d'un changement, d'une suppression ou d'un fichier devenu invalide annule la connexion, y compris pendant l'attente ou TLS. Les octets déjà transmis ne peuvent pas être rappelés. Un changement de configuration interrompt l'échange en cours ; il faut ensuite en démarrer un nouveau. Chaque appareil gère son propre consentement.

## Stockage et transport

- `identity.key` : clé privée PKCS#8, dossier Linux privé `0700`, fichier `0600` ; reste locale.
- `identity.crt` : certificat public autosigné Ed25519, valable un an, usages serveur et client. La rotation et le renouvellement explicites restent à développer.
- `group.json` : configuration locale v1, liée à l'identité, au groupe et au certificat exact du pair ; fichier privé `0600`, remplacement atomique. Aucun relais n'est autorisé. Le format local n'est pas le protocole réseau.

Les certificats approuvés sont les seules ancres de confiance. La vérification standard de [crypto/tls](https://pkg.go.dev/crypto/tls#Config) reste activée, avec certificat client obligatoire, validité/usages contrôlés, nom lié à l'empreinte et comparaison supplémentaire du certificat et de la clé attendus. Aucun recours à `InsecureSkipVerify`. L'ALPN exigé est `coopace-group/2`. La protection des clés au repos reste fondée sur les permissions Linux, sans chiffrement ni défense contre un processus hostile du même utilisateur.

Le nom DNS du certificat est `coopace-<32 premiers caractères du hash>.<32 derniers caractères>.invalid`. Ce nom sert à la vérification TLS, sans résolution DNS ; la connexion utilise l'adresse IP choisie. Les labels restent inférieurs à 64 octets.

Le [protocole JSON v2](../packages/protocol/README.md) utilise une longueur de quatre octets en ordre réseau, vérifiée avant allocation, puis au plus 64 Kio de JSON strict. Par connexion et par expéditeur : `hello` en séquence 1, une observation si annoncée, puis `complete`. Le client envoie son observation avant celle du serveur ; le serveur envoie sa fin avant celle du client. Les deux côtés attendent la fin distante. Une erreur ferme la connexion sous-jacente ; une réussite la ferme après les messages de fin, sans session persistante. Les répétitions, mauvais groupes/expéditeurs, séquences invalides, fins prématurées et observations inattendues sont refusés.

La version 1 définie à l'étape 3.3 n'est plus acceptée : la version 2 ajoute le choix de partage et la fin d'échange. Le rapport JSON local de `latency` conserve sa propre version 1.

Sous Windows, les commandes d'aide compilent mais l'identité persistante et les opérations de groupe restent indisponibles avant l'adaptateur de stockage protégé. Cette limite du prototype n'impose pas Linux au produit final. Android reste à développer.

## Vérifier

```sh
sh scripts/go.sh test -count=1 -v ./apps/agent/internal/group
sh scripts/go.sh test ./...
```

`TestGroupLoopbackExchange` doit passer depuis un environnement Linux autorisant les sockets. Les tests en mémoire utilisent [net.Pipe](https://pkg.go.dev/net#Pipe) avec les mêmes configurations TLS, cadrage et moteur d'échange ; ils ne simulent pas une authentification réussie. Les mesures injectées dans ces tests sont des fixtures, pas des résultats réseau.

La suite est l'étude limitée du [prototype de passerelle](ROADMAP.md#étape-4--prototype-de-passerelle), avec point d'application, permissions, mesures de référence et restauration à définir avant toute intervention.
