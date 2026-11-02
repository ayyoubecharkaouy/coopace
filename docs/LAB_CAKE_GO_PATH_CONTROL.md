# Passage IPv4 raccordé au superviseur Go puis trafic

## État

Le [contrat de passage IPv4](LAB_CAKE_GO_PATH.md), ses lecteurs purs et leur raccordement au superviseur sont implémentés. Les tests du raccordement utilisent un réseau simulé et de vrais groupes Go/trafic de test ; les tests de l’exécuteur utilisent de vrais sous-processus sans réseau. **La [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) est confirmée.** La [validation combinée historique](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) garde son périmètre sans sondes négatives.

Une entrée distincte est disponible :

```sh
python3 -I -B scripts/lab-cake-go-path.py plan
```

`plan` ne crée aucune ressource et ne demande aucun privilège. Les modes `check` et `check-crash` exigent `--worker`, `--binaries` et `--artifacts`, un dossier existant neuf et vide, ainsi que les privilèges du laboratoire Linux amd64 avec Python `os.setns`. Les [outils de préparation et de relecture natives](LAB_CAKE_GO_PATH_NATIVE.md) sont livrés pour cette extension ; leur [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) est consignée ; toute répétition exige un dossier neuf.

Le [premier essai natif](REVIEW_CAKE_GO_PATH_FAILURE_2026-11-01.md) a été refusé à cause de l’interaction `-c`/`-w`. Les commandes corrigées retirent `-w` et conservent les comptes stricts et les délais externes. Une nouvelle préparation a permis la [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) des deux modes corrigés.

## Organisation

| Emplacement | Responsabilité |
| --- | --- |
| `scripts/lab_cake_go_path.py` | Lecteurs purs des comptes ICMP et des états relus du forwarding |
| `scripts/lab_cake_go_path_control.py` | Inventaire étendu à ping, exécuteur à deux captures, séquence de passage et continuité |
| `scripts/lab-cake-go-path.py` | Entrée séparée `plan`, `check`, `check-crash` |
| `scripts/lab_cake_go_active.py` | Possession unique, point de raccordement avant le collecteur TCP et nettoyage global |

L’inventaire commun peut spécialiser ses empreintes de sources ; l’inventaire du nouveau contrôle ajoute le lecteur, l’exécuteur et son entrée. Le chemin canonique et l’empreinte ELF de `ping` sont vérifiés avec les autres outils. Sa version doit annoncer iputils ; stdout et stderr de `ping -V` sont conservés dans l’environnement. La locale de ses commandes est fixée à C.

## Séquence et refus

Le propriétaire et son échéance sont conservés de bout en bout. Go termine normalement, son groupe est récupéré, puis le superviseur active les mêmes espaces et la même CAKE. Le groupe destiné au trafic reste neuf et sans leader pendant le passage.

`PathCheck` exécute les six commandes fixes du contrat : désactivation, relecture de `0`, sonde négative, réactivation, relecture de `1`, sonde positive. Une seule tentative de chaque commande est permise, dans cet ordre. Une erreur interdit la suite ; un échec de sonde négative interdit notamment la réactivation et la sonde positive dans ce contrôle abandonné.

Les identités possédées, outils et sources sont revérifiés avant chaque commande et après sa sortie. Les identités des liens de passerelle et les statistiques CAKE sont relues après chaque étape, y compris avec forwarding à `0`. La relecture complète de topologie qui exige `1` est effectuée avant et après le passage.

Le superviseur exige ensuite `state: verified` et `path_verified: true` avant de construire le collecteur TCP. Le mode `check` reprend le transfert de 8 Mio et dix sondes ; `check-crash` reprend la mort forcée du seul pilote de trafic après son annonce, avec récupération des trois outils. Une panne Go ou de passage ne peut atteindre ce lancement.

## Exécution bornée et nettoyage

Chaque commande possède un stdin fermé et deux pipes non bloquants, stdout/stderr, limités chacun à 64 Kio. Le code OS réel est conservé, notamment `1` pour la sonde négative attendue. Une capture trop grande, un délai dépassé, un signal ou une erreur de lancement ne devient pas une preuve de blocage.

Les échéances d’exécution sont de 2 s pour sysctl, 4 s pour la sonde négative et 6 s pour la positive, sous l’échéance globale restante de 180 s. L’exécuteur vérifie les deux pipes et le propriétaire sans attendre une lecture bloquante. Les commandes épinglées `ip`/`sysctl`/`ping` ne doivent pas créer de sous-processus auxiliaire ; le sondage utilise une adresse numérique et IPv4 explicite.

