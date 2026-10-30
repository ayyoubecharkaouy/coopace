# Réception et statistiques de file — préparation du goulot actif

## État et périmètre

Le rapport optionnel de réception et les lectures de statistiques TBF sont implémentés et testés en mémoire ou avec des outils simulés. **Leur première validation native est consignée** : réception TCP locale et statistiques à zéro sur liens TBF désactivés. Le [compte rendu](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) conserve les résultats et leurs limites. Le [cycle de vie TBF déjà validé](VALIDATION_LAB_QUEUE_2026-10-29.md) reste distinct de ces nouvelles mesures.

Cette sous-étape prépare les données du [protocole du goulot](VIRTUAL_BOTTLENECK.md). Le [contrôle fonctionnel suivant](LAB_ACTIVE.md) intègre maintenant une topologie active et des lectures périodiques, avec une [première validation native](VALIDATION_LAB_ACTIVE_2026-10-30.md) sur un transfert ; la [campagne de trois paires avec file](LAB_CAMPAIGN.md) est implémentée et testée avec des commandes réseau simulées, en attente de validation native. Les modes existants de `lab-network.sh` et les contrôles TBF sans statistiques gardent leurs sorties et paramètres.

## Rapport côté récepteur

L'outil Go accepte maintenant `coopace-lab-load receive --json`, avec ses options habituelles de cible privée, volume et durée. Sans `--json`, il conserve son comportement précédent : annonce `READY IP:port` sur stdout et comptage final sur stderr.

Avec `--json`, l'annonce READY reste la première ligne, puis un unique objet `synthetic_tcp_receive` v1 est émis après réception exacte du volume et EOF. Une erreur peut donc laisser l'annonce READY, mais aucun rapport de réussite. Ce flux stdout n'est pas un fichier JSON unique : le pilote doit séparer l'annonce et le rapport. Il n'est pas une entrée de `latency compare`.

| Champ | Signification |
| --- | --- |
| `schema_version`, `method` | `1`, `synthetic_tcp_receive`. |
| `os`, `architecture`, `go_version` | Plateforme et compilateur de l'exécutable. |
| `listen`, `requested_bytes`, `received_bytes` | Adresse d'écoute explicite, volume demandé et reçu ; égalité exigée avant publication. |
| `block_bytes`, `timeout_ms` | Tampon de lecture de 16 Kio et délai couvrant aussi l'attente du client. |
| `started_at`, `first_read_at`, `last_read_at`, `finished_at` | UTC : début avant écoute, fin de la première/dernière lecture ayant progressé, puis lecture indiquant EOF. |
| `elapsed_ms` | Durée monotone du contrôle de réception, depuis le début avant écoute jusqu'à EOF. |
| `receive_elapsed_ms` | Durée monotone entre première lecture ayant progressé et EOF ; exclut l'attente initiale. |
| `average_bytes_per_second` | `received_bytes / (receive_elapsed_ms / 1000)`, ou `null` si cette durée est nulle. |

La durée jusqu'à EOF inclut une éventuelle attente après les derniers octets. Si données et EOF arrivent dans une unique lecture, la durée peut être nulle : le débit reste explicitement indisponible. Pour le futur critère de débit du goulot, ce cas sera non exploitable, sans valeur de remplacement.

