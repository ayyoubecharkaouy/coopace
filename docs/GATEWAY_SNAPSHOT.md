# Capture locale des files d'une interface Linux

État : commande `snapshot` implémentée et testée avec des sources simulées ; les [six sections sont confirmées sur `wlp3s0`](VALIDATION_GATEWAY_SNAPSHOT_2026-11-12.md) dans le rapport utilisateur, y compris les classes vides vérifiées en texte. La restauration n'est pas implémentée.

La [campagne Go native](VALIDATION_CAKE_GO_CAMPAIGN_2026-11-05.md) a validé le chemin de laboratoire et son nettoyage. Pour préparer une intervention sur une configuration existante, il faut aussi connaître les objets déjà présents. Cette capture conserve davantage de détails que l'[inventaire `inspect`](GATEWAY_DIAGNOSTIC.md), sans modifier le réseau.

## Utilisation

Depuis la racine du dépôt, choisir explicitement une interface indiquée par `inspect`. Remplacer `enp1s0` par son nom réel :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --interface enp1s0
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --interface enp1s0 --json
```

Ces commandes ne demandent pas `sudo`. Les permissions et les versions locales des outils peuvent rendre certaines lectures indisponibles ; leur échec est conservé dans le rapport. Aucun WAN n'est choisi automatiquement. Les interfaces de boucle locale sont refusées ; une interface désactivée peut être observée. Les noms acceptés comportent 1 à 15 caractères ASCII parmi lettres, chiffres, `_`, `-`, `.`, `:`, sans tiret initial ; `.` et `..` sont refusés.

La sortie texte donne l'état des lectures. `--json` conserve leurs options détaillées dans un document JSON local v1 de type `gateway_queue_snapshot`, sur stdout. L'option explicite `--output FICHIER` peut maintenant enregistrer cette capture JSON dans un nouveau fichier privé, sans écraser un fichier existant ; voir [GATEWAY_RECOVERY.md](GATEWAY_RECOVERY.md). Sans cette option, aucun fichier n'est créé automatiquement.

## Sources et bornes

Les six requêtes initiales sont exécutées successivement dans l'espace réseau visible par le processus, avec le même nom d'interface :

| Section | Requête |
| --- | --- |
| `link` | `ip -j -d link show dev NOM` |
| `qdiscs` | `tc -j -s -d qdisc show dev NOM` |
| `classes` | `tc -j -s -d class show dev NOM` |
| `filters_root` | `tc -j -s -d filter show dev NOM root` |
| `filters_ingress` | `tc -j -s -d filter show dev NOM ingress` |
| `filters_egress` | `tc -j -s -d filter show dev NOM egress` |

Une confirmation conditionnelle `tc -s -d class show dev NOM` peut s'ajouter à la lecture des classes ; elle réutilise le même chemin d'outil et la même interface. Il reste six sections dans le rapport, pour un maximum de sept commandes. Les noms de sections et le schéma JSON v1 existants sont conservés ; les champs de preuve supplémentaires sont optionnels.

Chaque lecture conserve la commande, le chemin résolu de l'outil, ses horaires UTC, sa disponibilité et ses objets JSON. Le nom, l'index, le MTU, les flags et l'adresse matérielle de l'interface sont relevés avant les commandes puis comparés après celles-ci. Une disparition ou une différence invalide la capture entière. Cette comparaison aux deux extrémités ne détecte pas tous les changements intermédiaires ni une recréation ayant les mêmes attributs.

Les outils sont recherchés dans le PATH local et leurs chemins symboliques sont résolus. Ils ne sont pas épinglés par empreinte comme ceux du laboratoire ; le rapport ne certifie pas leur provenance. Il n'y a ni shell, ni installation, ni élévation, ni appel de modification réseau, ni trafic de test.

Le lanceur de diagnostic existant limite chaque commande à deux secondes, stdout à 256 Kio et stderr à 4 Kio ; l'ensemble des commandes dispose d'une échéance de quinze secondes. Les réponses doivent être des tableaux d'objets JSON UTF-8, sans clés dupliquées, nombres flottants non finis, données finales supplémentaires ou profondeur excessive. Les entiers gardent leur précision. Le lien doit correspondre au nom, index et MTU observés ; les champs `dev` présents dans les autres objets doivent correspondre à l'interface choisie. Les options du producteur sont conservées sans prétendre valider leur capacité à être restaurées.

Une lecture réussie sans objet produit `available: true, value: []`. Une lecture absente, refusée ou invalide produit `available: false, value: null` et un motif. `partial` est vrai si l'une des six lectures manque. `partial: false` signifie seulement que ces six lectures sont disponibles ; il ne prouve pas l'exhaustivité de la configuration. Une annulation arrête les requêtes suivantes et ne publie aucun rapport.

### Compatibilité avec les classes sans sortie JSON

Le [code amont d'iproute2 v6.1.0](https://github.com/iproute2/iproute2/blob/v6.1.0/tc/tc_class.c) montre que la liste de classes ne crée pas de tableau JSON : une liste vide peut produire zéro octet malgré `-j`. La [version actuelle](https://github.com/iproute2/iproute2/blob/main/tc/tc_class.c) possède un encadrement JSON. Le logiciel ne déduit pas la version du producteur à partir de la seule sortie.

Si la commande JSON des classes réussit et produit uniquement zéro octet ou des espaces ASCII JSON (` `, tabulation, CR, LF), le logiciel effectue la confirmation texte ci-dessus. Si cette seconde commande réussit et reste vide selon la même règle, la section devient disponible avec `value: []`, `normalization: empty_classes_confirmed_by_text` et `source_output` contenant exactement la première sortie. `classes_text_fallback` conserve les arguments, les horaires, le succès de la commande et sa sortie exacte encodée dans `stdout_base64` ; une chaîne vide signifie zéro octet, `null` signifie qu'aucune sortie n'a été conservée. La fin de lecture de la section inclut cette confirmation.

Une confirmation refusée, non vide, trop grande ou annulée ne devient jamais une liste vide. Une sortie de classes non vide et non JSON reste indisponible : le logiciel n'analyse pas de configuration de classes à partir du texte. Ce repli est limité aux classes ; une réponse vide pour les liens, qdisc ou filtres reste invalide. Les délais et limites du lanceur restent applicables, et la collecte demeure non atomique.

Les codes de sortie du binaire sont : `0` pour un rapport, même partiel ; `2` pour des arguments invalides ; `1` pour une erreur globale ou d'écriture ; `130` pour une annulation. Le lanceur `go run` peut traduire ces codes lors du développement.

## Limites et étape suivante

La capture est séquentielle (`atomic: false`) et limitée aux requêtes listées (`completeness: selected_queries_only`). Les filtres attachés à d'autres parents, les blocs partagés, les chaînes, les actions externes, les programmes BPF et les dépendances entre objets ne sont pas inventoriés exhaustivement. Le rapport ne couvre pas les routes, règles de routage, adresses IP, pare-feu, DNS, offloads et services qui pourraient réécrire les files.

Le JSON détaillé peut contenir l'adresse MAC, des adresses de filtres et d'autres identifiants locaux. Il reste distinct de l'export réduit `inspect`, du protocole de groupe et des données ML. Aucun partage n'est réalisé par cette commande.

`restoration: not_implemented` et `traffic_coverage: unverified` restent explicites. Un dump JSON de `tc` ne constitue pas un script de restauration. L'[évaluation et la comparaison de restauration](GATEWAY_RECOVERY.md) sont maintenant implémentées pour un premier profil noqueue : import strict, candidat/refus et comparaison avec une observation ultérieure. L'exécution de la restauration sous supervision indépendante et sa validation restent à réaliser avant toute intervention sur le foyer, conformément à [GATEWAY_BASELINE.md](GATEWAY_BASELINE.md).

## Code et vérification

`platforms/linux/gateway_snapshot*.go` sépare modèles/collecte, validation JSON et accès natifs. `apps/gateway/internal/snapshot` assemble le rapport local et sa provenance ; `internal/cli/snapshot.go` porte les arguments et l'affichage. Les modèles bruts du système ne sont pas ajoutés au noyau métier.

Les tests contrôlent les six commandes exactes, les refus avant exécution, les lectures manquantes, la distinction vide/inconnu, l'identité de l'interface, l'annulation, les JSON malformés, les bornes et la précision, puis l'export et les erreurs de la CLI. Les régressions de compatibilité vérifient la confirmation texte exacte, ses preuves, les classes présentes, erreurs, sorties invalides ou trop grandes, ainsi que l'absence de repli sur les autres sections ou après annulation. Les tests existants du lanceur couvrent délais et sorties excessives. Ils ne remplacent pas une collecte native réussie sur le foyer.

```sh
sh scripts/go.sh test ./platforms/linux ./apps/gateway/internal/cli ./apps/gateway/internal/snapshot
```

Vérification du 6 novembre 2026 : suite Go complète, tests ciblés sans cache après la dernière correction du parseur, `go vet ./...` et compilation Windows amd64 réussis. Le binaire Linux confirme l'aide et les codes de refus. La tentative locale sur `eth0` n'a pas pu commencer la collecte : Netlink est interdit dans cet environnement (`operation not permitted`) ; aucun rapport complet du foyer n'est déclaré validé.

Retour utilisateur du 12 novembre 2026 : le rapport partagé dans la conversation pour `wlp3s0` contient le lien actif, la qdisc racine `noqueue` et trois sélections de filtres vides. La section des classes est indisponible pour JSON inexploitable ; `partial: true` est donc correct pour ce rapport. La sortie brute séparée des classes et la version de `tc` ne sont pas établies par ce retour. Le repli ci-dessus corrige le cas des versions sans JSON lorsque leurs sorties vides peuvent être confirmées. Ce premier retour demandait une nouvelle exécution pour vérifier la correction sur le PC ; il ne valide ni une restauration ni un bénéfice réseau.

Vérification de la correction du 12 novembre 2026 : tests ciblés sans cache et suite Go complète réussis, ainsi que `go vet ./...` et compilation Windows amd64. La [nouvelle exécution utilisateur sur `wlp3s0`](VALIDATION_GATEWAY_SNAPSHOT_2026-11-12.md), commencée à `2026-11-12T01:03:19.348055453Z`, confirme ensuite les six sections disponibles et le repli des classes vides. La provenance VCS reste inconnue dans ce rapport.
