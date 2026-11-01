# Contrôle combiné Go puis trafic : collecte et rapport

## État

L’enchaînement du [contrat fonctionnel](LAB_CAKE_GO_ACTIVE.md) est implémenté avec un seul propriétaire des espaces. Les tests utilisent un noyau réseau et des outils simulés, mais de vrais processus, descripteurs, pipes, signaux et groupes Linux. La [préparation et la relecture natives](LAB_CAKE_GO_ACTIVE_NATIVE.md) sont livrées ; les contrôles combinés sont [validés en natif](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) sur une révision figée.

L’entrée `scripts/lab-cake-go-active.py` fournit `plan`, `check` et `check-crash`. `plan` reste sans privilèges ni création de ressource :

```sh
python3 -I -B scripts/lab-cake-go-active.py plan
```

Les modes actifs exigent explicitement `--worker`, `--binaries` et `--artifacts` ; ce dernier désigne un dossier existant, neuf et vide. Ils sont réservés au laboratoire Linux amd64 avec les privilèges du contrôle DOWN. Ils ne sont pas exécutés automatiquement pendant les tests.

## Organisation et séquence

| Module | Responsabilité |
| --- | --- |
| `lab_cake_go_active.py` | Inventaire, preuves durables, phase Go, activation, rapport et nettoyage global. |
| `lab_cake_go_collect.py` | Pilotage des pipes, contrôle des trois PID, accusé ou panne, relevés CAKE et récupération du groupe de trafic. |
| `lab_cake_go_traffic.py` | Transfert et sondes, dialogue lié à la session, empreintes revérifiées avant chaque lancement d’outil. |
| `lab_cake_go_topology.py` | Activation et continuité des mêmes espaces, interfaces, adresses/routes et file CAKE. |

La phase Go normale termine et récupère son groupe avant activation. Le résultat de cette phase garde `cleanup: deferred_to_supervisor`. Ses trois fichiers de preuve sont empreintés avant le trafic puis relus ; le journal Go est validé avec le PID historique du groupe Go, jamais avec celui du nouveau pilote.

Le superviseur active ensuite la topologie fixe. Il prend une lecture immédiatement avant le lancement du pilote, vérifie sa disponibilité, puis envoie `continue` ou tue le seul leader en mode panne. Après récupération du groupe de trafic, il vérifie la fin des pipes, les preuves, la file et les outils, puis ferme l’unique propriétaire des espaces. Un succès n’est publié qu’après nettoyage confirmé et synchronisation des preuves.

## Vérification des outils annoncés

Les trois PID sont lus uniquement après une annonce valide de cette session. Le superviseur vérifie dans `/proc` leur état vivant, PID du parent, groupe, session, temps de création, exécutable, arguments exacts et identité de namespace. Les trois rôles restent cible, récepteur, émetteur. Les ancres sont relues après l’empreinte de l’exécutable. Aucun PID annoncé ne sert à signaler individuellement un processus ; seul le leader possédé est tué pour la panne, et le groupe possédé est récupéré avec le mécanisme existant.

L’inventaire privé `--tools-json` transmis au pilote contient les empreintes attendues de `ip`, de l’agent et des deux outils de trafic. Il est lié à la session, limité à 16 Kio et distinct des lignes READY/continue de 1 Kio. Le pilote autorise seulement les quatre commandes fixes ; il revérifie chemin et SHA-256 avant chacune. Les outils reçoivent `/dev/null` en entrée, sans hériter du pipe de contrôle. L’option `stdin` ajoutée au runner partagé conserve son comportement historique par défaut.

## Mesures et limites

Les paramètres restent ceux du contrat : transfert de 8 Mio, dix sondes TCP, cible/ports privés fixes, pilote 45 s, disponibilité totale 15 s, accusé 5 s. Le propriétaire conserve sa limite globale de 180 s entre les deux phases. Sur une erreur de mesure, son budget indépendant de nettoyage de 10 s permet d’arrêter le groupe avant suppression des espaces ; il n’est pas remplacé par une échéance de mesure déjà expirée. Un arrêt incertain conserve les ressources concernées.

