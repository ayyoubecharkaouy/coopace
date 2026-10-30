# Cycle de vie CAKE sur lien désactivé

## État et portée

`scripts/lab-cake.py` et le module `lab_cake.py` implémentent un premier contrôle CAKE : création, relecture des options/statistiques et nettoyage après fin normale ou mort forcée d'un pilote. Les tests utilisent des espaces et commandes réseau simulés, avec de vrais processus/signaux. **La première validation native est consignée** : les quatre contrôles TBF/CAKE ont réussi, avec options, statistiques et nettoyage conformes. Voir le [compte rendu du 30 octobre](VALIDATION_LAB_CAKE_2026-10-30.md).

Le lien reste DOWN, sans adresse, route, forwarding ou transfert. Ce contrôle prépare le [protocole TBF/CAKE statique v1](CAKE_COMPARISON.md) ; il ne mesure ni débit réel, latence, isolation des flux ou bénéfice CAKE. Le [goulot TBF qualifié](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) reste une expérience distincte. Le [contrôle fonctionnel CAKE actif](LAB_CAKE_ACTIVE.md) est maintenant [validé en natif](VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md) pour un transfert et le nettoyage normal ou après mort forcée ; la comparaison des six campagnes reste à développer.

## Création et supervision

Le [superviseur indépendant](LAB_GUARD.md) possède trois espaces neufs. Seuls passerelle et serveur sont reliés par un veth `wan`/`eth0`, créé directement dans ces espaces et laissé désactivé. Le client reste isolé. Les identités des espaces sont revérifiées avant chaque opération ; une collision ne donne aucun droit sur un objet existant.

Une préparation commune du veth est extraite dans `lab_queue.QueueCheck.prepare_link`. Les contrôles TBF gardent leurs paramètres et sorties ; le module CAKE réutilise cette préparation, les commandes bornées, la lecture JSON stricte et les différences de compteurs. Il dispose de son propre validateur d'options et de statistiques CAKE.

Le contrôle lit l'état initial vide ou noqueue du lien neuf, refuse toute autre racine, puis ajoute une seule CAKE `10:` sans remplacement. Les arguments sont ceux du protocole comparatif : `bandwidth 4mbit`, `besteffort`, `flows`, `nonat`, `nowash`, `raw`, `mpu 0`, `rtt 100ms`, `split-gso`, `no-ack-filter`, `egress`, `memlimit 1048576`, `fwmark 0`. Le budget mémoire n'est pas une longueur de FIFO et le RTT n'est pas un délai injecté ; voir le [manuel iproute2](https://github.com/iproute2/iproute2/blob/v6.1.0/man/man8/tc-cake.8).

Les options, classe et statistiques sont relues après ajout et après fin du pilote. `check` attend sa fin normale ; `check-crash` impose SIGKILL après son annonce de disponibilité. Le pilote laisse volontairement un descendant résistant à SIGTERM : le superviseur doit le terminer et le récupérer avant de supprimer les espaces. Le leader reste non récupéré jusqu'au dernier signal au groupe. Ce contrôle n'est pas encore la panne du pilote de trafic CAKE actif.

Les commandes ont 2s et 64 Kio de stdout ; l'échéance indépendante est 180s et le nettoyage 10s. Une erreur après ajout, même partiel, entraîne le nettoyage des seuls objets possédés. Un arrêt de processus ou une identité non confirmés empêchent la suppression et la publication d'un succès ; le journal de possession est conservé lorsque possible. La destruction du superviseur lui-même et la restauration d'un réseau existant restent hors garantie.

## Producteur JSON et validation

Le profil pris en charge est **iproute2-6.1.0**. La bannière `tc -V` est lue sous contrôle du superviseur, bornée à 512 octets et conservée avec le chemin de tc. Un profil inconnu arrête le contrôle avant création du veth ou ajout de file ; les trois espaces déjà possédés sont nettoyés. Cette identification ne prouve pas que CAKE est disponible dans le noyau. Aucun chargement manuel de module ni installation n'est effectué.

La validation exige une racine CAKE unique sur `wan`, le handle `10:`, bande passante 500 000 octets/s, RTT 100 000µs, mémoire configurée 1 048 576 octets et toutes les options demandées. Les nombres et booléens sont distingués strictement ; le masque nul est la chaîne JSON `"0"` exportée par ce producteur. Les sorties brutes et champs supplémentaires sont conservés. Doublons, nombres non finis, données supplémentaires et types incorrects sont refusés.

