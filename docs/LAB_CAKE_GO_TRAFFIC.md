# Pilote de trafic après Go — disponibilité à accusé

## État et portée

Le pilote interne `scripts/lab_cake_go_traffic.py` et son entrée privée `scripts/lab-cake-go-traffic.py` sont implémentés. Les tests emploient de vrais processus, pipes, signaux et groupes Linux ; les exécutables réseau et leurs rapports sont simulés. Aucun namespace, socket ou qdisc réel n’est créé par ces tests.

Cette sous-étape suit l’[activation sur les ressources conservées](LAB_CAKE_GO_TOPOLOGY.md). Le [raccordement au propriétaire, la collecte CAKE et le rapport global](LAB_CAKE_GO_COLLECT.md) sont maintenant implémentés et testés avec réseau simulé ; la [première validation native combinée](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) est confirmée.

## Responsabilités

Le superviseur devra vérifier les outils/binaires et leurs empreintes, les ressources activées et le journal de provenance avant de lancer cette entrée dans le groupe neuf déjà réservé. Les options privées sont `--session-id`, `--client`, `--server`, `--ip` et `--binaries`. L’entrée résout les chemins et vérifie la présence des exécutables. Le contrôle combiné transmet aussi `--tools-json`, un inventaire privé lié à la session ; les empreintes et les quatre commandes fixes sont alors revérifiées avant chaque lancement. Les outils utilisent `/dev/null` en entrée. Ces contrôles ne remplacent pas la vérification d’identité et de provenance du superviseur.

Le pilote exige un jeton de huit caractères `[a-z0-9_]`, les noms exacts `cg-JETON-c` et `cg-JETON-s`, et sa position de leader d’un groupe/session distinct. Ces noms ne prouvent pas à eux seuls la possession des espaces. Il ne crée, n’active ni ne supprime d’espace et ne modifie aucune file.

`lab_active.measure_loaded` est réutilisé sans changement : cible TCP `10.203.0.6:46001`, réception de 8 388 608 octets sur `10.203.0.6:46002`, émetteur plafonné à 1 048 576 octets/s et dix sondes TCP. Les trois outils démarrent dans le groupe hérité. Aucun outil de sondage ne démarre avant l’accusé valide ; les deux pauses existantes conservent au moins une seconde après la première écriture avant les sondes.

## Dialogue sur pipes

Après `STARTED` de l’émetteur, le pilote vérifie que les trois outils sont vivants et appartiennent à son groupe. Il écrit une ligne sur stdout, dans l’ordre cible/récepteur/émetteur :

```text
READY {"schema_version":1,"kind":"lab_cake_go_active_ready","session_id":"traffic1","helper_pids":[101,102,103]}
```

Il attend ensuite cette unique ligne sur stdin :

```json
{"schema_version":1,"kind":"lab_cake_go_active_control","session_id":"traffic1","action":"continue"}
```

Chaque ligne se termine par LF. La borne de 1 024 octets inclut LF et l’éventuel préfixe `READY `. Les champs supplémentaires, clés dupliquées, mauvais types, mauvais jeton, PID booléens/non positifs/répétés, ligne tronquée, deuxième ligne ou dépassement sont refusés. Les lectures et écritures sont non bloquantes ; un accusé fragmenté reste accepté jusqu’à sa fin et dans le délai.

Un contrôle reçu avant l’annonce est refusé. EOF avant un accusé complet empêche les sondes. EOF après l’accusé complet clôt normalement ce canal à message unique. Toute donnée supplémentaire, même reçue pendant les pauses ou les sondes, provoque l’échec lors du contrôle suivant. Un message arrivé après la sortie du processus n’est plus observable ; le superviseur doit également imposer son propre automate.

## Résultat et bornes

Après récupération de ses outils, le pilote écrit une ligne JSON v1 `lab_cake_go_active_flow`, avec exactement `schema_version`, `kind`, `session_id` et `flow`. `flow` conserve les exports d’émission, réception et latence, le code de mesure et les indicateurs de réussite/recouvrement. `parse_flow` recalcule ces indicateurs avec les validateurs existants ; ils ne sont pas acceptés sur simple déclaration.

Un code pilote `0` signifie collecte complète et rapports compatibles. Les dix sondes peuvent avoir échoué : les tentatives et le code de mesure `1` restent alors visibles. La validation native positive exige séparément dix réussites et le recouvrement temporel. Aucun seuil de latence/débit ni bénéfice Coopace n’est qualifié ici.

| Borne | Valeur |
| --- | --- |
| Pilote, à partir de son runner | 45 s monotones |
| Annonce disponible, écriture comprise | 15 s au total |
| Écriture d’une ligne / attente de l’accusé | 5 s chacune, sous les autres échéances |
| Disponibilité de chaque outil | 5 s |
| Exécution des sondes | 16 s |
| Stdout total, annonce et résultat compris | 256 Kio |

Les erreurs n’émettent aucun résultat final de réussite. `SIGHUP`, `SIGINT` et `SIGTERM` enregistrent une interruption et conservent les codes 129/130/143 après arrêt des outils. Si le pilote reçoit `SIGKILL` pendant l’attente, les trois outils restent dans son groupe : le superviseur indépendant doit les arrêter et les récupérer avant de retirer les espaces. Le pilote ne publie aucun `cleanup_verified` des namespaces.

## Vérification et prochaine étape

`test_lab_cake_go_traffic.py` couvre dialogue normal/fragmenté, EOF avant/après accusé, trames invalides ou multiples, contrôle prématuré/tardif, blocage de stdout, limites de taille et délais. Les tests de processus vérifient l’absence du quatrième outil avant accord, la pause après première écriture, le refus d’un outil hors groupe ou arrêté, les signaux, un rapport de réception invalide et la conservation des échecs de sondes.

Un scénario tue réellement le seul pilote pendant l’attente : un superviseur subreaper récupère ses trois outils orphelins avec `lab_process_group.py`, sans récupérer le leader avant les derniers signaux collectifs. Les ressources et résultats réseau restent simulés ; ceci ne valide pas un transfert natif.

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go_traffic.py' -v
```

Première validation locale du 1er novembre 2026 : les dix tests dédiés passent ; la suite Python complète passe également, avec 159 tests en 251,403 s. Cette vérification conserve les limites de simulation décrites ci-dessus.

La [collecte combinée](LAB_CAKE_GO_COLLECT.md) raccorde maintenant ce pilote à la topologie activée avec preuves durables et contrôle du nettoyage global. Les deux contrôles natifs complets sont [validés sur une révision figée](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md).
