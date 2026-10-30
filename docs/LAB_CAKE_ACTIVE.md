# Chemin actif CAKE — contrôle fonctionnel v1

## État et objectif

`scripts/lab-cake-active.py` et `lab_cake_active.py` raccordent maintenant CAKE à la topologie client → passerelle → serveur. Les tests utilisent des commandes réseau simulées et de vrais processus/signaux. **La première validation native est consignée** : transfert complet, dix connexions réussies, relevés et preuves conservés, nettoyage normal ou après mort forcée. Voir le [compte rendu du 30 octobre](VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md). Le [contrôle CAKE DOWN](VALIDATION_LAB_CAKE_2026-10-30.md) reste une preuve préalable distincte.

Ce contrôle porte sur un seul transfert et dix sondes. Il prépare la [comparaison TBF/CAKE](CAKE_COMPARISON.md), dont le [pilote des six campagnes et l’agrégateur](LAB_COMPARISON_RUN.md) sont implémentés et testés avec des opérations simulées, avant leur collecte native. Les anciens résultats TBF ne servent pas ici de bras comparatif ; `congestion` reste `not_assessed`. Aucun bénéfice CAKE ou Coopace n'est qualifié par ce contrôle isolé.

## Topologie et paramètres

CAKE est ajouté sur un lien neuf DOWN, puis la topologie complète est activée :

```text
client eth0         passerelle                         serveur eth0
10.203.0.2/30 -> lan 10.203.0.1/30
                   wan 10.203.0.5/30 [CAKE 10:] -> 10.203.0.6/30
```

Les deux veth sont créés directement dans les espaces possédés par le superviseur. Deux routes spécifiques relient les sous-réseaux. Le forwarding IPv4 est activé et relu dans la passerelle neuve ; le transfert TCP vérifie le passage positif. Comme dans le [contrôle actif TBF](LAB_ACTIVE.md), ce mode ne lance pas de contrôle négatif ICMP. Les contrôles ICMP sont maintenant intégrés à la [campagne CAKE](LAB_CAKE_CAMPAIGN.md), dont la [première validation native](VALIDATION_LAB_CAKE_CAMPAIGN_2026-10-30.md) est consignée. Il n'y a ni NAT, route par défaut, interface physique ou accès Internet.

Conserver exactement les options CAKE du [cycle de vie](LAB_CAKE.md) : 4 Mbit/s, `besteffort`, `flows`, `nonat`, `nowash`, `raw`, MPU 0, RTT 100ms, `split-gso`, sans filtre ACK, direction egress, mémoire 1 048 576 octets et masque nul. Identifier le profil iproute2-6.1.0 ; relire paramètres, classe et statistiques après ajout, activation, pendant les relevés et après fin du pilote. Refuser un état inattendu et ne jamais remplacer une racine étrangère.

| Paramètre | Valeur fixée |
| --- | --- |
| Transfert | 8 388 608 octets vers `10.203.0.6:46002`, plafond moyen applicatif 1 048 576 octets/s. |
| Délais | Émetteur 25s ; récepteur 28s, attente initiale incluse. |
| Sondes | Dix connexions vers `10.203.0.6:46001`, timeout 1s, pause 250ms, condition déclarée `loaded`. |
| Cible temporaire | Au plus 100 acceptations, durée 30s ; arrêt après les sondes. |
| Stabilisation | Au moins 1s après annonce de la première écriture avant lancement des sondes. |
| Statistiques | Lecture avant pilote, lectures périodiques avec pause d'au moins 250ms depuis la fin de la précédente, puis contrôle du vidage et lecture après fin du pilote. |
| Vidage normal | Backlog et qlen nuls à deux lectures espacées d'au moins 500ms, sous 3s. |
| Bornes | Disponibilité 5s par outil, sondes 16s, pilote 45s, superviseur 90s, nettoyage 10s ; commandes ip/tc/sysctl 2s. |
| Volumes de contrôle | 240 relevés/1 Mio dans les échantillons, sortie du pilote 256 Kio ; journal de preuves 4 Mio. |

La cadence des statistiques n'est pas exactement 4 Hz : garder les dates et durées réelles, sans rattrapage. Les compteurs racine sont séparés des jauges et des statistiques de classe/mémoire. Ne pas additionner racine et classe, ni interpréter `capacity_estimate` comme une mesure WAN. La signification des omissions et de la mémoire reste celle de [LAB_CAKE.md](LAB_CAKE.md).

## Réutilisation et nettoyage

`lab_active.activate` contient l'activation commune, après validation du moteur. Le module CAKE y raccorde son propre validateur ; le module TBF garde ses options et son format de rapport. Le même pilote `lab-active.py worker` exécute les outils Go dans les espaces client/serveur ; il ne configure aucune file. Le superviseur indépendant garde la possession des espaces et du groupe, sans récupérer le leader avant les derniers signaux collectifs.