Les lectures sont bornées au volume attendu plus un octet et ne conservent aucune charge utile. Elles suivent le contrat de [io.Reader](https://pkg.go.dev/io#Reader), notamment les données accompagnées d'une erreur. Le contexte ferme les sockets à l'expiration ; des lectures répétées sans progression sont refusées.

Ce débit décrit les données livrées à l'application réceptrice, pas une capacité WAN ou un débit instantané sur le câble. La première lecture a déjà consommé un bloc pouvant atteindre 16 Kio ; le tamponnement, la granularité des lectures et l'ordonnancement influencent donc le calcul, surtout pour de petits transferts. Aucun débit reçu n'est inventé pour les anciens rapports d'émission.

## Statistiques de TBF

Deux nouveaux contrôles utilisent le même laboratoire DOWN et le même nettoyage : `check-queue-stats` et `check-queue-stats-crash`. Ils ajoutent `tc -j -s -r qdisc show dev wan`, exécuté dans la passerelle possédée, après ajout et après fin du pilote. Les commandes et sorties gardent les bornes du [cycle de vie TBF](LAB_QUEUE.md).

Le format des statistiques vient de [tc_util.c d'iproute2](https://github.com/iproute2/iproute2/blob/main/tc/tc_util.c). Les sorties brutes JSON sont conservées avec les paramètres de file vérifiés. Les sept champs requis doivent être des entiers non négatifs représentables sur 64 bits ; un champ absent ou invalide provoque une erreur et le nettoyage.

| Valeurs normalisées | Interprétation |
| --- | --- |
| `statistics.counters.bytes`, `packets` | Compteurs cumulés annoncés par la file, distincts des octets utiles reçus par une application. |
| `statistics.counters.drops`, `overlimits`, `requeues` | Événements cumulés de la file ; ils ne sont pas une perte de paquets de bout en bout. |
| `statistics.backlog_bytes`, `queued_packets` | Jauges instantanées issues de `backlog` et `qlen`, pouvant augmenter ou diminuer normalement. |

Chaque lecture ajoute `elapsed_since_start_ms`, depuis le début monotone de préparation du contrôle, et `read_duration_ms`, durée de la commande et de ses contrôles. `collected_at` reste une date UTC de fin de lecture. Ces temps ne désignent pas un instantané atomique du noyau.

`queue.statistics_delta` compare uniquement les cinq compteurs cumulés entre les deux lectures. Il contient `available: true`, `reason: null` et leurs différences, ou `available: false`, `reason: counter_decreased`, `counters: null` si l'un diminue. Les lectures originales restent présentes. Aucune différence de backlog ni estimation de débit n'est ajoutée.

Les identités des espaces et les paramètres TBF sont vérifiés ; le contrôle ne remplace pas la file entre lectures. Cela ne détecte pas toute recréation identique effectuée par un processus privilégié étranger. Une observation valide sans différence interprétable reste une collecte technique réussie ; le code `0` n'atteste ni saturation ni bénéfice.

Le rapport local v1 a pour type `lab_queue_statistics_check`, distinct de `lab_queue_check`. Il garde les champs de supervision et `queue_applied: true`, même si la file a déjà été supprimée au moment de sa publication. Aucun trafic applicatif n'est généré sur le lien DOWN ; les compteurs observés seront consignés sans en déduire une congestion.

## Vérification et essai natif

Depuis le dépôt, sans privilèges :

```sh
sh scripts/go.sh test -count=1 ./scripts/lab-load
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_[gq]*.py' -v
python3 -I scripts/lab-guard.py plan-queue
```

Les tests Go vérifient volume exact, EOF, durées, débit indisponible, erreurs, limites et sortie optionnelle. Les tests Python vérifient champs manquants, valeurs invalides, compteurs en baisse, jauges décroissantes et nettoyage. Ils n'effectuent aucune création de réseau réel. Le test `TestLoopbackSyntheticTransfer` est ignoré explicitement si les sockets sont interdites.

Pour valider la réception sur le PC Linux sans élévation, exécuter ce test avec `-count=1` et conserver un résultat PASS, sans SKIP :

```sh
sh scripts/go.sh test -count=1 -v -run '^TestLoopbackSyntheticTransfer$' ./scripts/lab-load
```

Il effectue un vrai transfert TCP local et vérifie le JSON du récepteur. Il ne mesure pas un lien à 4 Mbit/s. Les deux contrôles natifs de statistiques demandent ensuite les privilèges et outils de `check-queue` :

```sh
sudo python3 -I scripts/lab-guard.py check-queue-stats
sudo python3 -I scripts/lab-guard.py check-queue-stats-crash
```

Préparer un dossier neuf avec protocole, commit et empreintes figés. Le lanceur doit conserver le test local, les deux rapports de statistiques, les journaux et codes exacts, puis refuser un résultat SKIP ou tout écrasement. Les [premiers contrôles natifs](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) sont validés. Le [contrôle fonctionnel actif](LAB_ACTIVE.md) intègre maintenant ces mesures et la collecte périodique ; son [premier essai natif](VALIDATION_LAB_ACTIVE_2026-10-30.md) est validé. La campagne de trois paires et l'étape 4.2 restent ouvertes.