Le [producteur CAKE v6.1.0](https://github.com/iproute2/iproute2/blob/v6.1.0/tc/q_cake.c) omet certains zéros : `mpu`, `atm` en mode raw et `autorate` désactivé. `configuration.omitted_fields` conserve la justification de chaque omission identifiée ; `configuration.effective` conserve sa signification. Aucune omission de statistique ne bénéficie de cette règle. Une autre version de tc doit avoir son profil et ses vérifications avant d'être acceptée.

Chaque lecture conserve les sept statistiques racine obligatoires, entiers non négatifs sur 64 bits : les cinq compteurs `bytes`, `packets`, `drops`, `overlimits`, `requeues`, puis les jauges `backlog` et `qlen`. Elle exige aussi `memory_used`, `memory_limit` et une unique entrée objet dans `tins`. La limite mémoire annoncée doit correspondre au budget demandé. Les champs connus de la classe sont conservés dans `cake.tin_fields`, avec `available`, `value` et `reason`; un détail absent reste `null`/`not_reported` et une valeur présente invalide provoque une erreur.

`memory_used_reported_bytes` conserve le champ fourni par le noyau, sans le présenter comme une mesure de RAM actuelle : dans le [noyau Linux v6.1](https://github.com/torvalds/linux/blob/v6.1/net/sched/sch_cake.c), cette statistique expose le maximum enregistré avant une éventuelle réduction de la file et peut dépasser le budget. Aucune différence de mémoire ou de jauge n'est calculée. Les compteurs de la classe ne sont pas ajoutés à ceux de la racine ; `capacity_estimate` ne devient pas une capacité WAN.

## Rapport et erreurs

Le rapport local v1 a le type `lab_cake_check`. Il conserve mode, PID, descendant récupéré, noms, réservation, `cleanup_verified`, `queue_applied: true` et `traffic_generated: false`. L'objet `queue` contient les arguments demandés, le producteur, `link_state: DOWN`, les lectures `before`, `after_add`, `after_driver_exit` et la différence des cinq compteurs racine.

Les lectures ajoutent `collected_at`, `read_duration_ms` et `elapsed_since_start_ms`, ce dernier depuis le début monotone de préparation du veth après identification de tc. Le JSON final n'est publié qu'après nettoyage. Un code `0` exige une sortie du pilote `0` ou `-9` selon le mode, un descendant récupéré et le retrait confirmé des ressources. Il ne signifie pas qu'une file reste installée ou qu'un gain réseau est mesuré.

Une baisse de compteur est conservée comme différence indisponible, sans remise à zéro ni bouclage arithmétique. Comme dans le contrôle TBF de statistiques, cette indisponibilité n'empêche pas de publier une collecte ciblée et un nettoyage réussis ; elle ne sera pas une fenêtre exploitable pour la future comparaison. Les erreurs utilisent `1`, les arguments invalides `2`, les interruptions gérées 129/130/143 lorsque le nettoyage réussit.

## Vérification et essai natif

Sans privilèges :

```sh
python3 -I -B scripts/lab-cake.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake.py' -v
```

Les tests couvrent profils, omissions justifiées, unités, options incompatibles, types, compteurs manquants, classe unique et détails indisponibles. Les tests de processus couvrent fin normale, mort forcée, interruption après ajout, erreur d'ajout/relecture, échéance et nettoyage refusé. Ils n'installent aucune file ni réseau réel.

Le lancement natif exige Linux, Python 3, `ip`, tc avec le profil pris en charge, UID 0, `CAP_NET_ADMIN` et `CAP_SYS_ADMIN`. Aucun binaire Go ni `CAP_NET_RAW` n'est nécessaire. Conserver `lab-cake.py`, `lab_cake.py`, `lab-guard.py` et `lab_queue.py` depuis la même révision.

Préparer un dossier neuf avec commit, empreintes, copie figée de ce protocole et prévisualisation. Le lanceur refuse d'écraser des résultats, conserve stdout/stderr/codes et peut commencer par les deux contrôles TBF de statistiques pour revérifier la préparation partagée, puis lancer `check` et `check-crash` avec `lab-cake.py`. Seuls ces contrôles appellent sudo. Un refus du noyau ou de tc arrête la séquence avec preuves conservées ; les résultats incomplets ne sont pas transformés en validation.

Après les essais, vérifier les rapports, paramètres effectifs et journaux, puis la disparition des noms, réservations et processus consignés. Consigner une validation datée sans modifier les protocoles figés ni l'état historique de préparation. Le contrôle CAKE actif avec transfert et supervision est maintenant implémenté et testé avec des commandes réseau simulées ; sa [première validation native](VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md) est consignée. Les campagnes avec phases idle/loaded et la comparaison restent à développer.
