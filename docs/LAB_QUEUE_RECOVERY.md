# Cycle de restauration de file dans le laboratoire

État : moteur de laboratoire, lanceur figé et relecture implémentés ; tests avec réseau simulé, vrai binaire Go et vrais processus réussis. Les deux essais réseau natifs restent à exécuter sur le PC utilisateur. La restauration du réseau du foyer n'est pas validée.

Le contrôle réalise `noqueue → CAKE possédé → noqueue` et vérifie l'état final **avant** de supprimer ses namespaces. Il exploite les [captures et comparaisons Go](GATEWAY_RECOVERY.md) ; la suppression finale des ressources jetables n'est donc plus utilisée comme preuve suffisante du retour à la file initiale.

## Périmètre et cycle

Le superviseur Python réutilise les propriétaires de namespaces et groupes de processus existants. Les trois namespaces habituels sont créés neufs ; seuls passerelle et serveur sont reliés par un veth `wan`/`eth0`. Leurs interfaces sont activées sans adresse IP ; IPv6 est désactivé dans ces deux espaces avant création du lien. Aucune route, sonde ou charge applicative n'est ajoutée. Aucun paramètre d'interface physique n'est accepté.

| Phase | Contrôle |
| --- | --- |
| Création | Namespaces possédés et distincts de celui du superviseur ; descripteurs retenus, type réseau vérifié par ioctl et identités comparées. |
| Référence | Veth et adresses contrôlés ; capture Go `before.json`, import strict et profil `noqueue-root-v1` reconnu. |
| Installation | Nouvelle capture et comparaison à la référence, intention synchronisée, ajout unique de CAKE racine `10:` à 4 Mbit/s. |
| Application constatée | Producteur iproute2-6.1.0, options et statistiques du profil fixe, nouvelle capture sans classes ni filtres sélectionnés. |
| Pilote | Processus séparé et descendant temporaire : fin normale, ou SIGKILL du pilote après disponibilité ; namespace du descendant vérifié. |
| Récupération | Groupe du pilote récupéré, relecture des identités, adresses, classes/filtres et CAKE possédé ; retrait ciblé de la racine `10:`. |
| Retour initial | Nouvelle capture Go et `restore-check` : `selected_state_matches`, empreintes liées aux fichiers exacts. |
| Nettoyage | Fermeture des descripteurs de namespaces, récupération des commandes puis suppression des seuls espaces et réservation possédés. |

Le profil CAKE reprend les options de la référence du laboratoire : `besteffort`, `flows`, `nonat`, `nowash`, `raw`, MPU 0, RTT 100 ms, `split-gso`, `no-ack-filter`, `egress`, mémoire 1 048 576 octets et fwmark 0. Les options/champs structurels inconnus, un autre handle, des classes/filtres ajoutés ou un changement d'identité interdisent le retrait. CAKE peut exposer des classes correspondant à ses [files actives](https://github.com/torvalds/linux/blob/v6.12/net/sched/sch_cake.c#L2875) ; ce premier contrôle sans trafic exige des sélections vides.

Un ajout ayant échoué reste traité comme potentiellement effectif après son intention durable. Le superviseur relit alors l'état : une racine initiale restée intacte n'est pas supprimée ; une CAKE conforme peut être retirée ; une configuration étrangère est refusée. Un échec initial ne devient pas un contrôle réussi parce que le nettoyage a fonctionné.

## Exécuter

Prévisualisation sans privilèges :

```sh
python3 -I -B scripts/lab-queue-recovery.py plan
```

Depuis un arbre Git propre, avec le compte habituel :

```sh
python3 -I -B scripts/prepare-queue-recovery.py
```

La préparation compile un seul `coopace-gateway` Linux amd64 depuis le commit courant, exige une provenance VCS propre, et fige les sources Go/Python, le binaire, les outils et le lanceur dans un dossier neuf `.local/experiments/queue-recovery-validation-REVISION/`. Elle affiche la commande `sh .../run.sh` exacte. Aucun réseau ni privilège n'est utilisé par la préparation.

