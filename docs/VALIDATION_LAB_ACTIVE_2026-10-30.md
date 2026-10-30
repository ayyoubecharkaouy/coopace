# Première validation native du chemin actif TBF — 30 octobre 2026 (UTC)

## Résultat et portée

Les deux contrôles du [chemin actif](LAB_ACTIVE.md) ont réussi sur le PC Linux utilisateur : **un transfert complet sous TBF avec sondes et statistiques périodiques, puis récupération des outils après mort forcée du pilote**. Les codes de `check` et `check-crash` sont `0` ; les ressources possédées ont été retirées dans les deux cas.

Le lanceur a ensuite refusé un nouveau lancement parce que ces résultats existaient déjà. Ce refus protège l'essai enregistré ; il ne signale pas un échec des contrôles. Aucun résultat n'a été écrasé et aucun nouveau transfert n'a été lancé pendant la revue.

Il s'agit d'un contrôle fonctionnel avec un seul transfert. Aucune phase idle ni campagne de trois paires n'a été exécutée. Le champ `congestion` reste `not_assessed` : la qualification du [protocole de goulot](VIRTUAL_BOTTLENECK.md), la référence CAKE et l'étape 4.2 restent ouvertes.

## Transfert et sondes effectivement mesurés

Le chemin relie client, passerelle et serveur dans trois espaces neufs, avec forwarding IPv4 relu et TBF sur la sortie virtuelle `wan`. Les paramètres effectifs sont conformes après ajout, après activation et après fin du pilote : racine `tbf`, handle `10:`, débit 500 000 octets/s, burst 65 536 et limit 131 072 octets. L'état initial était une liste vide sur le lien neuf DOWN.

| Élément | Observation native |
| --- | --- |
| Plateforme des trois outils | Linux amd64, Go 1.27.3 |
| Volume demandé, écrit et reçu | 8 388 608 octets ; réception complète et EOF requis avant publication |
| Durée monotone d'émission | 16 494.076665ms |
| Fenêtre monotone première lecture → EOF | 17 422.101813ms |
| Débit utile applicatif reçu | 481 492.307302 octets/s, recalculé depuis volume et durée de réception |
| Sondes TCP | 10 réussites, aucun échec ; timeout 1s, pause 250ms |
| Durées d'établissement TCP | Minimum 186.110056ms ; p50 204.376955ms ; maximum/p95/p99 255.624600ms |
| Stabilisation avant les sondes | 1 027.645859ms après la première écriture |
| Recouvrement | Fenêtre complète des sondes comprise entre première et dernière écritures de charge |

L'émission commence à `2026-10-30T10:35:28.230378026Z` ; la réception se termine à `10:35:45.652706260Z`. Les sondes vont de `10:35:29.258273809Z` à `10:35:33.674767525Z`. Les rapports complets ont été revalidés avec le module livré et les statistiques de latence ont été recalculées à partir des dix tentatives.

Le débit reçu et les durées de connexion décrivent ce flux synthétique IPv4. Ils ne fournissent aucune différence idle/loaded, capacité WAN ou amélioration attribuable à Coopace.

## File et cadence de collecte

Le contrôle normal conserve 72 objets dans `queue_samples` : une lecture avant pilote, 68 pendant son exécution et trois pendant le vidage. Les relectures après ajout, après activation et après fin du pilote sont conservées séparément dans `queue`.

La pause observée entre fin d'une lecture périodique et début de la suivante va de 251.617065 à 259.988275ms. Les commandes de statistiques du contrôle normal durent de 10.673862 à 21.775586ms. Il ne s'agit pas d'une cadence exacte à 4 Hz.

Seize lectures se trouvent dans la fenêtre des sondes et toutes montrent un backlog strictement positif. Le backlog maximal observé sur le contrôle est de 130 684 octets. Le vidage est confirmé par des lectures nulles espacées de 522.539185ms. Ces observations confirment une file alimentée pendant ce contrôle, sans satisfaire à elles seules la qualification répétée de congestion.

| Compteur | Différence avant pilote → après sa fin, contrôle normal |
| --- | --- |
| `bytes` | 8 776 646 |
| `packets` | 5 863 |
| `drops` | 14 |
| `overlimits` | 2 758 |
| `requeues` | 0 |

Les valeurs normalisées correspondent aux objets JSON de tc ; aucune baisse de compteur n'a été observée entre lectures. La différence a été recalculée. Elle couvre le trafic compté par la file, distinct des octets utiles reçus. Les 14 drops ne deviennent pas un taux de perte de bout en bout ; aucune différence de jauge n'est calculée.

## Mort forcée et nettoyage

`check` a une sortie de pilote `0` et aucun descendant orphelin à récupérer. `check-crash` a une sortie de pilote `-9` et **trois descendants récupérés**. Il conserve quatre lectures dans `queue_samples`, mais aucun rapport de flux complet : `flow` vaut `null`.

Les messages d'annulation et la réception partielle de 49 152 octets dans le journal crash sont attendus après l'arrêt imposé. Ils ne contredisent pas le code `0` du contrôle de récupération. La dernière lecture de file de ce mode précède l'arrêt des outils et ne représente pas un état après arrêt du trafic.

Les journaux confirment l'arrêt des processus avant suppression des espaces. Les six noms `cg-6q4uiqki-c/g/s`, `cg-8w9vb67h-c/g/s` sont absents sous `/run/netns` et `/var/run/netns`. Les réservations `/tmp/coopace-guard.6q4uiqki` et `/tmp/coopace-guard.8w9vb67h` sont absentes ; les huit PID consignés ne sont plus présents sous `/proc` au moment de la revue. Ces observations ne prouvent pas l'absence de références détenues par un processus étranger ni la restauration d'une passerelle réelle.

## Provenance et suite

Commit source : `218975a9995140ce5f6a9283d09500d269bbb10c`. Dossier local : `.local/experiments/active-validation-218975a/`, préparé le `2026-10-30T10:34:08.904834+00:00`. Les 112 empreintes d'entrée correspondent à la préparation ; les sources suivies correspondent au commit. Les trois binaires figés déclarent ce commit et `vcs.modified=false`.

| Rapport | SHA-256 |
| --- | --- |
| `check.json` | `fc94b31de792d946167797d44119df6cca3bbc39880a88758a89c9289fe9306d` |
| `check-crash.json` | `88ed2caa1f94101ca5c0b8e766f6eaa1520a3b762842a26ac2f5b5920f1a5fc6` |

Les protocoles figés, binaires, lanceur, rapports, journaux et codes restent inchangés. `prepared.json` garde son état historique `not_run`. Un nouveau `validation.json` consigne la revue, les calculs et les empreintes de dix-sept pièces conservées, dont le script de revue. Ces fichiers restent locaux et exclus de Git.

La prochaine sous-étape prépare les trois paires idle/loaded sous la même file, avec les contrôles de passage et les critères déjà déclarés. Elle exigera son propre dossier avant collecte. La référence CAKE manuelle viendra après la qualification du goulot ; aucun gain Coopace n'est revendiqué ici.
