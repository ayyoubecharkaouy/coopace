# Première campagne native CAKE — 30 octobre 2026 (UTC)

## Résultat et portée

Le contrôle de panne et la campagne ont chacun un code **`0`**. La collecte est techniquement valide et la **charge CAKE est qualifiée dans les trois paires** : `technical_valid: true`, `load_scenario: qualified`. Les octets progressent pendant chaque fenêtre de sondes loaded et les trois débits reçus appartiennent à l'intervalle fixé avant collecte.

Cette validation porte sur une campagne CAKE isolée du [laboratoire synthétique IPv4](LAB_CAKE_CAMPAIGN.md). `congestion` et `comparison` restent `not_assessed`. Les six campagnes neuves et les neuf comparaisons du [protocole TBF/CAKE v1](CAKE_COMPARISON.md) restent à réaliser ; les anciennes données TBF ne deviennent pas un bras comparatif. Aucun bénéfice comparatif CAKE, gain Coopace ou résultat WAN n'est qualifié ici. L'étape 4.2 reste ouverte.

## Phases et transferts vérifiés

Les six phases suivent idle/loaded, loaded/idle, idle/loaded, sur une seule file CAKE neuve à 4 Mbit/s. Les contrôles ICMP donnent zéro réponse sans forwarding puis trois réponses avec forwarding, dans les deux exécutions. Les rapports de campagne conservent **60 tentatives TCP réussies sans échec** et **trois réceptions exactes de 8 388 608 octets**, soit 24 Mio utiles.

| Paire | p50 idle (ms) | p50 loaded (ms) | Différence (ms) | Débit reçu (octets/s) | Lectures dans la fenêtre loaded |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.193088 | 1.377960 | +1.184872 | 478 091.343698 | 8 |
| 2 | 0.192935 | 1.391873 | +1.198938 | 478 095.696850 | 9 |
| 3 | 0.205216 | 1.396631 | +1.191415 | 478 094.299642 | 9 |

Les durées monotones première lecture → EOF sont respectivement 17 546.036151, 17 545.876391 et 17 545.927668ms. Les débits ont été recalculés à partir des volumes et de ces durées ; ils respectent l'intervalle inclusif de 350 000 à 525 000 octets/s. Les rapports complets d'émission/réception et les fenêtres d'écritures sont conformes. Les sondes loaded restent entièrement dans les écritures ; leur stabilisation vaut 1 027.420292, 1 027.317881 et 1 026.863484ms.

Les différences d'octets racine dans les trois fenêtres de sondes sont positives : 930 258, 1 066 790 et 1 066 790 octets. La qualification n'exige ni backlog durablement positif ni hausse de p50. Les statistiques TCP ont été recalculées depuis chaque tentative ; aucun percentile de paire n'est moyenné. Ces durées d'établissement TCP et leurs différences restent descriptives.

La décision a été reproduite avec le module livré et les critères de stabilisation, progression et débit ont été vérifiés directement sur les données. Les trois comparaisons de la vraie CLI `latency compare` ont été relancées hors ligne sur les fichiers conservés ; leurs sorties correspondent exactement au rapport et au journal. Aucun trafic n'a été relancé pendant la revue.

## Configuration, statistiques et vidage

Toutes les relectures sont conformes : une racine CAKE `10:` sur `wan`, 500 000 octets/s, `besteffort`, `flows`, `nonat`, `nowash`, `raw`, MPU 0, RTT 100 000µs, `split-gso`, filtre ACK désactivé, egress, mémoire 1 048 576 octets et masque nul. Le producteur identifié est iproute2-6.1.0 ; les omissions reconnues restent justifiées et distinctes des statistiques absentes.

La campagne conserve **258 échantillons** : 14 par phase idle et 72 par phase loaded. Le journal contient 543 événements, dont 263 relectures de file et les 258 échantillons de phase. Les objets JSON bruts, configurations et statistiques normalisées ont été revalidés. Les relevés correspondent exactement au rapport ; seules les étiquettes de phase sont ajoutées après l'enregistrement de la lecture CAKE.

