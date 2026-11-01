# Échec du premier essai natif de passage IPv4 — 1er novembre 2026 (UTC)

## Résultat conservé

Le lancement au commit `afa0b22bd14d859f60c6079413ec8414b6b3d5b9` s’est arrêté sur `check` avec le code `1`. Dossier : `.local/experiments/go-path-native-validation-afa0b22/`. Aucun `check-crash` ni relecture de succès n’a été exécuté ; aucun certificat natif n’est publié.

Les 312 entrées figées correspondent au manifeste et au commit au moment de l’analyse. La phase Go a terminé avec `0`, 14 appels et 36 lignes durables. L’activation puis la désactivation du forwarding ont réussi ; la relecture a confirmé exactement `0`.

La sonde négative a été lancée avec :

```text
ping -4 -n -c 1 -w 3 -W 1 10.203.0.6
```

Sa capture réelle, code OS `1`, sans stderr ni troncature, contient :

```text
PING 10.203.0.6 (10.203.0.6) 56(84) bytes of data.

--- 10.203.0.6 ping statistics ---
3 packets transmitted, 0 received, 100% packet loss, time 2036ms
```

La durée totale consignée est de 3 120 166 134 ns, dans la borne externe de 4 s. Le refus provient du nombre d’envois : trois au lieu d’un. L’absence de réponse est observée, mais le protocole complet de passage n’est pas validé. La réactivation, la sonde positive et le pilote TCP n’ont pas été lancés.

## Cause et correction

L’association de `-c` et `-w` avait été mal interprétée lors de la définition des commandes. Avec une échéance `-w`, iputils peut continuer d’émettre en attendant le nombre de réponses demandé ; `-c 1` ne garantit alors pas un seul envoi. Le [manuel de ping](https://man7.org/linux/man-pages/man8/ping.8.html) décrit cette interaction dans les options `-c` et `-w`.

La correction retire `-w` des deux sondes. Les comptes restent stricts : `-c 1` sans réponse, puis `-c 3` avec trois réponses. `-W 1` reste présent, ainsi que les échéances externes de 4 s et 6 s imposées par le superviseur. Aucun critère n’est assoupli pour accepter la capture défaillante.

L’exécuteur et le relecteur indépendant sont corrigés ensemble. La capture native est reprise dans un test de régression, et le réseau simulé reproduit désormais les envois supplémentaires de la sonde négative si `-w` est réintroduit. Les anciens tests ne modélisaient pas cette particularité d’iputils.

## Nettoyage et conservation

Les trois commandes lancées sont récupérées. Le rapport indique `cleanup_verified: true`, et stderr confirme le retrait du laboratoire. Un seul laboratoire a été créé, avec `cg-ytwcxfdg-c`, `cg-ytwcxfdg-g`, `cg-ytwcxfdg-s` et la réservation `/tmp/coopace-guard.ytwcxfdg`. Ces trois noms, cette réservation et les 18 PID consignés sont absents lors de l’analyse.

Les fichiers de l’essai restent inchangés. `prepared.json` conserve son état historique `not_run` ; `check/report.json` porte `state: failed`, `path_verified: false` et l’erreur de compte ICMP. Les nouvelles sources ne doivent pas être recopiées dans cet essai ni ses manifestes réécrits.

| Pièce | SHA-256 |
| --- | --- |
| `check/report.json` | `edaa38dcc593cf456cce09650274819850775662f55324884bfbe2dadcbdfb58` |
| `check/supervisor.jsonl` | `90d19acc6794b2d77bb5078a1314e01be6b29915f444755972283cca044ecaed` |

La correction demande un nouveau commit, quatre binaires recompilés et un dossier neuf selon le [protocole natif](LAB_CAKE_GO_PATH_NATIVE.md). Les deux modes restent à exécuter et à valider. Cet échec ne permet aucune conclusion sur un gain réseau ou sur le fonctionnement du produit dans le foyer.
