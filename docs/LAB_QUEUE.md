# Cycle de vie d'une file TBF sous supervision

## État et objectif

Le code et les tests simulés du cycle de vie sont livrés. **Les premiers contrôles natifs avec file sont validés**, ainsi que les deux contrôles sans file sur la même révision. Le [compte rendu](VALIDATION_LAB_QUEUE_2026-10-29.md) conserve les valeurs effectives et les preuves de nettoyage. Les [contrôles natifs précédents](VALIDATION_LAB_GUARD_2026-10-29.md) concernent le superviseur sans file, au commit qui y est consigné.

Cette sous-étape vérifie la configuration d'une file TBF, sa présence après fin normale ou mort forcée d'un pilote, puis son retrait avec les ressources possédées. Elle prépare le [goulot expérimental](VIRTUAL_BOTTLENECK.md), sans activer de chemin de trafic ni lancer la campagne de latence/débit.

## Ressources et opérations

Le superviseur crée les trois espaces neufs `cg-JETON-c/g/s` et arme son échéance avant toute configuration. Le module interne `scripts/lab_queue.py` effectue les opérations sous son contrôle. Aucun nom d'espace ou commande arbitraire n'est accepté par la CLI.

1. Confirmer les identités des espaces possédés, puis vérifier que passerelle et serveur ne contiennent que `lo`.
2. Créer une paire veth depuis la passerelle : `wan` dans celle-ci, `eth0` dans le serveur neuf. Le client reste sans lien dans ce contrôle ciblé. Les deux extrémités doivent rester administrativement **DOWN**, ce qui est relu et vérifié.
3. Lire les files de `wan`. Sur ce lien neuf vérifié DOWN, accepter une liste vide ou une unique racine `noqueue`, handle `0:`, avant toute création de file. Toute autre configuration est refusée.
4. Créer explicitement la racine TBF `10:` : `rate 4mbit`, `burst 65536`, `limit 131072`. Aucun `replace`, file enfant, règle de routage, adresse ou changement de forwarding.
5. Relire et valider le type, le handle et les options effectives. Démarrer le pilote temporaire et son descendant dans la passerelle ; attendre la fin normale ou provoquer le SIGKILL attendu.
6. Relire TBF après la fin du pilote, alors que le superviseur conserve encore son PID. Récupérer les processus, puis supprimer les seuls espaces créés et la réservation privée. Publier le rapport uniquement après nettoyage réussi.

La suppression de l'espace retire sa veth et sa file. Le contrôle n'essaie pas de reconstituer une configuration préexistante et ne touche pas aux interfaces physiques. Les modes de `lab-network.sh` gardent leur cycle de vie et restent sans file configurée.

Un lien DOWN permet de contrôler la configuration mais **ne valide pas l'ordonnancement de paquets ni le débit réel**. Aucun trafic applicatif, adresse, route ou sonde n'est ajouté. Le futur scénario avec trafic devra raccorder la topologie complète, vérifier le passage et recueillir les métriques du protocole avant toute conclusion de congestion.

## Relecture des options et bornes

