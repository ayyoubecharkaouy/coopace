# Retour à la file initiale validé en laboratoire — 12 novembre 2026 (UTC)

## Résultat

Les deux modes du [cycle de restauration](LAB_QUEUE_RECOVERY.md) ont réussi depuis le commit `b2e4aece90138f842e700c8d371f6b552a60a9e9`. Les codes du contrôle et de sa relecture sont `0` pour `check` et `check-crash`. Une seconde relecture indépendante des fichiers retrouve les mêmes résultats et les mêmes empreintes, sans commande réseau.

Chaque mode confirme `noqueue 0:` → CAKE possédé `10:` → `noqueue 0:` sur un veth neuf, avec comparaison Go de l'état sélectionné **avant** suppression des namespaces. Cette preuve valide un premier retour de file dans le laboratoire ; elle ne valide pas une restauration du réseau du foyer.

| Observation | `check` | `check-crash` |
| --- | --- | --- |
| Début UTC | `2026-11-12T10:42:18.276230+00:00` | `2026-11-12T10:42:30.621960+00:00` |
| Fin UTC | `2026-11-12T10:42:29.918028+00:00` | `2026-11-12T10:42:42.193006+00:00` |
| État du contrôle | `complete` | `complete` |
| CAKE / retrait | Installation vérifiée, racine possédée retirée | Installation vérifiée, racine possédée retirée |
| Comparaison Go | `selected_state_matches` | `selected_state_matches` |
| Pilote | Code `0` | Code `-9`, SIGKILL attendu |
| Descendant récupéré | `1` | `1` |
| Restauration / nettoyage | Tous deux confirmés | Tous deux confirmés |
| Journal / commandes | 101 événements, 45 commandes bornées | 101 événements, 45 commandes bornées |
| Pièces vérifiées | 105 | 105 |

Les imports des captures avec CAKE produisent les refus attendus du profil initial noqueue ; leurs statuts métier `3` ne sont pas des échecs du contrôle. La configuration CAKE est vérifiée séparément avant le retrait.

## État et ordre vérifiés

Les captures `before.json`, `applied.json`, `pre-restore.json` et `after.json` sont disponibles avec `partial: false`. Dans chaque mode, l'identité du veth `wan` reste identique : index 2, MTU 1500, flags 51 et adresse matérielle stable au sein du contrôle. Les classes et les trois sélections de filtres restent vides ; les adresses IP des deux extrémités sont contrôlées avant et après retrait.

CAKE conserve le profil fixe iproute2-6.1.0 : racine `10:`, 4 Mbit/s, besteffort/flows, raw, RTT 100 ms, limite mémoire 1 048 576 octets et autres options de la référence. Ses compteurs octets/paquets restent `0` à l'installation et avant le retrait, conformément au contrôle sans trafic applicatif.

L'intention d'ajout est l'événement 49 ; la récupération du groupe du pilote, l'événement 61 ; l'intention de retrait, l'événement 76 ; la vérification du retour initial, l'événement 94 ; la fermeture des descripteurs de namespaces, l'événement 95. La suppression des espaces intervient ensuite. Les deux intentions précèdent leurs commandes mutantes, avec un seul ajout et un seul retrait ciblé de la racine `10:`.

| Mode | Namespaces supprimés | Réservation supprimée |
| --- | --- | --- |
| `check` | `cg-3t6sr0rm-c`, `cg-3t6sr0rm-g`, `cg-3t6sr0rm-s` | `/tmp/coopace-guard.3t6sr0rm` |
| `check-crash` | `cg-izutnixg-c`, `cg-izutnixg-g`, `cg-izutnixg-s` | `/tmp/coopace-guard.izutnixg` |

La seconde revue constate l'absence des six noms sous `/run/netns` et `/var/run/netns`, des deux réservations et des 94 PID distincts consignés (commandes, pilotes et descendants). Aucune commande de nettoyage supplémentaire n'a été exécutée par cette revue.

## Provenance et pièces

Dossier : `.local/experiments/queue-recovery-validation-b2e4aec/`. Les 249 entrées figées sont vérifiées avant la consignation documentaire. Le binaire est compilé avec Go 1.27.3, Linux amd64, révision source ci-dessus et `vcs.modified=false`. L'environnement indique Linux `7.0.0-42-generic`, Python `3.12.3`, tc `iproute2-6.1.0, libbpf 1.3.0`, et `simulation: false`.

| Pièce | SHA-256 |
| --- | --- |
| `prepared.json` | `81bdbee4d836985ffbd5dcee70207a2dd4852a855e2395a991fcf6b3c5ba6f12` |
| `check/report.json` | `26ce90b00ffcda3affaf14490d2eff9bf298f83b6145525aea5d1361fd98380d` |
| `check/comparison.json` | `f6396d193ac1f3d073d53679896bf6f916aaa56f2424eec0a5b1b471575920fb` |
| `check-crash/report.json` | `2634cd316df686fbd54af7d28c69c450bf634ced5caa2e3252a255906afffb89` |
| `check-crash/comparison.json` | `84ba8e26d3b65f6175c95f4c69d9058f7150075839492e535907936d68250dea` |

Les relectures restent sans écriture, avec `queue_recovery_evidence_reviewed`, `execution_source: native_control_report` et `native_certificate: false`. Aucun certificat automatique n'est ajouté. `prepared.json` conserve son état historique `not_run` ; les résultats effectifs restent dans les deux sous-dossiers et leurs journaux.

Après le commit documentaire, le contrôle global de préparation refusera la nouvelle révision HEAD ; les manifestes ne doivent pas être modifiés pour l'accepter. La relecture des preuves reste possible tant que les scripts et le binaire figés concordent. Pour un nouvel essai, préparer un autre dossier depuis son propre commit.

## Suite et limites

Cette validation clôt les deux essais natifs du premier cycle de retour à noqueue, sans charge, sur ressources virtuelles neuves. La suite consiste à raccorder ce mécanisme à une session de passerelle supervisée du produit, avec propriété et autorisations locales explicites avant toute application.

Le pilote du contrôle reste un processus de cycle de vie Python ; le superviseur installe et retire la file, tandis que Go collecte et compare. La passerelle publique reste en lecture seule. Ni la mort du superviseur, ni la coupure machine, ni la restauration d'une file initiale complexe ne sont couvertes. La topologie réelle, la couverture du trafic du foyer, IPv6/DNS, l'équité et un bénéfice réseau restent à valider. `real_gateway_restoration_validated` reste faux.
