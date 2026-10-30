# Première campagne native avec goulot TBF — 30 octobre 2026 (UTC)

## Résultat et portée

Le contrôle de panne et la campagne ont chacun un code de sortie **`0`**. La collecte est techniquement valide et la **congestion est observée selon les critères préalables du protocole v1** : `technical_valid: true`, `congestion: observed`. Les trois paires satisfont les critères de file alimentée, débit reçu et augmentation de p50.

Ce résultat qualifie le laboratoire synthétique IPv4 avec TBF à 4 Mbit/s. Il ne démontre aucun gain d'optimisation Coopace, aucune capacité WAN ni restauration d'une passerelle réelle. La référence CAKE manuelle reste à comparer et l'étape 4.2 reste ouverte. Voir le [protocole v1](VIRTUAL_BOTTLENECK.md) et son [implémentation](LAB_CAMPAIGN.md).

## Collecte vérifiée

Les six phases suivent idle/loaded, loaded/idle, idle/loaded sur une seule file dans la passerelle neuve. Les paramètres effectifs restent conformes dans toutes les lectures : racine `tbf`, handle `10:`, débit 500 000 octets/s, burst 65 536 et limit 131 072 octets.

Les contrôles ICMP donnent zéro réponse sans forwarding, puis trois réponses avec forwarding, dans les deux exécutions. La campagne conserve **60 tentatives TCP réussies sans échec** et **trois réceptions exactes de 8 388 608 octets**, soit 24 Mio utiles au total. Les rapports d'émission et réception, EOF, durées et débits sont conformes ; les fenêtres complètes des sondes loaded sont comprises dans les écritures de charge.

| Paire | p50 idle (ms) | p50 loaded (ms) | Écart (ms) | Lectures positives espacées dans la fenêtre loaded | Débit reçu (octets/s) |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.182849 | 207.303243 | +207.120394 | 17 | 481 521.676415 |
| 2 | 0.253220 | 203.179321 | +202.926101 | 16 | 481 494.773215 |
| 3 | 0.220909 | 204.345396 | +204.124487 | 16 | 481 522.461344 |

Les débits reçus sont recalculés depuis les 8 Mio et les durées monotones première lecture → EOF : respectivement 17 421.039199, 17 422.012588 et 17 421.010801ms. Ils se trouvent dans l'intervalle déclaré de 350 000 à 525 000 octets/s. Ils décrivent les données livrées à l'application, distinctes des octets comptés par tc.

La stabilisation avant les sondes vaut respectivement 1 025.793553, 1 027.180364 et 1 027.780628ms. Les lectures positives sont espacées d'au moins 200ms et les compteurs d'octets progressent dans chacune des trois fenêtres loaded. Les écarts de p50 dépassent 10ms dans trois paires, contre deux exigées. Les statistiques ont été recalculées à partir des tentatives ; aucun percentile de paire n'est moyenné. Avec dix réussites par phase, p95/p99 restent des observations exploratoires.

La décision a été reproduite avec le module livré, puis les critères de débit, latence et occupation de file ont été vérifiés directement sur les données. Les trois comparaisons de la vraie CLI `latency compare` ont été relancées hors ligne sur les fichiers conservés : leurs sorties correspondent exactement aux comparaisons du rapport et du journal. Aucun trafic n'a été relancé pendant la revue.

## Statistiques, continuité et vidage

La campagne conserve 255 lectures dans ses phases : 14 par phase idle et 71 par phase loaded. Le journal contient 277 événements ; ses lectures correspondent exactement à celles du rapport. Les objets JSON de tc ont été revalidés et leurs normalisations recalculées.

Les pauses entre lectures périodiques vont de 251.779259 à 259.172470ms ; les commandes de statistiques de campagne durent de 10.719763 à 19.887728ms. Les contrôles de vidage après les six phases donnent des lectures nulles espacées de 522.691939 à 524.943771ms. Aucune baisse de compteur n'est observée, y compris entre phases.

| Compteur | Différence après contrôles de passage → après fin du pilote |
| --- | --- |
| `bytes` | 26 336 742 |
| `packets` | 17 685 |
| `drops` | 67 |
| `overlimits` | 8 817 |
| `requeues` | 0 |

Ces compteurs décrivent la file, pas seulement la charge utile ; les drops ne constituent pas un taux de perte de bout en bout. Aucune différence de jauge ni estimation de débit par soustraction des compteurs n'est utilisée.

Les lectures de configuration/statistiques de campagne vont de `2026-10-30T11:14:19.009722+00:00` à `11:15:27.347483+00:00`. Les paramètres et critères sont ceux figés avant cette collecte ; aucun seuil n'a été modifié après observation.

## Contrôle de panne et nettoyage

Le contrôle `check-crash` termine une phase idle de dix connexions, puis impose SIGKILL au pilote après la première écriture du premier transfert loaded. Le pilote sort avec `-9` et **trois outils orphelins sont récupérés**. Le rapport conserve la phase terminée et les relevés de la phase interrompue ; la congestion n'y est pas évaluée. Les annulations et les 49 152 octets partiellement envoyés/reçus sont attendus dans ce contrôle. Sa dernière lecture précède l'arrêt des outils.

La campagne normale a une sortie de pilote `0`, sans descendant orphelin à récupérer. Les deux rapports et journaux confirment la suppression des ressources après arrêt des processus. Les six noms `cg-693cy6qa-c/g/s` et `cg-i7h9ozd6-c/g/s`, ainsi que les réservations `/tmp/coopace-guard.693cy6qa` et `/tmp/coopace-guard.i7h9ozd6`, sont absents depuis l'environnement de développement. Les quatorze PID consignés ne sont plus présents sous `/proc` au moment de la revue.

Ces vérifications portent sur les noms sous `/run/netns`, `/var/run/netns`, les réservations et les PID enregistrés. Elles ne prouvent pas l'absence de références détenues par un processus étranger. La destruction du superviseur lui-même et la restauration d'une passerelle existante restent hors validation.

## Provenance et suite

Commit source : `61618036db2c2de8fe842e37f0db49ad48ab1374`. Dossier local : `.local/experiments/bottleneck-validation-6161803/`, préparé le `2026-10-30T11:10:51.411500+00:00`. Les 124 empreintes d'entrée ont été vérifiées ; les sources suivies correspondent au commit et les trois binaires Linux amd64/Go 1.27.3 déclarent ce commit avec `vcs.modified=false`.

| Pièce | SHA-256 |
| --- | --- |
| `campaign.json` | `99f4432b12c68bcffca7328fa96351d0ed2137414c5edf3018e0b283045bc1c5` |
| `check-crash.json` | `6613a1b493abf0ffd198234be00a18340e868343c7abf8bd357793def28a3ac0` |
| `campaign/progress.jsonl` | `ecba32470348c4393e3aa48e5c3f3821ef75208c152ac3ad647f48552ed331a0` |
| `crash/progress.jsonl` | `0bffc97166ceeba43d898349a92b3c1d45a4b701c8b7473176111352222ea562` |

Les fichiers figés et les données brutes restent inchangés. `prepared.json` garde son état historique `not_run` ; un nouveau `validation.json` consigne la revue et les empreintes de vingt-neuf pièces, dont le script de revue. Les preuves intermédiaires, fichiers des phases et binaires restent locaux et exclus de Git.

La prochaine sous-étape définit la comparaison avec CAKE configuré manuellement au même débit nominal, avant toute nouvelle collecte. Son protocole, ses ordres, critères et contrôles de nettoyage devront être figés séparément. Le goulot qualifié ici fournit une référence TBF, sans clore les validations WAN, IPv6/DNS, équité et ressources du produit.