Le processus courant est enregistré dans `owner.command_child` dès son lancement. En sortie normale ou sur erreur, il est arrêté si nécessaire et récupéré, avec une attente bornée à 1 s. Une récupération incertaine conserve cette référence pour le nettoyage final du propriétaire. Les captures sont fermées dans tous les cas. Le nettoyage existant arrête les processus avant de supprimer les espaces ; une incertitude persistante conserve les espaces et produit un échec. Aucun forwarding de l’hôte n’est modifié pour compenser une interruption dans le laboratoire.

## Rapport et preuves

Le nouveau rapport porte `kind: lab_cake_go_path_check`, avec le même schéma de base et un objet `path_check` distinct. L’ancienne commande conserve son type et son comportement sans ce raccordement.

`path_check` garde son état, le marqueur d’acceptation, les six résultats bruts, les faits recalculés sans/avec forwarding, deux relevés CAKE et leur différence. `probe_attempted` signifie tentative de lancement d’une sonde, sans garantir qu’un paquet ait été émis. Le champ racine `traffic_generated` garde la signification du collecteur TCP ; ses valeurs ne permettent pas de déduire l’absence de trafic ICMP. Les comptes de sondes restent disponibles séparément.

Les événements `path_begin`, `path_tool_intent`, `path_tool_result` et `path_verified` sont intégrés au journal durable existant. Chaque intention précède le lancement ; chaque résultat conserve arguments, indice, code OS, PID, récupération, dates UTC, durée monotone, captures base64 et indicateurs de troncature. Une validation de capture peut échouer après un résultat de commande correctement enregistré ; l’erreur figure alors dans l’objet de passage et la fin du contrôle.

La durée du résultat inclut la récupération et les vérifications après sortie. L’échéance de commande est imposée par l’exécuteur ; la revue du passage utilise cette durée totale comme majorant conservateur. Un échec d’écriture des preuves interdit le lancement suivant et tout succès global.

Les relevés `before_path` et `after_path` ne modifient pas la différence d’activation déjà figée. Le départ de la différence TCP reste immédiatement avant le pilote, après les sondes ICMP. Une baisse de compteur ou une modification de CAKE interdit le succès.

Le relecteur natif historique refuse ce nouveau type de rapport. Les [outils de préparation et de relecture natives](LAB_CAKE_GO_PATH_NATIVE.md) adaptés sont maintenant livrés ; leur revue réutilise explicitement les vérifications communes et recalcule le passage IPv4. La [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) confirme les deux modes. Le [contrat de campagne répétée Go](LAB_CAKE_GO_CAMPAIGN.md) est défini avant collecte : trois paires repos/charge, dialogue lié à la session et critères séparés. Les [lecteurs et l’automate purs](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md) sont implémentés et couverts par quatorze tests. Le [pilote privé des six phases](LAB_CAKE_GO_CAMPAIGN_TRAFFIC.md) est livré et testé avec outils simulés et vrais processus. Le [collecteur des six phases](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) est implémenté et testé avec réseau simulé : contrôle des PID, journal durable et vidage entre phases. L’[évaluation pure des mesures](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) est implémentée et testée. Son raccordement aux preuves du superviseur constitue la prochaine sous-étape ; la commande publique et les essais natifs de campagne restent ultérieurs.

## Vérification

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go_path*.py' -v
```

Les tests propres au raccordement couvrent captures des deux pipes, locale et stdin, codes réels, dépassements de taille/délai, interruptions, échec de lancement, attente incertaine, producteur ping et ordre fermé. L’intégration simulée vérifie fin normale et panne du pilote, aucune ouverture TCP sans passage accepté, comptes/captures invalides, forwarding mal relu, lien modifié, sources/outils ou journal défaillants et nettoyage après interruption. La suite des neuf lecteurs purs reste séparée.

Validation locale du 1er novembre 2026 : les 198 tests Python passent en 452,576 s, dont treize tests propres au raccordement. Le mode `plan` est également vérifié sans privilèges. Aucun contrôle réseau natif de cette extension n’a été exécuté.

Les tests ne valident ni gain réseau, ni passage natif de cette extension, ni couverture du foyer, IPv6/DNS ou restauration réelle. La campagne comparative de l’intégration Go reste ultérieure.