La collecte conserve au plus 240 lectures et 1 Mio de relevés. Chaque lecture revalide options et monotonie des cinq compteurs racine. La cadence attend au moins 250 ms après la lecture précédente, sans rattrapage. Après fin normale et arrêt des outils, le vidage exige deux lectures vides espacées d’au moins 500 ms sous trois secondes depuis la fin observée du pilote. Le mode panne conserve une lecture après arrêt sans exiger ce vidage.

`activation_statistics_delta` est figé à la fin de l’activation. `traffic_statistics_delta` utilise uniquement la lecture juste avant le pilote et celle après arrêt. Le trafic automatique éventuel ne devient ni un volume utile TCP ni une validation IPv6.

Un rapport complet peut conserver dix sondes échouées : code de mesure et tentatives restent visibles. `state: complete` valide la collecte et le nettoyage ; la validation native positive exige en plus dix réussites et le recouvrement des sondes avec les écritures applicatives. Le contrôle ne qualifie aucun bénéfice Coopace ni comparaison de latence.

## Preuves et rapport

Le dossier d’expérience conserve :

- `environment.json` : chemins canoniques et SHA-256 des huit exécutables, sources de travail et commit Git de contexte, noyau, Python et versions textuelles disponibles ;
- `go/worker.jsonl`, `go/events.bin`, `go/worker.stderr` : preuves de la phase Go conservées ;
- `supervisor.jsonl` : transitions, intentions, résultats d’activation, identités et relevés, limités à 4 Mio ;
- `driver.stdout.bin` et `driver.stderr.bin` : octets exacts, limités à 256 Kio chacun ;
- `report.json` : objet v1 `lab_cake_go_active_check` avec état, phases/groupes distincts, topologie, relevés, différences, flux et nettoyage.

Les versions textuelles de Python, iproute2 et sysctl sont relues avant réservation. Les quatre programmes Go n’ont pas de commande de version uniforme : cette absence est explicite dans l’environnement, leurs SHA-256 restent identifiants, et les métadonnées d’exécution disponibles restent dans le journal Go et les exports de flux. Le commit ne remplace pas les empreintes des fichiers de travail.

Les fichiers sont créés exclusivement, sans suivi de symlink, avec mode privé et propriétaire du dossier d’expérience. Les écritures de preuve sont synchronisées avant de poursuivre. Les tailles, identités et empreintes des captures sont revérifiées à la fermeture, y compris contre une modification de contenu à taille identique. Une erreur de preuve ou de nettoyage empêche la publication d’un succès.

Le rapport conserve `congestion: not_assessed` et `traffic_coverage: synthetic_ipv4_only`. `traffic_generated` vaut `false` avant lancement, `null` après lancement tant que l’annonce n’est pas vérifiée, puis `true` après cette vérification. La panne attend Go `0`, pilote de trafic `-9`, trois outils orphelins récupérés et `flow: null`.

## Vérification et suite

`test_lab_cake_go_active.py` enchaîne la phase Go simulée, l’activation et le vrai pilote Python avec quatre outils simulés. Les descripteurs, identités de processus, groupes, signaux et récupérations restent réels ; les rôles d’exécutables et namespaces des outils Python sont explicitement simulés. Les tests refusent erreurs Go/activation, annonce étrangère, PID étranger, sortie prématurée, compteur remis à zéro, absence de progression, file non vidée, lien modifié, preuve défaillante, délai global et nettoyage incomplet.

Les tests dédiés du pilote vérifient aussi l’inventaire avant chaque lancement et l’absence d’héritage du pipe de contrôle. Les tests de topologie vérifient que les relectures après activation ne modifient plus sa différence de compteurs.

Validation locale du 1er novembre 2026 : la suite Python complète passe avec 168 tests en 365,645 s. Elle inclut huit tests du contrôle combiné et onze tests dédiés du pilote. Les limites de simulation décrites ci-dessus restent applicables.

Les [outils de préparation figée et de relecture indépendante](LAB_CAKE_GO_ACTIVE_NATIVE.md) sont livrés. La [première validation native combinée](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) confirme `check` et `check-crash`. La prochaine sous-étape définit les contrôles négatifs du chemin IPv4 avant une éventuelle campagne comparée de l’intégration Go. Ces validations de laboratoire n’autorisent aucune conclusion sur le trafic du foyer, la restauration d’une passerelle réelle ou le bénéfice du pilotage Coopace.