Le lanceur réserve son exécution, refuse les résultats existants, vérifie ses entrées, puis utilise `sudo` uniquement pour les deux contrôles `check` et `check-crash`. Linux amd64, les capacités `CAP_NET_ADMIN`/`CAP_SYS_ADMIN`, iproute2-6.1.0 et CAKE disponible sont requis. Le programme ne les installe pas. Prévoir environ une minute ; les deux modes ont des laboratoires distincts. Un essai échoué est conservé et ne doit pas être réécrit.

Les commandes ont des groupes propres, une sortie bornée à 512 Kio sur stdout et 4 Kio sur stderr, et un délai de six secondes par défaut, vingt secondes pour une capture Go. Le pilote a une fenêtre globale de 90 secondes ; sa récupération dispose ensuite d'une fenêtre indépendante de 30 secondes, suivie du nettoyage borné à dix secondes. L'arrêt d'un groupe de commande dispose de trois secondes supplémentaires. Une interruption du superviseur est consignée et ne supprime pas sa tentative de récupération bornée.

## Preuves et relecture

Les captures avant/pré-ajout/appliquée/pré-retrait/après, les évaluations Go, l'environnement, les octets stdout/stderr de chaque commande et un journal JSONL séquencé sont conservés. Les intentions et résultats sont synchronisés. Les exécutables ELF sont ouverts et contrôlés par SHA-256 ; les opérations principales utilisent ces descripteurs. Les sous-outils recherchés par Go sont contrôlés par chemin et empreinte avant/après les appels. Le pilote Python utilise le descripteur retenu du superviseur pour relancer son descendant, qui ferme ses propres descripteurs hérités.

`report.json` indique séparément `applied_verified`, `root_removed`, `restoration_verified` et `cleanup_verified`. Pour un contrôle complet, ils doivent être vrais, avec pilote `0` ou `-9` selon le mode et un descendant récupéré. `restoration_verified` porte sur les champs sélectionnés de ce veth, pas sur une configuration de foyer complète.

La relecture sans privilèges vérifie les empreintes, l'ordre du journal, les mutations exactes de file, les identités déclarées et l'absence actuelle des namespaces, réservation et PID. Elle recalcule la comparaison Go depuis les fichiers conservés, sans opération réseau :

```sh
python3 -I -B scripts/lab-queue-recovery.py review --gateway DOSSIER/coopace-gateway --artifacts DOSSIER/check
```

Le lanceur effectue cette relecture automatiquement pour chaque mode. Le résultat est `queue_recovery_evidence_reviewed`, avec `native_certificate: false` ; les contrôles sur données simulées restent étiquetés `execution_source: simulated`. Une relecture ne constitue pas une signature d'authenticité ni une nouvelle exécution réseau.

## Limites

Ce moteur est une intégration de laboratoire Python ; la passerelle Go publique reste en lecture seule. Le pilote de ce contrôle exerce le cycle de vie des processus et ne pilote pas encore une session réseau du produit. Les contrôles d'identité sont séquentiels : ils supposent que d'autres administrateurs ne reconfigurent pas ces espaces pendant l'essai. Le système, ses bibliothèques et son noyau restent des prérequis de confiance.

La panne forcée porte sur le pilote, pas sur la mort du superviseur ni la coupure machine. La synchronisation des preuves n'est pas une garantie générale de récupération après panne matérielle. Les adresses, routes, DNS, IPv6 du foyer, équité et bénéfice sous trafic ne sont pas évalués. `real_gateway_restoration_validated` reste faux. Les anciennes campagnes et leurs preuves figées restent distinctes et inchangées.

Vérification locale : 64 tests Python ciblés réussis (superviseur, TBF/CAKE, nouveau cycle, processus bornés et préparation), ainsi que la suite Go complète. Les nouveaux tests de cycle utilisent des namespaces simulés et de vrais processus/binaire Go ; les vérifications de descripteurs réseau en lecture seule et du relancement Python épinglé passent également. Le contrôle natif est refusé ici avant création de ressources, faute de privilèges de laboratoire. Aucune restauration réseau native n’est déclarée à cette étape.
