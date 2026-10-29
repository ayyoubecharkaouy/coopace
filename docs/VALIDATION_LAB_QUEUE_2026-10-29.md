# Premier contrôle natif du cycle de vie TBF — 29 octobre 2026

## Résultat et portée

Le lanceur a exécuté quatre contrôles sur le PC Linux utilisateur. **Les quatre codes de sortie conservés valent `0`**. Les contrôles sans file revérifient le superviseur modifié ; les deux suivants ajoutent TBF sur une veth administrativement désactivée, puis vérifient sa présence après la fin du pilote et le nettoyage du laboratoire.

| Contrôle | Code du pilote | Descendants récupérés | File pendant le contrôle |
| --- | --- | --- | --- |
| `check` | 0 | 1 | Aucune |
| `check-crash` | -9, SIGKILL attendu | 1 | Aucune |
| `check-queue` | 0 | 1 | TBF `10:` sur `wan` |
| `check-queue-crash` | -9, SIGKILL attendu | 1 | TBF `10:` sur `wan` |

Ce résultat valide le [cycle de vie ciblé](LAB_QUEUE.md), y compris après mort forcée du pilote. **Le lien reste DOWN** : aucun débit effectif, ordonnancement de paquets, niveau de congestion ou gain d'optimisation n'est validé. Aucune adresse, route, sonde ou charge applicative n'est ajoutée par ces contrôles.

## Configuration effectivement relue

Les deux contrôles avec file commencent par un dump vide, conforme à l'état attendu d'une veth neuve désactivée. Après ajout et après fin du pilote, chacun contient une unique racine TBF `10:`, avec les mêmes options :

| Paramètre | Valeur relue dans les quatre lectures TBF |
| --- | --- |
| `options.rate` | 500 000 octets/s, correspondant aux 4 000 000 bits/s demandés |
| `options.burst` | 65 536 octets, sans écart de représentation observé |
| `options.limit` | 131 072 octets |

Les lectures de `check-queue` vont de `2026-10-29T22:19:53.922927+00:00` à `2026-10-29T22:19:54.017731+00:00`. Celles de `check-queue-crash` vont de `2026-10-29T22:19:54.405341+00:00` à `2026-10-29T22:19:54.495046+00:00`. Ces horaires décrivent les lectures enregistrées, pas la durée totale des quatre contrôles.

Les deux JSON avec file ont été revérifiés avec les validateurs de configuration livrés. `queue_applied: true` décrit la configuration pendant ces contrôles ; les rapports sont publiés après nettoyage et ne désignent pas une file restée active.

## Provenance et pièces conservées

- Commit source : `9d1d9002148b74d5bb39c04f06b0d61f88150733`.
- Dossier local : `.local/experiments/queue-validation-9d1d900/`.
- Préparation : `2026-10-29T22:19:20.301993+00:00`, Python 3.12.3 dans l'environnement de préparation.
- Les deux scripts correspondent au commit ; toutes les empreintes des entrées correspondent à la préparation.

`prepared.json`, les copies figées `protocol.md` et `supervisor-protocol.md`, `plan.txt`, `inputs.sha256` et `run.sh` sont conservés inchangés. Les quatre rapports, journaux et codes restent locaux et exclus de Git. `validation.json` consigne la revue et les empreintes de toutes ces pièces.

| Rapport | SHA-256 |
| --- | --- |
| `check.json` | `094cc56e6ccba40a5c98f9b44df40cb40bf1d7c45bc81736c0c899a842cf5845` |
| `check-crash.json` | `d0ad49e18a74144f237c3e08762299d67414bde4d40eab40006d640b49dbbe59` |
| `check-queue.json` | `2f3970c41ed54b29655c45738e6487b16aa3e3f96f286b63a32a90d8be5e9bb2` |
| `check-queue-crash.json` | `32a64eb38b2cac694a915a5e3d9f1c1f82b05d9bb6877faa13f791a9614cf826` |

## Nettoyage vérifié et limites

Les quatre rapports indiquent `cleanup_verified: true` et `traffic_generated: false`. Les journaux concordent avec les PID et réservations annoncés, et confirment la récupération des processus avant suppression des espaces. Les douze noms sous `/run/netns` et `/var/run/netns`, ainsi que les quatre réservations sous `/tmp`, ne sont plus visibles depuis l'environnement de développement :

| Contrôle | Noms `cg-JETON-c/g/s` et réservation `/tmp/coopace-guard.JETON` |
| --- | --- |
| `check` | Jeton `0eh9vdca` |
| `check-crash` | Jeton `ikzpo3qn` |
| `check-queue` | Jeton `mgo4wyt4` |
| `check-queue-crash` | Jeton `4k700w0e` |

La récupération est attestée par le superviseur ; aucun PID recherché après coup n'est utilisé comme preuve d'identité. L'absence des noms ne prouve pas l'absence de références détenues par un processus étranger. La destruction du superviseur, les descendants sortant de son groupe, la panne de l'hôte et la restauration d'une passerelle réelle ne sont pas validés. Les erreurs de création/relecture restent testées avec des outils simulés.

## Suite

Préparer le rapport du récepteur et les statistiques de file avant la campagne du [goulot virtuel](VIRTUAL_BOTTLENECK.md). L'intégration à la topologie active et ses contrôles de passage précéderont les séries avec file, puis la référence CAKE manuelle. Les modes de `lab-network.sh` restent sans intégration à ce superviseur. L'étape 4.2 reste ouverte.