`check` attend le volume complet et EOF, valide les rapports d'émission/réception et les dix tentatives, puis le vidage. Les cinq compteurs racine ne doivent pas diminuer et les octets doivent progresser. Les échecs TCP sont conservés. `has_successful_probe` et `probe_window_inside_application_writes` restent des indicateurs séparés : une valeur fausse ne supprime pas une collecte fonctionnelle complète, mais ne suffira pas à qualifier une phase de la future comparaison. Aucun seuil comparatif de débit/latence n'est appliqué ici.

`check-crash` tue uniquement le pilote après annonce de première écriture, lorsque cible, récepteur et émetteur sont disponibles. Le superviseur termine ensuite le groupe et récupère ses trois outils orphelins avant suppression des espaces. Le code `0` exige alors une sortie de pilote `-9`, trois descendants récupérés et le nettoyage confirmé. Aucun transfert complet ni vidage avant arrêt n'est exigé dans ce mode ; `flow` vaut `null`. La dernière lecture précède l'arrêt des outils.

Une erreur opérationnelle déclenche le nettoyage des seules ressources possédées, sans JSON final de réussite. Les règles de refus en cas d'identité ou d'arrêt non confirmés restent celles du [superviseur](LAB_GUARD.md). Sa propre destruction par SIGKILL et la restauration d'un réseau existant ne sont pas validées.

## Rapport et preuves intermédiaires

Le rapport local v1 `lab_cake_active_check` garde les champs du contrôle actif : PID, espaces, réservation, sortie du pilote, descendants récupérés, `cleanup_verified`, configuration CAKE, `queue_samples`, `traffic_statistics_delta` et `flow`. La différence porte uniquement sur les cinq compteurs racine, depuis avant pilote jusqu'à après sa fin ; toute baisse observée dans la séquence la rend indisponible et empêche un succès normal. Une progression de trafic IPv6 automatique peut aussi entrer dans la fenêtre : la différence n'est pas le seul volume utile TCP.

`--evidence FICHIER_NEUF` est requis. Le journal JSONL est créé exclusivement, sans écrasement ni suivi d'un lien symbolique à son emplacement, et reste hors réservation jetable. Il conserve d'abord les noms/réservation possédés, puis chaque lecture de file brute/normalisée avec date et PID du pilote lorsqu'il existe. Les étiquettes de phase des échantillons sont ajoutées par l'observateur après le relevé ; les dates permettent de les relier au journal. Un événement `cleaned`, avec sortie du pilote, descendants et rapport de flux, n'est ajouté qu'après réussite de l'ensemble du contrôle.

Le journal est écrit et vidé après chaque événement ; une erreur de collecte conserve les événements déjà écrits. Cela ne garantit pas la conservation après panne d'alimentation. Les journaux stderr et codes du lanceur complètent ces relevés ; le journal de possession est aussi conservé si le nettoyage échoue. Le JSON final n'est publié qu'après nettoyage. Les codes restent `0` pour succès technique, `1` pour erreur, `2` pour arguments invalides et 129/130/143 pour interruption gérée après nettoyage réussi.

## Vérification et essai natif

Sans privilèges :

```sh
python3 -I -B scripts/lab-cake-active.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_active.py' -v
```

Les tests vérifient transfert complet simulé, statistiques périodiques et preuves conservées, trois outils réellement récupérés après mort forcée, profil inconnu, changement d'options après activation, erreur de configuration/statistiques, baisse des compteurs, absence de vidage, échéance et interruption. Les fichiers préexistants ou liens symboliques ne sont pas modifiés. Ces tests ne démontrent pas le routage ou l'ordonnancement natif.

L'essai natif exige Linux, Python 3, `ip`, `tc`, `sysctl`, UID 0 et `CAP_NET_ADMIN`/`CAP_SYS_ADMIN`. `CAP_NET_RAW` n'est pas requis pour ce contrôle TCP. Compiler avec le compte habituel les trois binaires Go utilisés par le [contrôle actif TBF](LAB_ACTIVE.md), puis figer leurs versions et empreintes avec toutes les sources Python nécessaires.

Préparer un dossier neuf avec protocole, commit, versions, empreintes, binaires et prévisualisations. Le lanceur peut revérifier `check`/`check-crash` sous TBF avant les deux modes CAKE, car l'activation et le superviseur sont partagés. Prévoir un journal de preuves CAKE distinct par mode, capturer stdout/stderr/codes et refuser toute reprise qui écraserait des résultats. Vérifier ensuite volumes, sondes, paramètres, compteurs, preuves et disparition des ressources avant de consigner une validation native. La comparaison des six campagnes viendra après ce contrôle fonctionnel et de panne.

La sous-étape suivante est maintenant implémentée : [campagne CAKE de trois paires](LAB_CAKE_CAMPAIGN.md), avec contrôles de passage et qualification de charge distincte de TBF. Ses tests avec commandes réseau simulées sont complétés par une [première validation native](VALIDATION_LAB_CAKE_CAMPAIGN_2026-10-30.md) : six phases, charge qualifiée et nettoyage confirmé. L’[orchestration des six campagnes comparatives](LAB_COMPARISON_RUN.md) est implémentée et testée avec des opérations simulées ; sa collecte native reste à réaliser.