Les commandes de statistiques durent de 10.663471 à 18.553512ms ; les pauses entre lectures périodiques vont de 250.517621 à 261.604937ms. Les six vidages sont confirmés par des lectures backlog/qlen nuls espacées de 523.336224 à 524.611102ms. Aucune baisse des cinq compteurs racine n'est observée, y compris entre phases.

| Compteur racine CAKE | Différence après passage → après fin du pilote |
| --- | --- |
| `bytes` | 26 330 452 |
| `packets` | 17 638 |
| `drops` | 452 |
| `overlimits` | 46 879 |
| `requeues` | 0 |

Ces compteurs décrivent la file, pas seulement les octets utiles ni un taux de perte de bout en bout. Les statistiques racine/classe ne sont pas additionnées. La plus grande valeur `memory_used` rapportée est 32 720 octets ; avec ce producteur elle reste un maximum historique, pas une mesure de RAM courante. `capacity_estimate` n'est pas une mesure WAN.

Les relevés après ajout de CAKE vont de `2026-10-30T13:18:56.994093+00:00` à `13:20:05.570773+00:00`. Les paramètres et seuils sont ceux figés avant cette collecte.

## Contrôle de panne et nettoyage

Le mode `check-crash` termine une phase idle de dix connexions puis tue le pilote après la première écriture du premier transfert loaded. Sa sortie est `-9` ; **trois outils orphelins sont récupérés**. Le rapport conserve la phase terminée et la phase interrompue, avec qualification `not_assessed`. Son journal contient 44 événements, dont 21 relectures CAKE et 16 échantillons de phase. Les annulations et les volumes partiels de stderr — 65 536 octets écrits et 7 240 reçus — sont attendus ; la dernière lecture précède l'arrêt des outils.

La campagne normale termine avec un pilote à `0`, sans descendant orphelin à récupérer. Les deux rapports ont `cleanup_verified: true` et les journaux confirment le nettoyage après arrêt des processus. Les six noms `cg-7bchzp74-c/g/s` et `cg-04c5yuip-c/g/s` sont absents sous `/run/netns` et `/var/run/netns`. Les réservations `/tmp/coopace-guard.7bchzp74` et `/tmp/coopace-guard.04c5yuip`, ainsi que les quatorze PID consignés sous `/proc`, sont absents au moment de la revue.

Ces observations depuis l'environnement de développement complètent l'attestation du superviseur. Elles ne prouvent pas l'absence de références détenues par un processus étranger. La destruction du superviseur et la restauration d'une passerelle existante restent hors validation.

## Provenance et suite

Commit source : `751a1cde82f89abad581b2f47c072a16bf103510`. Dossier local : `.local/experiments/cake-campaign-validation-751a1cd/`. Les **147 empreintes d'entrée** sont conformes, dont celles des outils système ; les sources suivies correspondent au commit. Les trois binaires Linux amd64/Go 1.27.3 déclarent ce commit avec `vcs.modified=false`. Le lancement consigne Linux `7.0.0-38-generic` et Python 3.12.3.

| Pièce | SHA-256 |
| --- | --- |
| `campaign.json` | `f1069d0e6c21a524b0216aaf61f5c2d48051b177caa4be72452d995726aa18af` |
| `check-crash.json` | `7e1d26221bbfdab5c60b526403fba3b32d9c49186a88e33bcc009a1ca116241e` |
| `campaign/progress.jsonl` | `d8492ed1e14bd48e23b1bdaad9f88d8ab4f8920525f81c0488914c2e8d454583` |
| `crash/progress.jsonl` | `204de44a66a2164036b8853028081ea30f9d24f1804c8f61ddfc86f7a593e152` |

Les données et protocoles figés restent inchangés. `prepared.json` conserve son état historique `not_run` ; le nouveau `validation.json` consigne la revue et les empreintes de trente-six pièces, dont le script de revue. Les preuves intermédiaires, fichiers des phases et binaires restent locaux et exclus de Git.

La prochaine sous-étape développe l'orchestration des six campagnes TBF/CAKE neuves et l'agrégateur des neuf comparaisons, avec les ordres et critères v1 inchangés. Les références du foyer, la restauration réelle et les autres validations du produit restent ouvertes.
