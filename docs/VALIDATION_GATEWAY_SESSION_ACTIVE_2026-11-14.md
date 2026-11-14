# Session Go avec transfert et restauration validée — 14 novembre 2026 (UTC)

## Résultat

Les deux modes du [contrôle de session avec trafic](GATEWAY_SESSION_ACTIVE.md) ont réussi depuis le commit `9d5f895dcfacd54328b74e4a993989500df3b626`. Les quatre codes conservés — contrôle et relecture, en fin normale puis en panne — sont `0`. Une nouvelle relecture indépendante vérifie 164 pièces pour `check` et 161 pour `check-crash`, avec dialogue Go conforme et comparaison finale `selected_state_matches`.

Le transfert normal a envoyé et reçu exactement **4 194 304 octets**, pendant que le pilote Go restait en état `applied`. Le mode panne confirme la mort forcée de Go après observation du trafic avec les deux outils TCP encore vivants, puis leur récupération indépendante. Dans les deux cas, les adresses temporaires sont retirées et la file retourne à noqueue avant suppression des namespaces.

| Observation | `check` | `check-crash` |
| --- | --- | --- |
| Début UTC | `2026-11-14T11:52:10.188882+00:00` | `2026-11-14T11:52:37.175986+00:00` |
| Fin UTC | `2026-11-14T11:52:35.997133+00:00` | `2026-11-14T11:52:54.545916+00:00` |
| Rapport / session | `complete` / `restored_and_closed` | `complete` / `restored_and_closed` |
| UID opérateur Go consigné | `1000` | `1000` |
| PID / code Go | `26871` / `0` | `27205` / `-9`, SIGKILL attendu |
| Outils TCP : réception / émission | `26985` / `26993` | `27281` / `27289` |
| Codes réception / émission après récupération | `0` / `0` | `1` / `1`, outils interrompus |
| Transfert complet | 4 Mio envoyés et reçus | Non revendiqué, `traffic.flow: null` |
| Journal superviseur / commandes | 169 événements / 68 commandes | 165 événements / 67 commandes |
| Pièces vérifiées | 164 | 161 |
| Restauration / nettoyage | Confirmés | Confirmés |

Les trois groupes de chaque contrôle sont récupérés avec zéro descendant supplémentaire. Le journal Go normal comporte six lignes, jusqu'à la demande de récupération et sa sortie ; celui du mode panne s'arrête après quatre lignes, à `applied`. Les journaux de diagnostic Go sont vides. Le superviseur conserve l'installation, le retrait et la comparaison ; le pilote ne revendique pas lui-même la restauration.

## Mesures du transfert normal

| Mesure | Résultat |
| --- | --- |
| Écrit / reçu | `4 194 304` / `4 194 304` octets |
| Durée monotone d'émission | `8 510,391604 ms` |
| Fenêtre de réception première lecture → EOF | `8 770,341926 ms` |
| Débit utile reçu | `478 237,226711` octets/s, soit environ `3,83 Mbit/s` |
| Plafond d'écritures demandé | `1 048 576` octets/s |
| Profil CAKE | Racine `10:`, 4 Mbit/s, besteffort/flows et options de la référence |

Les rapports conservent les horodatages d'écriture, de lecture et d'EOF. La fin de réception intervient après la fin des écritures ; le débit utile utilise la fenêtre première lecture → EOF. Il s'agit d'un débit de charge utile observé sous cette configuration CAKE, sans comparaison permettant de conclure à une amélioration de la connexion Internet.

Dans le mode normal, les relevés CAKE passent de zéro à 130 908 octets et 90 paquets à l'observation avec outils vivants, puis à 4 385 862 octets et 2 903 paquets après transfert. Ce dernier relevé montre `backlog: 0` et `qlen: 0`. Les compteurs de file couvrent également les en-têtes et le trafic de protocole ; ils ne sont pas assimilés aux seuls octets applicatifs reçus.

Dans le mode panne, l'observation préalable au SIGKILL montre 129 394 octets et 89 paquets. La capture avant retrait conserve ensuite 364 130 octets et 245 paquets : le noyau et les outils peuvent encore progresser entre observation, arrêt de Go et récupération des groupes TCP. Ce contrôle ne revendique ni réception des 4 Mio ni vidage complet des tampons avant retrait.

## Ordre, classes et remise en état

L'intention d'ajout CAKE est l'événement 52 et `applied` est reçu à l'événement 62 dans les deux modes. Les adresses temporaires sont vérifiées à l'événement 81, puis le trafic est observé à l'événement 95.

| Étape | `check` | `check-crash` |
| --- | --- | --- |
| Fin de transfert / intention de SIGKILL | `99` / sans objet | Sans objet / `96` |
| Groupes TCP récupérés : émission, réception | `101`, `102` | `97`, `98` |
| Groupe Go récupéré | `103` | `99` |
| Adresses temporaires retirées | `126` | `122` |
| Classes intrinsèques vérifiées | `141` | `137` |
| Intention de retrait CAKE | `144` | `140` |
| Racine possédée retirée | `147` | `143` |
| Retour initial comparé et confirmé | `162` | `158` |
| Descripteurs de namespaces fermés | `163` | `159` |

