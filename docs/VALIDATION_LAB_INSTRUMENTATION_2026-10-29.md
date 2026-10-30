# Première validation native de l'instrumentation — 29 octobre 2026 (UTC)

## Résultat et portée

Les trois contrôles du lanceur ont réussi sur le PC Linux utilisateur : **réception TCP locale avec rapport JSON, statistiques TBF après fin normale et après mort forcée du pilote**. Le test Go et la vérification de son rapport ont chacun un code `0` ; les deux contrôles TBF ont également un code `0`.

La réception et TBF sont deux expériences distinctes : le transfert passe uniquement par la boucle locale, tandis que les liens TBF restent DOWN. Ce résultat valide l'instrumentation ciblée, sans mesurer un goulot actif, une capacité WAN ou un gain Coopace. L'étape 4.2 reste ouverte.

## Réception effectivement mesurée

`TestLoopbackSyntheticTransfer` est passé sans SKIP. Il effectue un vrai transfert TCP, contrôle la sortie JSON du récepteur, puis inscrit ce rapport dans le journal JSON des tests. Le vérificateur local a extrait le rapport et recalculé son débit ; la revue a reproduit ces contrôles sans relancer de transfert.

| Élément | Observation |
| --- | --- |
| Méthode et version | `synthetic_tcp_receive`, schéma local v1 |
| Plateforme | Linux amd64, Go 1.27.3 |
| Volume demandé / reçu | 32 785 / 32 785 octets, EOF confirmé par le test |
| Durée totale monotone | 8.571703ms |
| Fenêtre monotone première lecture → EOF | 8.474147ms |
| Débit utile applicatif reçu | 3 868 825.971511 octets/s, recalculé depuis volume et fenêtre de réception |

La réception va de `2026-10-29T22:43:49.478090153Z` à `2026-10-29T22:43:49.486661852Z`. Ce petit transfert local ne constitue pas une estimation fiable d'un débit réseau et n'est pas soumis à la file TBF à 4 Mbit/s. Les durées sont monotones ; les horaires UTC servent à la provenance, pas au recalcul du débit.

## Statistiques TBF effectivement relues

Les deux contrôles disposent d'une lecture après ajout et d'une lecture après fin du pilote. Les quatre sorties brutes sont valides ; leur normalisation et leurs différences ont été reproduites avec le module livré.

| Contrôle | Code du pilote | Descendants récupérés | Différence de compteurs |
| --- | --- | --- | --- |
| `check-queue-stats` | 0 | 1 | Disponible, cinq différences à zéro |
| `check-queue-stats-crash` | -9, SIGKILL attendu | 1 | Disponible, cinq différences à zéro |

Dans les quatre lectures, les compteurs `bytes`, `packets`, `drops`, `overlimits`, `requeues`, ainsi que les jauges `backlog` et `qlen`, valent zéro. Ces zéros proviennent des données réellement fournies par `tc`, sans remplacement de champ absent. Les paramètres effectifs restent `rate: 500000` octets/s, `burst: 65536` octets et `limit: 131072` octets, sous une unique racine TBF `10:`.

Les durées des commandes de statistiques vont de 10.805725ms à 11.191041ms. Les temps monotones depuis le début du contrôle et les horaires UTC sont cohérents dans les rapports. Ces deux lectures par contrôle ne valident pas une collecte périodique à 250ms. Les progressions non nulles et les baisses de compteurs restent couvertes par les tests simulés.

## Provenance et conservation

- Commit source : `023f7d0451d3cffe2e378c59ba30c5858700e0f7`.
- Dossier local : `.local/experiments/instrumentation-validation-023f7d0/`.
- Préparation : `2026-10-29T22:41:09.812127+00:00`, Python 3.12.3 et Go 1.27.3 consignés.
- Les empreintes des entrées correspondent à la préparation ; les sources et le module Go correspondent au commit.

Le dossier conserve les protocoles figés, la prévisualisation, le lanceur, le vérificateur, les événements des tests, les rapports, journaux et codes exacts. `prepared.json` reste inchangé avec son état antérieur `not_run`. Le nouveau `validation.json` consigne la revue et les empreintes de vingt pièces conservées ; ces données brutes restent locales et exclues de Git.

| Pièce | SHA-256 |
| --- | --- |
| `receiver-test.jsonl` | `d092cde98767ba629d8fa6d3fadf2a1783a2bc598f7ab78a44be5683e79708a1` |
| `receiver-report.json` | `d01f12e7fef149fb2193e7eb1800bacaacf5bc23e9b644b1fc9bdb49da7088c8` |
| `check-queue-stats.json` | `3d183bdca048d330f52b8453f92e7daabf5514530417c274f084e9faf6c3828e` |
| `check-queue-stats-crash.json` | `752a14d24dd52dfaab4b0a098958730c44f8a35c78451d61012ab84bf7283f0e` |

## Nettoyage et suite

Les journaux et rapports confirment la récupération d'un descendant par contrôle TBF, y compris après SIGKILL du pilote, puis la suppression des ressources possédées. Les six noms `cg-wpz_65jh-c/g/s`, `cg-t5qd0i0v-c/g/s` et les réservations `/tmp/coopace-guard.wpz_65jh`, `/tmp/coopace-guard.t5qd0i0v` ne sont plus visibles depuis l'environnement de développement. Les chemins exacts sous `/run/netns`, `/var/run/netns` et `/tmp` ont été contrôlés.

Ces absences de noms ne prouvent pas l'absence de références détenues par un processus étranger. La destruction du superviseur et la restauration d'une passerelle réelle ne sont pas validées.

La prochaine sous-étape intègre ces mesures à la topologie active sous supervision, avec ses contrôles de passage et sa collecte périodique, avant la campagne du [goulot virtuel](VIRTUAL_BOTTLENECK.md). Les modes historiques de `lab-network.sh` gardent leur comportement. Voir le [protocole d'instrumentation](LAB_INSTRUMENTATION.md).
