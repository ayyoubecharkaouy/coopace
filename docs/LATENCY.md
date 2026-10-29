# Latence TCP et référence avant intervention — étape 3.2

## Méthode retenue

`coopace latency` mesure la durée d'établissement de nouvelles connexions TCP vers une cible explicitement choisie. Chaque connexion réussie est fermée immédiatement, sans requête HTTP, négociation TLS ni donnée applicative envoyée par Coopace.

La mesure chronomètre l'appel à [`net.Dialer.DialContext`](https://pkg.go.dev/net#Dialer.DialContext) avec un délai maximal et utilise les [durées monotones de Go](https://pkg.go.dev/time#hdr-Monotonic_Clocks). La cible doit être une adresse IP littérale avec port numérique, validée avec [`netip.ParseAddrPort`](https://pkg.go.dev/net/netip#ParseAddrPort), pour exclure la résolution DNS du chronométrage. Aucun serveur public ou routeur n'est sélectionné automatiquement.

Cette durée inclut le traitement par les systèmes et l'établissement TCP. **Ce n'est pas un RTT ICMP, une mesure directe de perte de paquets, une gigue normalisée ou la latence d'un jeu/flux QUIC.** Un serveur saturé, un refus de connexion ou son filtrage peuvent influencer les résultats sans démontrer une congestion WAN.

## Utilisation

Choisir un service TCP accessible qui accepte de nouvelles connexions. L'adresse ci-dessous est un exemple à remplacer par celle de la cible choisie :

```sh
coopace_target='192.168.1.1:443'
sh scripts/go.sh run ./apps/agent/cmd/coopace latency --target "$coopace_target" --condition idle
sh scripts/go.sh run ./apps/agent/cmd/coopace latency --help
```

IPv6 utilise la forme `[adresse]:port`, avec une zone si nécessaire pour une adresse de lien local. La boucle locale est acceptée pour tester le logiciel ; ses résultats ne représentent pas une latence Internet.

| Option | Valeur par défaut et limites |
| --- | --- |
| `--target` | Obligatoire, IP littérale unicast et port de 1 à 65535 ; aucun nom de domaine. |
| `--count` | 5 essais ; de 1 à 100. |
| `--timeout` | `1s` par essai ; positif et au plus de `10s`. |
| `--interval` | `250ms` de pause après chaque essai, sauf le dernier ; de `0s` à `5s`. |
| `--condition` | `unspecified`, `idle` ou `loaded` ; étiquette déclarée par l'utilisateur, jamais détectée automatiquement. |
| `--json` | Rapport JSON local v1 sur la sortie standard, à la place du texte. |

Le code de sortie du binaire est `0` si au moins un essai réussit, `1` si tous échouent ou qu'une erreur d'exécution/affichage survient, `2` pour des arguments invalides et `130` après annulation par Ctrl+C. Les échecs restent visibles même lorsque le code est `0`. `go run` peut modifier le code de sortie présenté par le programme Go ; utiliser le binaire compilé pour vérifier les codes exacts.

## Statistiques et valeurs absentes

Les durées des connexions réussies sont triées pour calculer min, p50, p95, p99 et max. Les percentiles utilisent le rang le plus proche supérieur : pour `n` réussites et un percentile `p`, prendre le rang `ceil(p × n / 100)`, à partir de 1.

Les essais échoués sont comptés séparément et exclus des percentiles. Ils ne sont remplacés ni par zéro ni par le délai maximal. Si tous échouent, les durées sont indisponibles (`null` dans le JSON). Les catégories d'échec sont `timeout` et `connection_failed` ; elles ne permettent pas d'estimer une perte de paquets.

Avec une à cinq réussites, p95 et p99 sont le maximum observé. Ces résultats sont exploratoires et ne constituent pas une estimation fiable des queues de distribution. Toujours conserver le nombre de réussites, les échecs et les échantillons individuels pour interpréter une comparaison.

## Format local de conservation

Le format JSON est défini à cette étape dans `apps/agent/internal/latency/json.go`. Il s'agit d'un export local v1, distinct du protocole réseau du groupe v2. Les mesures de latence ne sont pas échangées par le prototype de l'étape 3.4.

| Champs | Signification |
| --- | --- |
| `schema_version`, `method` | `1` et `tcp_connect`. |
| `coopace_version`, `go_version`, `os`, `architecture` | Version de développement, compilateur Go et plateforme de l'exécutable. |
| `target`, `declared_condition` | IP:port explicitement choisis et condition déclarée. |
| `requested_attempts`, `timeout_ms`, `pause_between_attempts_ms` | Paramètres de la série. |
| `started_at`, `finished_at`, `attempts[].started_at` | Horodatages UTC ; les durées sont calculées avant leur conversion pour l'export. |
| `attempts[].connect_ms`, `attempts[].failure` | Durée en millisecondes pour une réussite, sinon `null` et catégorie d'échec. |
| `successful`, `failed` | Comptages réels. |
| `connect_ms` | Distribution min/p50/p95/p99/max en millisecondes, ou `null` sans réussite. |

Coopace ne crée aucun fichier automatiquement. La redirection suivante conserve volontairement le rapport dans un dossier exclu de Git :

```sh
mkdir -p .local/baselines
sh scripts/go.sh run ./apps/agent/cmd/coopace latency --target "$coopace_target" --count 30 --condition idle --json > .local/baselines/idle.json
```