Les captures initiale, avant ajout, appliquée et finale sont complètes pour les sélections observées. La capture `pre-restore.json` est **partielle uniquement pour les classes non JSON**, conformément au protocole. Les lectures complémentaires exactes sont :

- `check` : `class cake 10:d3 parent 10:` — identifiant de flux intrinsèque 211.
- `check-crash` : `class cake 10:1e0 parent 10:` — identifiant de flux intrinsèque 480.

Ces textes ont été conservés séparément, sans transformer les classes actives en liste vide. L'import Go des captures, la racine CAKE et ses options, les filtres vides et les en-têtes de classes attendus sont vérifiés avant retrait. La capture finale redevient complète, avec noqueue `0:` et comparaison Go conforme à la référence. Les identités du veth restent identiques au sein de chaque contrôle.

Le transfert est direct de `wan` (`10.203.0.5/30`) vers `eth0` (`10.203.0.6/30`) dans les namespaces passerelle et serveur. Les deux adresses sont retirées avant restauration ; le namespace client reste inutilisé. Aucun forwarding, route par défaut ni accès Internet n'est ajouté.

La nouvelle revue constate l'absence des six noms de namespaces, des deux réservations et des 141 PID distincts consignés (135 commandes, deux pilotes Go et quatre outils TCP) :

- `check` : `cg-gh0iuho0-c`, `cg-gh0iuho0-g`, `cg-gh0iuho0-s` ; `/tmp/coopace-guard.gh0iuho0`.
- `check-crash` : `cg-4s5ycgjo-c`, `cg-4s5ycgjo-g`, `cg-4s5ycgjo-s` ; `/tmp/coopace-guard.4s5ycgjo`.

Aucun nettoyage supplémentaire n'est exécuté par cette revue. Les identités de namespaces sont contrôlées pendant chaque session ; leurs numéros d'inode ont été réutilisés après libération entre ces essais successifs et ne servent pas d'identifiants persistants globaux.

## Provenance et pièces

Dossier conservé : `.local/experiments/gateway-session-active-validation-9d5f895/`. Ses 271 entrées figées concordent avant cette consignation. Les trois binaires — passerelle, pilote Go et outil de transfert — portent Go 1.27.3, Linux amd64, la révision ci-dessus et `vcs.modified=false`. L'environnement déclare `simulation: false`, Linux `7.0.0-43-generic`, Python `3.12.3` et tc `iproute2-6.1.0, libbpf 1.3.0`.

| Pièce | SHA-256 |
| --- | --- |
| `prepared.json` | `c34017d682fcfdc09d1c02f74b6a9a1eb1f0fcecfae038f6587a560ae59c8a73` |
| `check/report.json` | `c2e218709287c2158a00f316fdce7ad8ae27dee974b19627b87441cd22a3ea13` |
| `check/comparison.json` | `208735f7e81baa7ed7400535f111cf56181825949bb1b3c647922e14e5b9e42c` |
| `check/worker.jsonl` | `4281a0b5cd8d63283cbaf150662355aab579ed4c71165e50b5486191290be740` |
| `check/pre-restore.json.classes.txt` | `0787704375ab27602120aa38b919eb578b13420f5231ddf66495acf0e2f4918f` |
| `check-crash/report.json` | `3542430182b5a86474bddbfa866b7649250430c4eb08f3664ab452cec684c05a` |
| `check-crash/comparison.json` | `1b0fa7bb85e811003b86acba8b6e2aa594263729e4545cef6d4fde294e6f2369` |
| `check-crash/worker.jsonl` | `991616e4d515c78df29c7799d8c4a5436dc53396cb142b7fc399246eabc7d3ef` |
| `check-crash/pre-restore.json.classes.txt` | `1a38fd23c3f5b9fa7996dbaa359945a087edcabb08c4313d82aa2772f827b26b` |

Les relectures renvoient `gateway_session_active_evidence_reviewed`, `protocol_verified: true`, `selected_state_matches: true`, `execution_source: native_control_report` et `native_certificate: false`. Le manifeste conserve son état historique `not_run` ; les rapports séparés contiennent les résultats réels. Aucun manifeste ni fichier d'essai n'est modifié. Après le commit documentaire, la vérification globale de préparation refusera le nouveau HEAD ; préparer un autre dossier pour un nouvel essai, sans réécrire celui-ci.

## Portée et suite

Ces deux essais valident le transfert borné pendant que Go reste appliqué et la restauration indépendante après fin normale ou SIGKILL de Go pendant le flux, dans le laboratoire virtuel. Le cas de classes actives non JSON est désormais rencontré et traité en natif.

La suite est d'étendre cette session au trafic routé d'un client et d'y associer les mesures de latence au repos/sous charge. La couverture du foyer, IPv6/DNS, la restauration d'une configuration existante, la panne du superviseur et la coupure machine restent ouvertes. La latence et un gain causal ne sont pas évalués ici ; `congestion` reste `not_assessed`, `real_gateway_restoration_validated` reste faux et l'étape 4.2 reste en cours.