La lecture utilise `tc -j -r qdisc show dev wan`, explicitement exécuté dans l'espace passerelle. Le choix de `-r` rend le champ `limit` visible ; `-d` est évité ici car il peut formater `burst` en chaîne taille/cellule. Le champ `dev` peut être absent d'une sortie filtrée par interface. Ces comportements proviennent des sources [q_tbf.c](https://github.com/iproute2/iproute2/blob/main/tc/q_tbf.c) et [tc_qdisc.c](https://github.com/iproute2/iproute2/blob/main/tc/tc_qdisc.c) d'iproute2.

Un lien neuf désactivé peut encore utiliser l'ordonnanceur interne `noop`, absent du dump ; `noqueue` est normalement attaché à l'activation. Cela justifie l'acceptation d'un dump vide uniquement dans ce contrôle de lien neuf DOWN. Voir l'[initialisation des files dans le noyau](https://github.com/torvalds/linux/blob/master/net/sched/sch_generic.c) et leur [filtrage dans le dump](https://github.com/torvalds/linux/blob/master/net/sched/sch_api.c).

Le débit JSON attendu est **500 000 octets/s**, correspondant aux 4 000 000 bits/s demandés. La limite doit être exactement 131 072 octets. Pour `burst`, conserver la valeur effective et accepter au plus un octet d'écart autour de 65 536, en raison de sa représentation à partir des ticks du noyau. Une valeur absente, ambiguë ou incompatible arrête le contrôle ; aucun format texte alternatif n'est deviné.

Chaque commande de configuration/relecture dispose d'au plus 2s, dans l'échéance globale de 180s du superviseur. Stdout est limité à 64 Kio et décodé en UTF-8 strict ; doublons JSON, données supplémentaires et nombres non finis sont refusés. Stderr des commandes reste dans le journal du lanceur. Les commandes temporaires sont suivies et récupérées ; un arrêt non confirmé empêche la suppression des espaces.

Les règles de possession, le budget de nettoyage de 10s et les limites du [superviseur](LAB_GUARD.md) s'appliquent. L'échec d'un ajout, même après un effet partiel, ou d'une relecture provoque le nettoyage du laboratoire possédé. Un nettoyage incomplet conserve son journal lorsque possible et ne publie pas de JSON de réussite. Les délais ne garantissent pas l'interruption d'une opération bloquée dans le noyau.

## Prévisualisation et tests

Depuis le dépôt, sans privilèges :

```sh
python3 -I scripts/lab-guard.py plan-queue
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_[gq]*.py' -v
```

Les tests de parseurs vérifient les unités, valeurs effectives, faibles écarts de représentation et refus des options incompatibles. Les tests de cycle de vie simulent `ip`/`tc` et les espaces, avec de vrais pilotes, descendants et signaux. Ils couvrent fin normale, mort forcée, interruption après ajout, état initial inattendu, erreur d'ajout/relecture, perte de possession et nettoyage refusé. Les tests de commandes vérifient sortie bornée, timeout, annulation et récupération du processus. Aucun réseau réel n'est créé par cette suite.

## Reproduire les contrôles natifs

Linux, Python 3, `ip`, `tc`, UID 0, `CAP_NET_ADMIN` et `CAP_SYS_ADMIN` sont requis avant création des ressources. Aucun binaire Go n'est nécessaire. Conserver les deux fichiers Python `lab-guard.py` et `lab_queue.py` ensemble depuis la même révision ; le superviseur charge son module voisin par chemin explicite.

Préparer un dossier neuf avec commit, empreintes des deux scripts et du lanceur, copie figée de ce protocole et prévisualisation. Le lanceur doit capturer séparément les rapports, journaux et codes exacts, sans écraser de résultat existant. Les nouveaux appels sont :

```sh
sudo python3 -I scripts/lab-guard.py check-queue
sudo python3 -I scripts/lab-guard.py check-queue-crash
```

Le lanceur préparé peut commencer par `check` et `check-crash` pour revérifier le superviseur modifié avant les deux contrôles avec file. Une erreur arrête la séquence et conserve les résultats déjà obtenus.

Chaque contrôle avec file doit sortir avec `0` et publier un unique JSON local v1 `lab_queue_check`. Il contient les champs du contrôle de supervision, `queue_applied: true`, `traffic_generated: false`, et un objet `queue` avec paramètres demandés et lectures horodatées `before`, `after_add`, `after_driver_exit`. Les options TBF doivent être conformes dans les deux dernières lectures. Le code du pilote doit être `0` ou `-9` selon le mode et un descendant doit avoir été récupéré. Vérifier aussi les traces, les six noms et les deux réservations de ces deux contrôles.

`queue_applied` décrit la configuration pendant le contrôle ; le rapport n'est publié qu'après suppression du laboratoire. Il ne signifie pas qu'une file reste active. Les erreurs utilisent le code `1`, les arguments invalides `2`, les interruptions gérées 129/130/143 lorsque le nettoyage réussit.

## Suite

Le [premier contrôle natif du cycle de vie](VALIDATION_LAB_QUEUE_2026-10-29.md) est validé. Le [rapport optionnel de réception et les statistiques de file](LAB_INSTRUMENTATION.md) sont implémentés et leurs [premiers contrôles natifs](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) sont validés : réception locale et statistiques sur liens désactivés. Les nouveaux modes `check-queue-stats` et `check-queue-stats-crash` ajoutent deux lectures `tc -j -s -r` et des différences de compteurs, avec un type de rapport distinct. Les contrôles sans statistiques gardent leur sortie précédente.

Le [contrôle fonctionnel actif](LAB_ACTIVE.md) intègre maintenant la topologie et les lectures périodiques ; sa [première validation native](VALIDATION_LAB_ACTIVE_2026-10-30.md) confirme un transfert et le nettoyage dans les deux modes. Les contrôles ICMP de la future campagne, ses trois paires avec goulot puis la référence CAKE manuelle restent à réaliser. L'étape 4.2 reste ouverte ; aucun bénéfice réseau ni restauration de passerelle réelle n'est revendiqué.