Un rapport complet est émis même si toutes les connexions échouent, avec un code non nul. Une annulation ou une erreur de configuration ne produit pas de rapport complet. L'IP cible apparaît dans le fichier par choix de l'utilisateur ; aucun nom d'appareil, identifiant de groupe, URL ou contenu n'est ajouté automatiquement. Aucun rapport n'est envoyé au groupe ni utilisé automatiquement pour entraîner le ML.

## Protocole de référence avant optimisation

1. Fixer la cible, les paramètres, le chemin réseau, les conditions d'essai et les seuils d'acceptation avant de mesurer. Conserver la configuration initiale et consigner le commit Git utilisé ; la version `dev` seule ne distingue pas les révisions du logiciel.
2. Recueillir plusieurs séries au repos, avec `--condition idle`. Consigner les autres usages connus ; l'étiquette ne prouve pas l'absence de trafic.
3. Refaire les mêmes séries avec une charge connue et autorisée, lancée séparément, puis `--condition loaded`. Coopace ne génère pas de téléchargement de saturation à cette étape.
4. Comparer les séries sur la même méthode, cible et configuration, en examinant les échecs aussi bien que les durées. Une baisse des percentiles accompagnée de plus d'échecs n'est pas une preuve d'amélioration.
5. Conserver les paramètres, données individuelles et limites. Les comparaisons après intervention et face aux moteurs existants appartiennent à l'étape passerelle.

La comparaison hors ligne décrite ci-dessous charge désormais deux rapports pour présenter leurs différences. Elle ne calcule pas de gain causal d'optimisation. Les mesures TCP, les compteurs d'interfaces et les futurs essais applicatifs restent des observations complémentaires.

## Comparer les rapports au repos et sous charge

Une fois les rapports réellement recueillis avec la même cible et les mêmes paramètres :

```sh
sh scripts/go.sh run ./apps/agent/cmd/coopace latency compare --idle .local/baselines/idle.json --loaded .local/baselines/loaded.json
```

Cette sous-commande lit uniquement ces deux fichiers. Elle n'appelle pas la mesure TCP et ne lance aucune charge. Les deux chemins doivent désigner des fichiers ordinaires sans lien symbolique, limités chacun à 256 Kio. L'aide est disponible avec `latency compare --help`.

Le lecteur attend les exports locaux v1 de méthode `tcp_connect`, avec conditions déclarées `idle` et `loaded`. Il refuse les champs inconnus ou requis manquants, doublons, variantes de casse, alias Unicode de clés, valeurs invalides, séries incomplètes et horodatages incohérents. Les durées en millisecondes sont converties à la nanoseconde la plus proche, puis les comptages et percentiles sont recalculés à partir des essais ; ils doivent correspondre au résumé importé.

La cible doit être textuellement identique, ainsi que le nombre d'essais demandé, le timeout, l'intervalle, la version Coopace, la version Go, le système et l'architecture déclarés. Ces vérifications sont conservatrices : elles ne prouvent ni le même appareil, ni le même commit derrière `dev`, ni le même chemin ou la même charge. Ces éléments restent à consigner dans le [protocole de laboratoire](GATEWAY_BASELINE.md).

L'affichage présente les réussites, les échecs, les distributions et l'écart signé **charge moins repos**, en millisecondes. Les distributions utilisent les seules réussites. Si une série n'a aucune réussite, sa distribution et l'écart correspondant restent indisponibles. Une différence négative accompagnée de plus d'échecs ne prouve pas une amélioration ; aucun diagnostic de congestion ni bénéfice Coopace n'est déduit.

Le code de sortie est `0` si la comparaison descriptive a été produite, même lorsqu'une distribution est indisponible ; `1` pour une erreur de fichier, de validation ou d'affichage ; `2` pour des arguments invalides ; `130` après annulation détectée. Les lectures de fichiers locaux ne sont pas interruptibles individuellement ; l'annulation est contrôlée avant la lecture et avant l'affichage. Le code `0` ne signifie pas que les connexions étaient réussies ni que le réseau s'est amélioré.

Les tests de comparaison utilisent des données contrôlées, y compris des séries sans réussite et des durées à zéro. Aucune référence WAN réelle ni comparaison sous charge n'est validée par ces tests.

## Validation et limites actuelles

Les tests déterministes couvrent les percentiles, valeurs absentes, unités, échecs, cibles et paramètres invalides, annulation et export JSON. La compilation et l'analyse statique passent sous Linux et pour Windows amd64.

Le test `TestProbeLoopbackConnectsAndClosesWithoutPayload` a réussi dans le terminal de développement de l'utilisateur sous Linux. Il vérifie une véritable connexion locale, sa fermeture et l'absence de données applicatives. Dans l'environnement isolé de l'agent de développement, il est ignoré avec un motif explicite car les sockets sont interdites. Le chemin d'échec de la commande et son export JSON sans fausses durées y ont été vérifiés.

Ces résultats ne valident pas une mesure WAN ni l'exécution native Windows. Pour reproduire le test local sans utiliser de serveur extérieur :

```sh
sh scripts/go.sh test -count=1 -v ./apps/agent/internal/latency
```

Les compteurs Linux restent décrits dans [OBSERVATIONS.md](OBSERVATIONS.md), et les essais Windows dans [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md).
