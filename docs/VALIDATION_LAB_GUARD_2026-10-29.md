# Premier contrôle natif du superviseur — 29 octobre 2026

## Résultat et portée

Les deux contrôles ont été exécutés depuis le terminal Linux utilisateur avec le lanceur préparé. **Ils ont chacun terminé avec le code `0`**, après récupération du descendant et suppression des espaces possédés.

| Contrôle | Code du contrôle | Code du pilote | Descendants récupérés |
| --- | --- | --- | --- |
| `check` — fin normale | 0 | 0 | 1 |
| `check-crash` — mort forcée | 0 | -9, SIGKILL attendu | 1 |

Le descendant ignore volontairement SIGTERM. Le superviseur envoie ensuite SIGKILL au groupe possédé et récupère ses processus avant de retirer les espaces. Le second contrôle confirme ce comportement lorsque le pilote ne peut plus exécuter son propre nettoyage.

Cet essai valide le cycle de vie ciblé du [superviseur indépendant](LAB_GUARD.md). Aucune file TBF/CAKE, adresse, route ou charge de trafic n'est configurée par ces contrôles. Il ne valide ni un goulot ni un bénéfice réseau.

## Provenance et pièces conservées

- Commit source : `b81f4c90a23bf2be8faa30e9269498ede19cc9b9`.
- Dossier local : `.local/experiments/guard-validation-b81f4c9/`.
- Préparation : `2026-10-29T21:51:12.413402+00:00`, Python 3.12.3 dans l'environnement de préparation.
- Empreinte du script : `63136d37b341ca6e88c6839e14fce3ee7714b8c6b9b1a5be0d4d5ef010330572`.

Le script correspond au commit source et toutes les empreintes des entrées correspondent à la préparation. Les deux rapports JSON, leurs journaux et les codes exacts sont conservés. Les rapports ne contiennent pas d'horodatage d'exécution ; aucune heure précise de lancement n'en est déduite.

`prepared.json`, la copie figée `protocol.md`, `plan.txt`, `inputs.sha256` et `run.sh` restent inchangés. `validation.json` consigne la revue après exécution, les contrôles et les empreintes des pièces. Ces données brutes restent locales et exclues de Git.

| Pièce | SHA-256 |
| --- | --- |
| `check.json` | `05de2e8bde48b1fa8107247694b8b848ca28a2ad1190499d03a700fabe759553` |
| `check.log` | `e04b082a0d1c1a09a8b1a8a98abbbd22b3035909d1d7e71154655746fcc71b7d` |
| `check-crash.json` | `934b88a24d6faae9ed34fe77051a51256b01e827d52f40da5e6fff207d055703` |
| `check-crash.log` | `81f67da3f1276aad9928a78c429400994b40b0fba5c3c1401698ba0187878a23` |
| `check.exit` et `check-crash.exit`, chacun | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` |

## Vérifications et nettoyage

Les deux JSON correspondent au schéma local attendu : mode, code du pilote, un descendant récupéré, `cleanup_verified: true`, `queue_applied: false` et `traffic_generated: false`. Les noms correspondent chacun au jeton de leur réservation et les journaux concordent exactement avec les PID et chemins des rapports.

Pour `check`, les noms `cg-unh7g359-c/g/s` et la réservation `/tmp/coopace-guard.unh7g359` ne sont plus visibles. Pour `check-crash`, les noms `cg-3wdosb3s-c/g/s` et `/tmp/coopace-guard.3wdosb3s` ne sont plus visibles. Les vérifications ont porté sur les chemins exacts sous `/run/netns`, `/var/run/netns` et `/tmp` disponibles depuis l'environnement de développement.

La récupération des processus est attestée par le superviseur et ses contrôles avant suppression ; la revue ne déduit pas l'identité d'un processus à partir d'un PID recherché plus tard. L'absence des noms ne prouve pas à elle seule l'absence de références détenues par un processus étranger. La destruction du superviseur, les descendants sortant de son groupe, les pannes de l'hôte et la restauration d'une passerelle réelle ne sont pas validés par cet essai.

## Suite

La prochaine sous-étape est l'intégration de ce superviseur au cycle de vie de la file virtuelle, avec prévisualisation et tests d'erreur de création/relecture. Le rapport du récepteur et les statistiques de file devront ensuite compléter l'instrumentation avant la campagne définie par le [protocole du goulot](VIRTUAL_BOTTLENECK.md).

Les modes existants de `lab-network.sh` ne sont pas encore intégrés au nouveau superviseur. L'étape 4.2 reste ouverte ; ces deux contrôles n'ajoutent aucune gestion du trafic au produit.
