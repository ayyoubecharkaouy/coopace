# Capture locale sur Wi-Fi confirmée — 12 novembre 2026 (UTC)

La commande [`snapshot`](GATEWAY_SNAPSHOT.md) a produit ses six sections disponibles sur l'interface `wlp3s0` du PC Linux utilisateur. Le rapport partagé dans la conversation indique `partial: false` et confirme la compatibilité avec une liste de classes vide sans sortie JSON.

## Exécution rapportée

Depuis la racine du dépôt, sans `sudo` :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --interface wlp3s0 --json
```

| Champ | Valeur rapportée |
| --- | --- |
| Type / schéma | `gateway_queue_snapshot` / `1` |
| Système / architecture | `linux` / `amd64` |
| SDK / version applicative | `go1.27.3` / `dev` |
| Début UTC | `2026-11-12T01:03:19.348055453Z` |
| Fin UTC | `2026-11-12T01:03:19.377841785Z` |
| Interface | `wlp3s0`, index `3`, MTU `1500`, état du lien `UP` |
| Portée / mode | `process_network_namespace` / `read_only` |
| Outils résolus | `/usr/bin/ip`, `/usr/sbin/tc` |
| Résultat | Six sections `available: true`, `partial: false` |

## Observations

| Section | Résultat |
| --- | --- |
| `link` | Un lien portant le nom, index et MTU attendus ; `qdisc: noqueue`. |
| `qdiscs` | Une racine `noqueue`, handle `0:`, options `{}` ; compteurs exportés à zéro. |
| `classes` | Liste vide confirmée par une lecture texte supplémentaire réussie. |
| `filters_root` | Liste vide `[]`. |
| `filters_ingress` | Liste vide `[]`. |
| `filters_egress` | Liste vide `[]`. |

La section `classes` conserve `source_output: ""` et `normalization: empty_classes_confirmed_by_text`. La confirmation exécute `tc -s -d class show dev wlp3s0` avec `succeeded: true` et `stdout_base64: ""`. Ces deux sorties vides et les six disponibilités concordent avec `partial: false`.

Le premier retour du même jour, commencé à `2026-11-12T00:54:52.504871976Z`, avait cinq sections disponibles et des classes indisponibles pour JSON inexploitable. Il conserve son résultat partiel ; la nouvelle exécution confirme séparément le comportement corrigé.

## Provenance et limites

La source de ce compte rendu est le JSON fourni par l'utilisateur dans la conversation. La version applicative est `dev` ; les champs VCS, révision et état modifié sont `null`. Le rapport n'atteste donc pas une révision de compilation précise, ni la version de `tc`. Le dépôt est au commit `048dc49` lors de la consignation ; ses tests Go, `go vet` et compilation Windows ont déjà réussi à l'étape précédente. Cette lecture du résultat ne constitue pas une nouvelle exécution indépendante.

La réussite porte sur les six sélections annoncées et leur compatibilité sur cette interface. `atomic: false` et `completeness: selected_queries_only` restent explicites. Les compteurs de `noqueue` à zéro ne démontrent ni une absence de trafic Internet ni une absence de files ailleurs dans le chemin réseau.

`traffic_coverage: unverified` et `restoration: not_implemented` restent inchangés. Ce PC connecté en Wi-Fi n'est pas établi comme point de passage du trafic des autres appareils. Aucun bénéfice réseau, capacité WAN, support d'OpenWrt ou restauration de configuration existante n'est validé par cette observation.

## Suite

Cette exécution confirme la collecte locale et la correction des classes vides. Le prochain incrément doit définir les configurations de files prises en charge pour la restauration et les refus nécessaires pour les autres configurations. L'application et le retour arrière devront être testés sur des ressources jetables avant toute intervention sur le réseau du foyer ; voir [GATEWAY_BASELINE.md](GATEWAY_BASELINE.md).
