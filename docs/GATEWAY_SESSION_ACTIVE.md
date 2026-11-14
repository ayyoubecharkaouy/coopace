# Session Go pendant un transfert mesuré

État : contrôle, transfert borné, prise en compte des classes CAKE internes, préparation figée et relecture implémentés. Les tests simulent le réseau et le pair Go, avec de vrais groupes de processus et SIGKILL. Les [deux essais natifs de cette variante sont validés](VALIDATION_GATEWAY_SESSION_ACTIVE_2026-11-14.md) : 4 Mio reçus en fin normale, puis panne de Go pendant le flux, retour à noqueue et nettoyage dans les deux modes. Le [pilotage sans transfert est déjà validé en natif](VALIDATION_GATEWAY_SESSION_2026-11-14.md).

Ce contrôle garde le pilote Go en état `applied` pendant un transfert de **4 Mio**. Il mesure les octets reçus, la durée et le débit utile de réception, ainsi que les compteurs de la CAKE possédée. Il vérifie ensuite le retour à noqueue, après fin normale ou mort forcée du pilote Go pendant le transfert.

## Modules

| Module | Responsabilité |
| --- | --- |
| `scripts/lab_gateway_session_flow.py` | Adresses temporaires, deux outils Go épinglés, sorties bornées, réception et débit, compteurs de file, arrêt des groupes et retrait exact des adresses. |
| `scripts/lab_gateway_session_active.py` | Réutilisation du moteur de restauration et du pilote Go existants ; orchestration et capture complémentaire des classes internes. |
| `scripts/lab_gateway_session_active_review.py` | Relecture des empreintes, dialogue Go, journaux, transfert, compteurs, captures et ressources supprimées. |
| `scripts/lab-gateway-session-active.py` | Commandes de laboratoire `plan`, `check`, `check-crash`, `review`. |
| `scripts/prepare-gateway-session-active.py` | Compilation et gel de `coopace-gateway`, `coopace-session-worker` et `coopace-lab-load`, avec lanceur à usage unique. |

Les modules du contrôle sans trafic restent conservés. Cette variante réutilise leurs canaux, journal, propriété des namespaces, exécution bornée et opérations de restauration ; elle n'ajoute aucune commande d'application aux CLI publiques.

## Topologie et cycle

Les trois namespaces habituels sont créés neufs. Le client reste inutilisé dans cette tranche. Le veth existant relie `wan` dans le namespace passerelle à `eth0` dans celui du serveur. Leurs liens sont actifs et sans adresse lors de la capture initiale ; IPv6 y est désactivé avant création du veth.

Après `applied` reçu de Go, le superviseur ajoute uniquement `10.203.0.5/30` à `wan` et `10.203.0.6/30` à `eth0`. L'émetteur tourne dans le namespace passerelle, le récepteur dans celui du serveur, à `10.203.0.6:41001`. Les deux adresses sont sur le même lien ; aucun forwarding, route par défaut ou accès Internet n'est configuré. Les routes connectées résultent de ces adresses temporaires.

1. Le pilote importe la référence noqueue et son empreinte, vérifie l'accord local et demande l'application. Le superviseur installe la CAKE fixe `10:` à 4 Mbit/s puis Go vérifie sa capture, comme dans le contrôle validé.
2. Le superviseur vérifie les adresses temporaires et prélève les compteurs de référence. Il lance le récepteur, attend `READY`, puis lance l'émetteur et attend `STARTED`.
3. Il exige une progression d'au moins 16 Kio des compteurs CAKE et une augmentation du nombre de paquets, alors que Go et les deux outils TCP sont encore vivants. `STARTED` confirme une première écriture ; l'observation avec outils vivants ne prouve pas une écriture applicative continue ni une congestion.
4. En mode normal, les deux outils doivent terminer avec code 0, volumes envoyés/reçus de 4 194 304 octets et rapports cohérents. La réception exacte inclut EOF. Un relevé final doit montrer au moins le volume applicatif dans la progression des octets CAKE. Go reçoit ensuite `stop`, demande la récupération et termine.
5. En mode panne, Go reçoit SIGKILL après l'observation du trafic, pendant que les deux outils sont encore vivants. Aucun rapport de transfert complet n'est revendiqué.
6. Le superviseur récupère d'abord les deux groupes TCP, puis celui de Go. Il retire seulement ses adresses temporaires, vérifie les extrémités à nouveau sans adresse, relit la file et ses dépendances, retire la racine possédée et compare la capture finale à la référence noqueue.
7. La fermeture des descripteurs et la suppression des namespaces viennent après cette comparaison. Une classe, une adresse ou une configuration étrangère provoque un refus ; un échec de transfert ne devient pas une réussite grâce au nettoyage.

Un ajout d'adresse incertain est traité comme potentiellement effectif ; le retrait relit les deux extrémités et n'accepte que les adresses exactes attendues ou leur absence. Aucune commande `flush` n'est utilisée. Les fenêtres de récupération sont indépendantes de l'annulation du pilote. En mode panne, les octets encore tamponnés peuvent être abandonnés lors de la récupération ; ce mode vérifie le cycle de vie, pas la réception complète.

