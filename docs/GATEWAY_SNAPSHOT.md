# Capture locale des files d'une interface Linux

État : commande `snapshot` implémentée et testée avec des sources simulées. Une collecte complète sur l'interface du foyer reste à effectuer. La restauration n'est pas implémentée.

La [campagne Go native](VALIDATION_CAKE_GO_CAMPAIGN_2026-11-05.md) a validé le chemin de laboratoire et son nettoyage. Pour préparer une intervention sur une configuration existante, il faut aussi connaître les objets déjà présents. Cette capture conserve davantage de détails que l'[inventaire `inspect`](GATEWAY_DIAGNOSTIC.md), sans modifier le réseau.

## Utilisation

Depuis la racine du dépôt, choisir explicitement une interface indiquée par `inspect`. Remplacer `enp1s0` par son nom réel :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --interface enp1s0
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --interface enp1s0 --json
```

Ces commandes ne demandent pas `sudo`. Les permissions et les versions locales des outils peuvent rendre certaines lectures indisponibles ; leur échec est conservé dans le rapport. Aucun WAN n'est choisi automatiquement. Les interfaces de boucle locale sont refusées ; une interface désactivée peut être observée. Les noms acceptés comportent 1 à 15 caractères ASCII parmi lettres, chiffres, `_`, `-`, `.`, `:`, sans tiret initial ; `.` et `..` sont refusés.

La sortie texte donne l'état des lectures. `--json` conserve leurs options détaillées dans un document JSON local v1 de type `gateway_queue_snapshot`, sur stdout. Aucun fichier n'est créé automatiquement. Le fichier éventuellement obtenu par redirection reste sous le contrôle de l'utilisateur.

## Sources et bornes

Les six requêtes sont exécutées successivement dans l'espace réseau visible par le processus, avec le même nom d'interface :

| Section | Requête |
| --- | --- |
| `link` | `ip -j -d link show dev NOM` |
| `qdiscs` | `tc -j -s -d qdisc show dev NOM` |
| `classes` | `tc -j -s -d class show dev NOM` |
| `filters_root` | `tc -j -s -d filter show dev NOM root` |
| `filters_ingress` | `tc -j -s -d filter show dev NOM ingress` |
| `filters_egress` | `tc -j -s -d filter show dev NOM egress` |

Chaque lecture conserve la commande, le chemin résolu de l'outil, ses horaires UTC, sa disponibilité et ses objets JSON. Le nom, l'index, le MTU, les flags et l'adresse matérielle de l'interface sont relevés avant les commandes puis comparés après celles-ci. Une disparition ou une différence invalide la capture entière. Cette comparaison aux deux extrémités ne détecte pas tous les changements intermédiaires ni une recréation ayant les mêmes attributs.

Les outils sont recherchés dans le PATH local et leurs chemins symboliques sont résolus. Ils ne sont pas épinglés par empreinte comme ceux du laboratoire ; le rapport ne certifie pas leur provenance. Il n'y a ni shell, ni installation, ni élévation, ni appel de modification réseau, ni trafic de test.

Le lanceur de diagnostic existant limite chaque commande à deux secondes, stdout à 256 Kio et stderr à 4 Kio ; l'ensemble des commandes dispose d'une échéance de quinze secondes. Les réponses doivent être des tableaux d'objets JSON UTF-8, sans clés dupliquées, nombres flottants non finis, données finales supplémentaires ou profondeur excessive. Les entiers gardent leur précision. Le lien doit correspondre au nom, index et MTU observés ; les champs `dev` présents dans les autres objets doivent correspondre à l'interface choisie. Les options du producteur sont conservées sans prétendre valider leur capacité à être restaurées.

Une lecture réussie sans objet produit `available: true, value: []`. Une lecture absente, refusée ou invalide produit `available: false, value: null` et un motif. `partial` est vrai si l'une des six lectures manque. `partial: false` signifie seulement que ces six lectures sont disponibles ; il ne prouve pas l'exhaustivité de la configuration. Une annulation arrête les requêtes suivantes et ne publie aucun rapport.

Les codes de sortie du binaire sont : `0` pour un rapport, même partiel ; `2` pour des arguments invalides ; `1` pour une erreur globale ou d'écriture ; `130` pour une annulation. Le lanceur `go run` peut traduire ces codes lors du développement.

## Limites et étape suivante

La capture est séquentielle (`atomic: false`) et limitée aux requêtes listées (`completeness: selected_queries_only`). Les filtres attachés à d'autres parents, les blocs partagés, les chaînes, les actions externes, les programmes BPF et les dépendances entre objets ne sont pas inventoriés exhaustivement. Le rapport ne couvre pas les routes, règles de routage, adresses IP, pare-feu, DNS, offloads et services qui pourraient réécrire les files.

Le JSON détaillé peut contenir l'adresse MAC, des adresses de filtres et d'autres identifiants locaux. Il reste distinct de l'export réduit `inspect`, du protocole de groupe et des données ML. Aucun partage n'est réalisé par cette commande.

`restoration: not_implemented` et `traffic_coverage: unverified` restent explicites. Un dump JSON de `tc` ne constitue pas un script de restauration. Le prochain incrément devra définir les configurations prises en charge, refuser les dépendances non maîtrisées, puis préparer et tester une restauration indépendante avant toute intervention sur le foyer, conformément à [GATEWAY_BASELINE.md](GATEWAY_BASELINE.md).

## Code et vérification

`platforms/linux/gateway_snapshot*.go` sépare modèles/collecte, validation JSON et accès natifs. `apps/gateway/internal/snapshot` assemble le rapport local et sa provenance ; `internal/cli/snapshot.go` porte les arguments et l'affichage. Les modèles bruts du système ne sont pas ajoutés au noyau métier.

Les tests contrôlent les six commandes exactes, les refus avant exécution, les lectures manquantes, la distinction vide/inconnu, l'identité de l'interface, l'annulation, les JSON malformés, les bornes et la précision, puis l'export et les erreurs de la CLI. Les tests existants du lanceur couvrent délais et sorties excessives. Ils ne remplacent pas une collecte native réussie sur le foyer.

```sh
sh scripts/go.sh test ./platforms/linux ./apps/gateway/internal/cli ./apps/gateway/internal/snapshot
```

Vérification du 6 novembre 2026 : suite Go complète, tests ciblés sans cache après la dernière correction du parseur, `go vet ./...` et compilation Windows amd64 réussis. Le binaire Linux confirme l'aide et les codes de refus. La tentative locale sur `eth0` n'a pas pu commencer la collecte : Netlink est interdit dans cet environnement (`operation not permitted`) ; aucun rapport complet du foyer n'est déclaré validé.
