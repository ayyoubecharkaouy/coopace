# Passage IPv4 après Go validé en natif — 1er novembre 2026 (UTC)

## Résultat et portée

Les deux contrôles du [protocole natif de passage](LAB_CAKE_GO_PATH_NATIVE.md) ont réussi au commit `6d5ccd060188f499b0e4c103418d4c6167dadcf0`. Les codes `check`, `check-crash` et relecture sont `0`. Une seconde revue indépendante confirme les pièces, sans relancer de commande réseau ni modifier le certificat existant.

| Observation | `check` | `check-crash` |
| --- | --- | --- |
| Phase Go | Code 0, 14 appels, 36 lignes durables | Code 0, 14 appels, 36 lignes durables |
| Six commandes de passage | Récupérées, preuves cohérentes | Récupérées, preuves cohérentes |
| Forwarding relu à 0 | Une requête, zéro réponse, code ping 1 | Une requête, zéro réponse, code ping 1 |
| Forwarding relu à 1 | Trois requêtes, trois réponses, code ping 0 | Trois requêtes, trois réponses, code ping 0 |
| Code OS du pilote TCP | 0 | -9, SIGKILL attendu |
| Outils orphelins récupérés | 0 | 3 |
| Réception applicative | 8 388 608 octets | Aucun rapport final de flux attendu |
| Connexions TCP de mesure | 10 réussites, aucun échec | Aucune mesure finale attendue |
| Relevés de file pendant la collecte TCP | 66 | 3 |
| Nettoyage | Confirmé | Confirmé |

Le résultat valide l’ordre Go DOWN → activation des mêmes ressources → blocage/passage IPv4 → trafic TCP supervisé. Le passage est accepté avant toute intention de lancement du pilote TCP. Go termine normalement avant activation dans les deux modes ; la panne concerne ensuite le seul pilote de trafic.

Le [premier essai refusé au commit afa0b22](REVIEW_CAKE_GO_PATH_FAILURE_2026-11-01.md) reste conservé. Les sondes corrigées utilisent `-c 1` puis `-c 3` avec `-W 1`, sans `-w`. Le contrôle strict d’un puis trois envois est désormais satisfait, sans réinterpréter l’ancien échec.

## Continuité et relevés

Le profil reste `cake-ipv4-lab-4mbit-v1`, CAKE racine `10:` sur `wan`, producteur iproute2-6.1.0/libbpf 1.3.0, bande passante nominale de 500 000 octets/s. Le lien et sa file sont conservés après l’unique ajout Go. Les identités des liens intermédiaires, les sorties brutes et les relectures finales concordent ; les compteurs restent monotones.

Les commandes de passage prennent au total, récupération et vérifications après sortie comprises :

| Commandes | `check` | `check-crash` |
| --- | --- | --- |
| Sonde négative | 1 117,257 ms | 1 116,045 ms |
| Sonde positive | 2 181,865 ms | 2 183,581 ms |
| Écritures/relectures sysctl | 113,931–121,555 ms | 113,399–119,996 ms |

Ces durées restent sous les bornes conservatrices de 4/6 s et 2 s. Le `time 0ms` du résumé négatif ne décrit pas la durée du processus : la revue conserve séparément la durée monotone du superviseur. Les douze résultats de commande conservent stdout/stderr complets, sans troncature, et tous les processus de commande sont récupérés.

| Différences de compteurs racine | `check` | `check-crash` |
| --- | --- | --- |
| Passage : octets / paquets | 656 / 8 | 832 / 10 |
| Passage : drops / overlimits / requeues | 0 / 6 / 0 | 0 / 4 / 0 |
| Trafic TCP : octets / paquets | 8 774 074 / 5 839 | 120 790 / 83 |
| Trafic TCP : drops / overlimits / requeues | 152 / 15 538 / 0 | 4 / 225 / 0 |

La différence d’activation reste distincte et figée à 90 octets/un paquet dans les deux modes. La différence TCP commence après les sondes ICMP, juste avant le pilote. Ces compteurs peuvent inclure du trafic automatique local et ne sont ni le volume utile reçu, ni une mesure de perte TCP.

En mode normal, les dix établissements TCP sont entièrement recouverts par les écritures applicatives, après stabilisation. Les durées descriptives sont min 1,132678 ms, p50 1,372385 ms, p95/p99/max 1,960235 ms. Dix essais sans comparaison ne prouvent aucun gain de latence. Les 66 relevés comprennent un initial, 61 pendant l’exécution, trois pendant le vidage et un après arrêt ; le double relevé vide espacé d’au moins 500 ms est confirmé. La limite d’observation du point de départ interne du vidage reste celle du protocole.

Le mode panne a déjà généré du trafic avant la mort du pilote : ses compteurs positifs restent visibles malgré `flow: null`. Les trois outils sont récupérés avant retrait des espaces. Les relevés finaux des deux modes ont backlog et nombre de paquets en attente nuls.

## Nettoyage et provenance

| Contrôle | Réservation supprimée | Espaces supprimés |
| --- | --- | --- |
| `check` | `/tmp/coopace-guard.y9c7_zfk` | `cg-y9c7_zfk-c/g/s` |
| `check-crash` | `/tmp/coopace-guard.v9r41195` | `cg-v9r41195-c/g/s` |

Les six noms sont absents sous `/run/netns` et `/var/run/netns`, les deux réservations et les 50 PID consignés sont absents lors de la seconde revue. La cible Go porte device 5, inode 4026532716 dans les deux sessions successives ; sa réutilisation après nettoyage n’invalide pas la continuité vérifiée dans chaque session.

Dossier : `.local/experiments/go-path-native-validation-6d5ccd0/`. Début du lanceur : `2026-11-01T22:08:59.181215+00:00`. Première relecture : `2026-11-01T22:09:46.375260+00:00`. Les 313 entrées figées et les sources du commit sont conformes, ainsi que les 46 pièces consignées dans le certificat.

Les quatre binaires indiquent Go 1.27.3, Linux amd64, le commit préparé et `vcs.modified=false`. L’exécution utilise Linux `7.0.0-38-generic` et Python 3.12.3. Le producteur ping et son empreinte correspondent à la préparation.

| Pièce | SHA-256 |
| --- | --- |
| `check/report.json` | `5ada3818d9bccb30614fe80b6b9114f7c302cce1fbf5ccd763e8dd0185dbee06` |
| `check-crash/report.json` | `273019d946f75faeb839b08925b376f20bfe940d3684065119fb0c7cc80c16c3` |
| `validation.json` | `5ee0a613b62a98ac371c05069605f16e1a8f5f3eb3ed341a91819f6b8adac828` |

Les pièces restent inchangées. `prepared.json` conserve son état historique `not_run` ; `validation.json` porte `native_cake_go_path_validated`. Après mise à jour des documents courants, la vérification complète du manifeste exige de restituer les fichiers suivis du commit source à leurs chemins préparés, sans modifier les preuves.

## Suite et limites

La prochaine sous-étape définit une campagne répétée de l’intégration Go et ses critères avant collecte. Ce contrôle unique ne démontre ni gain propre à Coopace, comparaison de politiques, équité, coût système ou capacité Internet. IPv6/DNS, couverture du foyer, restauration réelle, destruction du superviseur et mort de Go pendant un outil actif restent hors de cette validation. L’étape 4.2 demeure ouverte.
