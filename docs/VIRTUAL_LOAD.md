# Premier flux de charge synthétique — préparation de l'étape 4.2

## Objectif et état

Le chemin IPv4 du laboratoire a été [validé en ICMP/TCP](VALIDATION_VIRTUAL_LAB_2026-10-29.md). Le nouveau mode `run-load` prépare maintenant un transfert borné entre le client et le serveur neufs, par la même passerelle. Le code et les tests simulés sont livrés. **Un premier transfert natif est validé** : 8 Mio envoyés et reçus en environ huit secondes, avec cadence et nettoyage conformes. Le [compte rendu](VALIDATION_VIRTUAL_LOAD_2026-10-29.md) conserve les observations, les empreintes et le code de sortie exact `0`.

Cette sous-étape vérifie la génération, la réception et l'arrêt d'un flux synthétique. Elle précède les séries de latence comparées au repos/sous charge. Elle n'ajoute ni politique de files, ni goulot artificiel, ni mesure de saturation ; le réseau virtuel peut absorber ce flux sans congestion.

## Paramètres fixés avant l'essai

| Élément | Valeur |
| --- | --- |
| Topologie | Trois espaces neufs, client → passerelle → serveur, selon [VIRTUAL_LAB.md](VIRTUAL_LAB.md). |
| Sens | Client `10.203.0.2` vers serveur `10.203.0.6:46002`, un flux TCP. |
| Données | Octets nuls synthétiques ; aucun fichier, DNS, Internet ou service extérieur. |
| Volume exact | 8 388 608 octets (8 Mio), vérifiés séparément en émission et réception. |
| Plafond moyen applicatif | 1 048 576 octets/s (1 Mio/s), blocs d'au plus 16 Kio. |
| Délais applicatifs | Émission : 12s ; réception, attente comprise : 15s. |
| Mise en disponibilité | Au plus 50 pauses de 0,1s, comme pour le serveur TCP précédent. |
| Répétition initiale | Une exécution fonctionnelle ; aucune inférence statistique. |

Le plafond est une cadence applicative moyenne, pas une limitation de lien par `tc`. Les écritures peuvent être tamponnées et les en-têtes ne sont pas inclus. La durée d'émission prévue est d'au moins huit secondes ; la durée totale du script inclut les sondes ICMP, les opérations locales et le nettoyage, sans borne globale dure.

## Critères de réussite et d'arrêt

L'essai exige les contrôles ICMP du laboratoire, l'annonce de disponibilité du récepteur, l'envoi des 8 Mio, la réception exacte suivie de la fin du flux et le nettoyage réussi. Le rapport doit indiquer `requested_bytes = written_bytes = 8388608`, `requested_bytes_per_second = 1048576` et une moyenne au plus égale à ce plafond. Le journal doit indiquer `8388608 octets reçus`.

Un volume incomplet ou excessif, une erreur de connexion, une expiration, une indisponibilité du récepteur ou un échec de nettoyage arrête l'essai avec un code non nul. Aucun JSON n'est publié par le script après un échec. Il ne relance pas automatiquement un transfert.

Ces critères évaluent le fonctionnement du générateur. Aucun seuil de gain de latence, de capacité WAN ou d'équité n'est fixé par ce test. Les séries futures devront définir ces critères selon leur scénario avant de mesurer.

## Reproduire l'essai natif

Depuis la racine du dépôt, compiler sans élévation :

```sh
mkdir -p .local/bin .local/experiments
sh scripts/go.sh build -o .local/bin/coopace-lab-load ./scripts/lab-load
sh scripts/lab-network.sh plan
```

Choisir des noms de fichiers neufs pour chaque essai, puis lancer explicitement depuis le terminal Linux :

```sh
sudo sh scripts/lab-network.sh run-load > .local/experiments/load-report.json 2> .local/experiments/load.log
printf '%s\n' "$?" | tee .local/experiments/load.exit
```

Conserver le commit, l'empreinte du binaire, les deux fichiers et le code de sortie. Les redirections du compte habituel conservent la propriété des fichiers. Le mode exige les mêmes outils, UID et capacités que `run-tcp`, avec le seul binaire `coopace-lab-load` ; il ne compile ni n'installe quoi que ce soit avec les privilèges.

Le script arrête et attend son propre récepteur avant de supprimer les espaces. Les interruptions gérées utilisent le mécanisme déjà testé du laboratoire. Le fichier de disponibilité privé s'appelle `load-ready` ; il est supprimé avec les autres ressources propres. Les limites après SIGKILL, panne machine ou erreur de suppression et la récupération ciblée restent celles de [VIRTUAL_LAB.md](VIRTUAL_LAB.md). Le nettoyage normal de ressources neuves n'est pas une restauration indépendante de production.

## Rapport et contrôles

Le [format de l'émetteur](../scripts/lab-load/README.md) est distinct de `tcp_connect` et du diagnostic de passerelle. Il ne doit pas être fourni à `latency compare`. Seuls le code `0` du script et les journaux associés ajoutent la confirmation de réception à ce rapport d'écritures côté client.

Les tests Python simulent aussi les échecs de l'émetteur, du récepteur, une réception incomplète, un rapport vide, une interruption et un nettoyage refusé. Ils vérifient l'arrêt du processus avant suppression de son espace. Les tests Go contrôlent les volumes et délais avec `net.Pipe` ; le test de sockets réel peut être ignoré dans l'environnement isolé.

```sh
sh -n scripts/lab-network.sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
sh scripts/go.sh test -count=1 -v ./scripts/lab-load
```

## Prochaine activité

Préparer ensuite plusieurs paires de séries sur une même topologie, avec la même cible de latence et les mêmes paramètres : sans ce flux, puis pendant ce flux. Consigner l'ordre, les répétitions et les horaires d'activité pour vérifier le recouvrement réel avec les mesures. L'étiquette `loaded` seule ne prouve ni ce recouvrement ni une saturation.

La latence simultanée, les répétitions et leur collecte ne sont pas encore intégrées dans `run-load`. La comparaison restera descriptive tant que le scénario et les conditions ne permettent pas une conclusion causale. La [référence initiale](GATEWAY_BASELINE.md), les métriques complémentaires et la restauration restent nécessaires pour clôturer l'étape 4.2.

Le nouveau mode distinct [`run-series`](VIRTUAL_SERIES.md) prépare désormais cette association sur une même topologie, avec trois paires, des horodatages d'écriture et le comparateur strict. Un [premier essai natif de ces séries](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) est consigné ; `run-load` conserve son rôle de transfert seul.
