# Chemin actif sous TBF — contrôle fonctionnel v1

## État et objectif

`scripts/lab-active.py` et son module `lab_active.py` raccordent maintenant le [superviseur indépendant](LAB_GUARD.md), la [file TBF](LAB_QUEUE.md) et l'[instrumentation](LAB_INSTRUMENTATION.md). Les tests emploient des commandes réseau simulées et de vrais processus/signaux. **La première validation native est consignée** : transfert complet, dix connexions réussies, statistiques périodiques et nettoyage après fin normale ou mort forcée. Voir le [compte rendu du 30 octobre](VALIDATION_LAB_ACTIVE_2026-10-30.md).

Ce contrôle préalable porte sur un seul transfert. La campagne de [trois paires et ses critères de congestion](VIRTUAL_BOTTLENECK.md) reste à implémenter. Aucun résultat de ce contrôle ne clôt cette campagne ou l'étape 4.2.

## Périmètre fixé avant collecte

Trois espaces réseau neufs `cg-TOKEN-c/g/s`, possédés par le superviseur :

```text
client eth0         passerelle                         serveur eth0
10.203.0.2/30 -> lan 10.203.0.1/30
                   wan 10.203.0.5/30 [TBF 10:] -> 10.203.0.6/30
```

Les deux paires veth sont créées directement dans les espaces du laboratoire. Deux routes spécifiques relient les sous-réseaux ; aucun NAT, route par défaut ou raccordement physique. Le forwarding IPv4 est activé et relu uniquement dans la passerelle neuve. Le passage complet est vérifié par le transfert TCP ; ce contrôle n'ajoute pas le contrôle négatif ICMP prévu pour la future campagne.

TBF est ajouté sur `wan` encore DOWN, sans remplacement : `rate 4mbit`, `burst 65536`, `limit 131072`. Les paramètres sont relus après ajout, après activation et après fin du pilote. Une configuration inattendue arrête le contrôle. L'activation peut générer du trafic IPv6 automatique ; le relevé juste avant lancement du pilote sert de départ à la différence de compteurs. Celle-ci inclut tout trafic observé dans cette fenêtre, pas uniquement les octets utiles du transfert.

| Paramètre | Valeur |
| --- | --- |
| Charge | 8 388 608 octets vers `10.203.0.6:46002`, plafond moyen applicatif 1 048 576 octets/s. |
| Délais de charge | Émetteur 25s ; récepteur 28s, incluant son attente initiale. |
| Sondes | Dix connexions vers `10.203.0.6:46001`, timeout 1s, pause 250ms, condition déclarée `loaded`. |
| Cible | Au plus 100 acceptations et 30s ; arrêt après les sondes. |
| Départ des sondes | Au moins 1s après l'annonce de première écriture de charge. |
| Statistiques | Avant lancement, puis pause d'au moins 250ms entre fin d'une lecture et début de la suivante, enfin après fin du pilote. |
| Vidage normal | Deux lectures avec backlog et qlen nuls, espacées d'au moins 500ms ; délai de contrôle 3s. |
| Bornes | Pilote 45s ; superviseur 90s ; nettoyage 10s ; chaque commande ip/tc/sysctl 2s. |
| Volume de collecte | Au plus 240 lectures périodiques, budget JSON cumulé 1 Mio ; sortie du pilote 256 Kio. |

Les commandes de disponibilité restent bornées à 5s par outil et les sondes à 16s. La cadence de statistiques est indicative, sans rattrapage après commande lente ; conserver les durées et dates réelles. Il ne s'agit pas d'un échantillonnage exact à 4 Hz.

## Deux modes, deux contrats

`check` attend la réception complète et EOF, valide les volumes, durées, débits applicatifs et dix tentatives, puis le vidage de la file. Aucun des cinq compteurs ne doit diminuer entre lectures ; au moins le compteur d'octets doit augmenter. Les compteurs autres que les octets peuvent rester constants. Le code `0` exige aussi une fin normale du pilote et le nettoyage confirmé.