## Classes CAKE et captures

Le producteur reste limité à iproute2 6.1.0. Son [affichage des classes](https://github.com/iproute2/iproute2/blob/v6.1.0/tc/tc_class.c#L281) utilise du texte, même avec l'option JSON. Le [parcours des classes CAKE du noyau Linux v6.12](https://github.com/torvalds/linux/blob/v6.12/net/sched/sch_cake.c#L2875) expose les flux internes actifs. Un dump vide sans trafic ne représente donc pas tous les états après transfert.

La capture publique conserve son comportement : des classes non vides non JSON restent indisponibles, avec `partial: true`. Cette variante ne transforme pas ce texte en liste vide. Avant retrait, elle importe le snapshot exact avec l'importeur Go puis conserve une lecture complémentaire `tc class show dev wan`, **sans statistiques**, dans `pre-restore.json.classes.txt`.

Le lecteur borné accepte uniquement des lignes `class cake 10:IDENTIFIANT parent 10:`, avec identifiants hexadécimaux uniques de 1 à 1024, correspondant au profil à un seul tin. Autre type, parent, handle, option, feuille, doublon, encodage ou format inconnu : refus. La racine CAKE et ses options sont vérifiées séparément ; les filtres doivent rester disponibles et vides. Toute autre section indisponible interdit le retrait. La capture finale noqueue doit redevenir complète pour les sélections observées et réussir la comparaison Go.

Ces observations restent séquentielles. Le format de classes est testé sur des exemples contrôlés ; les [essais natifs](VALIDATION_GATEWAY_SESSION_ACTIVE_2026-11-14.md) confirment aussi la lecture des flux `10:d3` et `10:1e0` sur cet hôte. Le noyau du dossier préparé est figé dans son manifeste.

## Bornes, preuves et exécution

Le volume est fixé à 4 Mio, avec plafond moyen d'écritures de 1 Mio/s, délai de 15 s en émission et 18 s en réception. Les annonces expirent en trois secondes ; les sorties de chaque outil sont limitées à 64 Kio. Les compteurs ont un budget de 100 relevés. Les délais de lecture du pilote Go restent de 25 s par frontière ; un transfert trop lent échoue et déclenche la récupération. Le superviseur conserve son délai de 120 s, puis dispose de 40 s pour récupérer les groupes et restaurer, et de dix secondes pour le nettoyage final.

Les journaux, trames, snapshots, lectures CAKE, sorties exactes des outils et empreintes sont conservés. La relecture hors ligne réimporte les captures via le binaire Go figé, recalcule la cohérence des rapports envoyés/reçus, vérifie le dialogue et l'ordre de récupération, compare le retour initial et constate l'absence des ressources enregistrées. Elle ne délivre aucun certificat natif.

```sh
python3 -I -B scripts/lab-gateway-session-active.py plan
python3 -I -B scripts/prepare-gateway-session-active.py
```

Depuis un arbre Git propre, la seconde commande compile sans sudo et affiche un `run.sh` absolu. Ce lanceur demande sudo uniquement pour les deux contrôles, puis effectue leurs relectures sans sudo. Il conserve les résultats existants et refuse tout changement de révision, noyau, Python, binaire ou entrée figée. Ne pas relancer le même dossier après collecte ; préparer un autre dossier pour un nouvel essai.

```sh
(cd scripts/tests && python3 -B -m unittest test_gateway_session_flow test_gateway_session_active test_prepare_gateway_session_active -v)
sh scripts/go.sh test ./...
```

Les 16 tests de cette variante couvrent parsing/refus des classes, rapports incohérents, sorties réelles de processus, lancement défaillant, adresses étrangères, ajout incertain, orchestration normale/panne/interruption, import d'une capture partielle de classes, relecture et entrées figées. Le test de transfert réel en boucle locale est explicitement ignoré lorsque les sockets sont interdites ; c'est le cas dans cet environnement. Les scénarios positifs du contrôle emploient des observations réseau et un pair Go simulés, avec de vrais processus récupérés.

Ce palier ne mesure pas la latence, l'équité ni un gain causal face à une référence sans Coopace. Il ne valide pas le trafic routé des appareils du foyer, IPv6/DNS ou la restauration d'une configuration existante. Ces travaux restent distincts de la première preuve de transfert et de retour initial avec le pilote Go vivant pendant le flux.

Vérification de cette tranche : suite Go complète réussie ; 90 tests Python ciblés exécutés, dont 89 réussis et un ignoré explicitement pour l'interdiction des sockets. La relecture du contrôle natif sans transfert reste conforme à ses 109 pièces, sans modifier ses preuves. Les [deux essais natifs](VALIDATION_GATEWAY_SESSION_ACTIVE_2026-11-14.md) ont ensuite confirmé le transfert et le retour initial ; leurs relectures indépendantes vérifient 164 et 161 pièces.

La suite est d’étendre cette session au trafic routé d’un client et d’y associer les mesures de latence au repos/sous charge, selon un protocole distinct.
