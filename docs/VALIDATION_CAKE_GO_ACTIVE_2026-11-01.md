# Premier contrôle natif CAKE Go puis trafic — 1er novembre 2026 (UTC)

## Résultat et portée

Les deux contrôles du [protocole natif combiné](LAB_CAKE_GO_ACTIVE_NATIVE.md) ont réussi au commit `0af91030276b921f0bdad12901196faf8ffcc826`. La relecture du lanceur puis une seconde relecture indépendante ont confirmé les preuves sans relancer de commande réseau. Les codes `check`, `check-crash` et relecture sont tous `0`.

| Observation | `check` | `check-crash` |
| --- | --- | --- |
| Code du processus Go | 0 | 0 |
| Appels d’outils / lignes du journal Go | 14 / 36 | 14 / 36 |
| Code OS du pilote de trafic | 0 | -9, SIGKILL attendu |
| Outils orphelins récupérés | 0 | 3 |
| Réception complète | 8 388 608 octets | Aucun rapport final de flux attendu |
| Établissements TCP | 10 réussites, aucun échec | Aucune mesure finale attendue |
| Échantillons CAKE | 64 | 3 |
| Nettoyage des deux groupes et espaces | Confirmé | Confirmé |

Cette preuve valide l’enchaînement Go DOWN → activation des mêmes ressources → trafic supervisé dans le laboratoire IPv4 jetable. Go termine normalement avant l’activation dans les deux contrôles. Le mode panne tue le pilote de trafic pendant l’attente de l’accusé ; il ne teste pas la mort de Go pendant un appel d’outil.

## Continuité et mesures

Les trames `ready`/`applied` et les journaux Go concordent avec les outils et la référence `cake-ipv4-lab-4mbit-v1`. Go ajoute CAKE une seule fois sur `wan` DOWN ; les quinze changements d’activation conservent son identité et sa configuration, sans réinstaller la file. Les adresses IPv4, routes spécifiques, interfaces et forwarding sont relus avant le trafic et après arrêt.

CAKE est relu avec iproute2-6.1.0, libbpf 1.3.0, racine `10:`, bande passante nominale de 500 000 octets/s (4 Mbit/s), `besteffort` et isolation `flows`. La différence d’activation reste distincte de celle du trafic.

| Différence des compteurs pendant le trafic | `check` | `check-crash` |
| --- | --- | --- |
| Octets | 8 774 436 | 121 058 |
| Paquets | 5 844 | 87 |
| Drops de la file | 143 | 4 |
| Overlimits | 15 554 | 236 |
| Requeues | 0 | 0 |

Les compteurs restent monotones. Ils décrivent la file, sans équivalence directe avec le volume applicatif ni avec un taux de perte TCP. Le transfert normal reçoit intégralement ses 8 Mio malgré les drops consignés. Le contrôle de panne a déjà généré du trafic avant l’accusé ; `flow: null` signifie absence de rapport final, pas absence de trafic.

Les dix connexions réussies sont entièrement comprises dans la fenêtre d’écritures applicatives, après la stabilisation prévue. Leurs durées sont descriptives : min 0,744064 ms, p50 1,375930 ms, p95/p99/max 1,737667 ms. Avec dix essais et sans série comparative, elles ne démontrent aucun gain de latence. Le débit moyen de réception est de 478 075,708 octets/s sur la durée entre première et dernière lecture ; il ne mesure pas la capacité Internet.

Le contrôle normal conserve 59 relevés pendant l’exécution, trois pendant le vidage, puis un relevé après arrêt, en plus du relevé initial. La relecture confirme le double relevé vide espacé d’au moins 500 ms. La borne de trois secondes reste imposée par l’exécuteur figé ; l’instant interne de détection de sortie n’étant pas journalisé séparément, cette borne n’est pas intégralement recalculée hors ligne.

## Nettoyage

| Contrôle | Réservation retirée | Espaces retirés |
| --- | --- | --- |
| `check` | `/tmp/coopace-guard.tzqp6s6o` | `cg-tzqp6s6o-c/g/s` |
| `check-crash` | `/tmp/coopace-guard.dwq3ab1a` | `cg-dwq3ab1a-c/g/s` |

Les six noms sont absents sous `/run/netns` et `/var/run/netns`, les deux réservations sont absentes et les 38 PID consignés ne sont plus présents au moment de la seconde revue. La cible réseau Go porte device 5, inode 4026532719 dans les deux contrôles successifs : le noyau peut réutiliser un inode après nettoyage. La continuité est vérifiée au sein de chaque session, avec des noms et jetons distincts.

Les trois outils laissés par le pilote tué sont récupérés avant suppression des espaces. La destruction du superviseur, une panne de l’hôte et la restauration d’une passerelle existante restent hors de cette validation.

## Provenance et conservation

Dossier local : `.local/experiments/go-active-native-validation-0af9103/`. Début du lanceur : `2026-11-01T17:46:13.051714+00:00`. Première relecture : `2026-11-01T17:46:48.746182+00:00`.

Les 295 entrées figées et les sources du commit ont été revérifiées. Les quatre binaires indiquent Go 1.27.3, Linux amd64, la révision préparée et `vcs.modified=false`. L’exécution utilise Linux `7.0.0-38-generic` et Python 3.12.3. Les 44 pièces consignées dans `validation.json` sont conformes ; la seconde relecture conserve ce certificat et les résultats existants.

| Pièce | SHA-256 |
| --- | --- |
| `check/report.json` | `280eab7df03d17ad08427279cb21a3a86c10e3b28fd8548f241c6220e7ee2359` |
| `check-crash/report.json` | `9751d7b30eb71dbc704dba77863e6d69bb51890d54278abdf675d4625257e6de` |
| `validation.json` | `5799b7509ef768d4d1ee5f4fa75f1ac16fa6fc7ab93390af16b45a6c31d095cd` |

Les données et copies de protocoles figées restent inchangées. `prepared.json` conserve son état historique `not_run` ; `validation.json` porte `native_cake_go_active_validated`. Après mise à jour des documents courants, la vérification complète des entrées demande de restituer les fichiers suivis du commit source à leurs chemins préparés, sans réécrire les manifestes ni les preuves.

## Suite et limites

L’étape 4.2 reste ouverte : ce contrôle ne compare pas de politiques, n’évalue ni bénéfice propre à Coopace, équité, coût système, IPv6/DNS, couverture du foyer ou restauration réelle. La prochaine sous-étape doit définir les contrôles négatifs du chemin IPv4 avant une éventuelle campagne comparée de l’intégration Go. Aucun contrôleur Go permanent ni application sur un chemin déjà actif n’est validé ici.
