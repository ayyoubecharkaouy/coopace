# Premier contrôle natif du cycle de vie CAKE — 30 octobre 2026 (UTC)

## Résultat et portée

Les **quatre contrôles natifs ont un code `0`** : deux revérifications TBF après extraction de la préparation commune du veth, puis deux contrôles CAKE, en fin normale et après mort forcée du pilote. Les fichiers ont été revalidés hors ligne ; aucun contrôle réseau n'a été relancé pendant la revue.

Ce résultat confirme la disponibilité de CAKE dans le noyau utilisé, ses options/statistiques sur un lien neuf DOWN et le nettoyage supervisé. Aucun transfert, adresse, route ou forwarding n'est ajouté. Le débit réel, la latence, l'isolation des flux et le bénéfice CAKE ne sont pas mesurés. Le [chemin actif CAKE](LAB_CAKE.md) reste à préparer avant la [comparaison TBF/CAKE](CAKE_COMPARISON.md).

| Contrôle | File | Sortie du pilote | Descendants récupérés | Code du contrôle |
| --- | --- | --- | --- | --- |
| `tbf-check` | TBF `10:` | 0 | 1 | 0 |
| `tbf-check-crash` | TBF `10:` | -9, SIGKILL attendu | 1 | 0 |
| `cake-check` | CAKE `10:` | 0 | 1 | 0 |
| `cake-check-crash` | CAKE `10:` | -9, SIGKILL attendu | 1 | 0 |

## Options et statistiques effectivement relues

Les quatre états initiaux sont des listes vides, conformes aux liens neufs désactivés. Les racines ont été relues après ajout puis après fin du pilote, soit quatre lectures TBF et quatre lectures CAKE. Les paramètres TBF restent débit 500 000 octets/s, burst 65 536 et limit 131 072 octets.

| Paramètre CAKE | Valeur dans les quatre lectures natives |
| --- | --- |
| Racine/interface | Une CAKE `10:` sur `wan` |
| Bande passante | 500 000 octets/s, correspondant à `4mbit` |
| Classe/isolation | `besteffort`, `flows` ; une seule entrée `tins` |
| Direction et options | `ingress: false`, `nat: false`, `wash: false`, `split_gso: true`, `ack-filter: disabled` |
| Compensation | `raw: true`, `overhead: 0` |
| RTT de réglage | 100 000µs ; aucun délai injecté |
| Mémoire | `memlimit` et `memory_limit` à 1 048 576 octets ; `memory_used` à zéro |
| Masque | `fwmark` est la chaîne JSON `"0"` |

Le producteur identifié est `/usr/sbin/tc`, iproute2-6.1.0 avec libbpf 1.3.0. `mpu`, `atm` et `autorate` sont absents des objets bruts ; leurs significations sont conservées avec les justifications du profil, sans fabriquer de statistique manquante.

Les cinq compteurs racine `bytes`, `packets`, `drops`, `overlimits`, `requeues`, ainsi que les jauges `backlog` et `qlen`, sont présents et nuls dans les huit lectures. Les quatre différences de compteurs sont disponibles et nulles. Les normalisations et différences ont été recalculées avec les modules livrés.

Les vingt champs de classe connus du module CAKE sont présents dans les quatre lectures. Les compteurs de trafic sont nuls ; certains paramètres restent non nuls : `threshold_rate: 500000`, `target_us: 5000`, `interval_us: 100000`, `flow_quantum: 300`. Ces paramètres et `capacity_estimate: 500000` ne deviennent pas une mesure de débit utile ou de capacité WAN. Les compteurs de la classe ne sont pas ajoutés à ceux de la racine.

Les lectures CAKE vont de `2026-10-30T11:58:59.569693+00:00` à `11:58:59.653448+00:00` en mode normal, puis de `11:59:00.071852+00:00` à `11:59:00.155087+00:00` en mode crash. Leurs durées de commande vont de 10.908097 à 10.964243ms. Ce contrôle à deux relevés par exécution ne valide pas une collecte périodique sous trafic.

## Nettoyage vérifié

Les quatre rapports indiquent `cleanup_verified: true`, `traffic_generated: false`, `link_state: DOWN` et un descendant récupéré. Les journaux concordent avec les PID et réservations ; la mort forcée concerne le pilote de contrôle sans trafic, pas encore un pilote de transfert CAKE.

| Contrôle | Jeton des noms `cg-JETON-c/g/s` et réservation `/tmp/coopace-guard.JETON` |
| --- | --- |
| `tbf-check` | `bpeatqlp` |
| `tbf-check-crash` | `fnzq0dp7` |
| `cake-check` | `fjbrzjtu` |
| `cake-check-crash` | `uniar71b` |

Les douze noms sont absents sous `/run/netns` et `/var/run/netns` ; les quatre réservations sont absentes et les huit PID consignés ne sont plus présents sous `/proc` au moment de la revue. Ces observations complètent l'attestation du superviseur, sans prouver l'absence de références détenues par un processus étranger. La destruction du superviseur, la panne de l'hôte et la restauration d'une passerelle existante restent hors validation.

## Provenance et suite

Commit source : `326e9f73dfbf9346299966a8f4c3afe779e372fe`. Dossier local : `.local/experiments/cake-validation-326e9f7/`, préparé le `2026-10-30T11:58:04.298815+00:00`. Les 25 empreintes d'entrée, dont ip et tc, sont conformes ; les sources suivies correspondent au commit. Le lancement consigne Linux `7.0.0-38-generic` et Python 3.12.3 ; aucun binaire Go n'est requis.

| Rapport | SHA-256 |
| --- | --- |
| `tbf-check.json` | `51c843d6e7ca7d5c6141a8910f71a5f44677a5ef771f5628c3f98ec777cd8949` |
| `tbf-check-crash.json` | `43cde4bff1b5cfdd6f5149d3af075729c62f017b0b342b660a932f386677f0fa` |
| `cake-check.json` | `d29e537d3eb301b3644bf38d09cc655ad59987c5430140adcd473cb22ff2319d` |
| `cake-check-crash.json` | `0e70c8479d166215a89cd000a2622d5d45ef43cde5e5050bddcc3d288ff099ad` |

Les fichiers figés et données brutes restent inchangés. `prepared.json` conserve son état historique `not_run`. Le nouveau `validation.json` consigne la revue et les empreintes de vingt-quatre pièces, dont le script de revue ; ces preuves restent locales et exclues de Git.

La prochaine sous-étape raccordera CAKE à la topologie active avec un transfert borné, sondes, statistiques et nettoyage après mort forcée du pilote de trafic. Les six campagnes comparatives restent ensuite à développer et réaliser ; aucun bénéfice d'optimisation n'est encore attribué à CAKE ou Coopace et l'étape 4.2 reste ouverte.