Les échecs TCP sont conservés, y compris dix échecs sur dix. Les champs `has_successful_probe` et `probe_window_inside_application_writes` indiquent séparément la réussite des sondes et leur recouvrement avec les écritures applicatives. Leur valeur `false` n'empêche pas de conserver une collecte fonctionnelle complète ; elle ne permet pas de qualifier une mesure loaded pour la future campagne. Aucun seuil de débit ou de latence ne qualifie une congestion ici.

`check-crash` attend que cible, récepteur et émetteur soient disponibles, puis tue **le pilote seulement** par SIGKILL après la première écriture. Le superviseur termine ensuite le groupe, récupère les trois outils orphelins et retire les espaces. Il exige une sortie du pilote `-9` et trois descendants récupérés. Ce contrôle n'attend pas de transfert complet ni de vidage préalable et ne publie aucun rapport de flux. Sa dernière lecture de file précède l'arrêt des outils ; elle ne représente pas un état après arrêt du trafic.

Le superviseur conserve le leader du groupe non récupéré jusqu'au dernier signal collectif, comme dans les contrôles précédents. Les outils restent dans ce groupe et ne créent aucune session supplémentaire. Les identités des espaces sont revérifiées avant chaque opération. Le JSON final n'est publié qu'après nettoyage ; une erreur garde stderr et le code de sortie, sans JSON de réussite. Un nettoyage incomplet conserve le journal de possession. Le SIGKILL du superviseur lui-même reste hors garantie.

## Résultats locaux

Le JSON v1 `lab_active_check` conserve les PID, noms d'espaces, réservation, sortie du pilote, nombre d'orphelins récupérés et `cleanup_verified`. `queue` contient les relectures de configuration ; `queue_samples` contient les objets JSON originaux de tc, normalisés avec compteurs/jauges et horodatages. `traffic_statistics_delta` utilise les lectures avant pilote et après sa fin ; toute baisse observée dans la séquence rend cette différence indisponible. Aucune différence de jauge n'est calculée.

En mode normal, `flow` conserve les rapports complets `send`, `receive`, `latency`, le code des sondes et les deux indicateurs de contexte. En mode crash, `flow` vaut `null`. `congestion` vaut toujours `not_assessed` et `traffic_coverage` vaut `synthetic_ipv4_only`. Le débit reçu décrit les octets livrés à l'application ; aucun gain WAN ou Coopace n'est déduit.

## Vérification et lancement

Sans privilèges :

```sh
python3 -I -B scripts/lab-active.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_active.py' -v
```

Les tests couvrent le flux complet avec outils simulés, les statistiques périodiques, la mort forcée avec trois vrais processus récupérés, l'échéance, une erreur de configuration, une file qui ne se vide pas, une baisse intermédiaire des compteurs et les rapports incohérents. Ils ne prouvent pas la topologie ou la limitation du noyau.

Pour le lancement natif : Linux avec `ip`, `tc`, `sysctl`, Python 3 et les privilèges `CAP_NET_ADMIN`/`CAP_SYS_ADMIN` décrits dans [LAB_GUARD.md](LAB_GUARD.md). Compiler les trois binaires avec le compte habituel :

```sh
sh scripts/go.sh build -o .local/bin/coopace ./apps/agent/cmd/coopace
sh scripts/go.sh build -o .local/bin/coopace-lab-tcp ./scripts/lab-tcp
sh scripts/go.sh build -o .local/bin/coopace-lab-load ./scripts/lab-load
```

Préparer un dossier d'expérience neuf avant chaque essai : copie de ce protocole, commit, versions, empreintes des sources et binaires, prévisualisation, lanceur conservant séparément stdout/stderr et codes des deux modes. Le lanceur appelle `sudo` uniquement pour ces contrôles et refuse d'écraser des résultats existants. Examiner ensuite rapports, codes et disparition des noms/réservations avant de consigner une validation native. Les anciennes expériences restent intactes.
