# Entrée interne CAKE et journal durable

## État

`apps/gateway/cmd/coopace-cake-worker` fournit l’entrée interne du contrôle DOWN sous Linux amd64. Elle assemble le [transport](LAB_CAKE_TRANSPORT.md), la session et le [backend natif borné](LAB_CAKE_BACKEND.md), avec journalisation synchronisée. L’application publique `coopace-gateway` conserve `inspect` et `plan` ; le processus interne n’est pas une commande d’application d’un scénario.

Les tests vérifient le cycle et les preuves avec une acceptation de namespace et des opérations simulées. Le binaire réel compilé est testé pour son aide et pour le refus natif de l’espace d’origine, sans appel externe. **L’intégration au superviseur Python est implémentée ; ses [deux contrôles natifs DOWN](VALIDATION_CAKE_GO_DOWN_2026-11-01.md) confirment ajout/relecture et nettoyage en fin normale et après SIGKILL.** Aucun vrai `ip`/`tc` ni changement réseau n’est lancé pendant ces tests.

## Entrées du lanceur

Le binaire attend exactement cinq options, sous la forme de paires nom/valeur : `--session-id`, `--ip`, `--ip-sha256`, `--tc`, `--tc-sha256`. Le jeton est celui de la réservation courante ; chemins absolus canoniques UTF-8 et empreintes SHA-256 minuscules sont requis. Champs inconnus, doublons, valeurs absentes et arguments supplémentaires sont refusés. Ces paramètres appartiennent au lancement de confiance, sans lecture d’un scénario `plan` ni repli sur PATH.

| Descripteur hérité | Rôle |
| --- | --- |
| 3 | Lecture du contrôle : initialisation, `apply`, `finish`. |
| 4 | Écriture des événements `ready` et `applied`. |
| 5 | Référence conservée de l’espace réseau cible. |
| 6 | Référence de l’espace réseau d’origine du superviseur. |
| 7 | Écriture du journal persistant. |

Le départ monotone est capturé dès `main`, avant l’initialisation. Les emplacements sont vérifiés avant le montage des I/O pollables et des signaux. Aucun numéro de descripteur, chemin d’espace ou chemin de journal ne provient du JSON de contrôle.

Le lanceur doit créer exclusivement le fichier du journal, hors de la réservation jetable, en mode `0600`, avec `O_WRONLY|O_APPEND`, puis synchroniser le fichier et son répertoire avant de démarrer l’enfant. Il ferme ensuite ses références d’écriture. L’héritage conserve le propriétaire du fichier, y compris lorsque l’enfant dispose de privilèges supplémentaires. Le processus Go ne crée ni ne recherche de fichier de preuves.

Le descripteur 7 doit désigner un fichier régulier vide, privé, avec un seul lien, ouvert en écriture seule et en ajout. Ces propriétés ne prouvent pas l’historique de création ni l’emplacement : le lanceur doit les établir et les conserver. Un journal existant non vide est refusé sans être écrasé. Les cinq références sont fermées après usage et marquées close-on-exec avant tout outil.

## Journal et ordre des preuves

`journal_linux.go` écrit des lignes JSON v1 `lab_cake_worker_journal`. Chaque ligne porte `session_id`, `sequence` croissante, `event`, `recorded_at` UTC, `elapsed_ns` monotone et `data`. Les champs sont distincts du protocole du groupe et des rapports de planification.

| Événement | Moment de synchronisation |
| --- | --- |
| `launch` | Avant toute opération externe ; version, provenance, PID, outils déclarés et identités des espaces observées lorsqu’elles sont disponibles. |
| `context_accepted` | Après validation de la session et liaison native au namespace. |
| `tool_intent` | Avant chaque appel d’outil ; chemin, empreinte et arguments fixes. |
| `tool_result` | Après récupération de l’outil ; PID/code disponibles, durée, sorties exactes et troncatures. |
| `ready`, `applied` | Avant l’événement correspondant sur le canal 4. |
| `apply_received`, `finish_received` | Après réception et validation de l’instruction, avant la suite. |
| `final_verified` | Après la dernière relecture conforme, sans attestation de nettoyage. |
| `worker_exit` | Code de sortie envisagé et état local ; aucune garantie sur la sortie OS ultérieure. |

Chaque ligne est complètement écrite, puis `File.Sync` est appelé avant de poursuivre. Une intention durable peut donc rester sans résultat si le processus est tué. stdout/stderr des outils sont encodés en base64, avec `null` si aucun tampon n’a été recueilli ; les octets conservés ne subissent aucune conversion de texte ou de nombre. Un préfixe tronqué conserve son indicateur, sans être présenté comme une sortie complète.

Le journal est limité à **8 Mio au total et 256 Kio par ligne**, saut de ligne inclus. Le budget des événements du canal 4 reste séparé : 128 Kio par événement, 512 Kio au total. Avant chaque écriture, identité du fichier, taille attendue, mode privé, lien unique et ajout sont revérifiés. Une erreur de sérialisation, budget, écriture ou synchronisation est permanente : aucun nouvel outil ni succès n’est autorisé ensuite.

`LabToolObserver` fournit les points d’écriture du backend. Une erreur d’intention empêche le lancement ; une erreur de résultat empêche `applied`, même si l’ajout a déjà pu avoir un effet. Les copies fournies à l’observateur ne peuvent pas modifier les arguments exécutés ou les traces en mémoire. L’entrée réelle impose cet observateur ; les anciens tests du backend peuvent rester sans journal.

La synchronisation régulière ne garantit pas une durée maximale d’un appel disque bloqué par l’hôte. Les délais du contrôle sont revérifiés après les écritures ; la récupération indépendante et les limites de panne de l’hôte restent celles du [contrat](LAB_CAKE_EXECUTOR.md).

## Sortie, signaux et nettoyage

Codes : `0` pour un cycle local terminé avec journal fermé sans erreur ; `2` pour lancement, descripteurs ou protocole incompatibles ; `1` pour erreur opérationnelle, délai ou journal défaillant. SIGHUP, SIGINT et SIGTERM annulent les canaux et opérations, avec codes 129, 130 et 143 lorsque le journal peut être clôturé. Une erreur de journal garde un code non nul.

`worker_exit.data.intended_exit_code` exprime l’intention avant fermeture finale et sortie OS. Un échec de fermeture ou SIGKILL peut encore modifier la sortie réelle. Le superviseur compare ce champ au code effectivement récupéré ; le journal seul ne démontre aucun succès global.

Les enregistrements conservent `cleanup: not_attested`, `traffic_generated: false` et `active_path_verified: false`. Un arrêt forcé peut laisser seulement un préfixe valide, sans `worker_exit`. Les fragments incomplets et l’absence de fin ne doivent jamais être reconstruits en succès. Le retrait des espaces, la récupération des descendants après mort du processus et la décision finale appartiennent au [superviseur raccordé](LAB_CAKE_GO_GUARD.md), dont les [contrôles natifs DOWN sont validés](VALIDATION_CAKE_GO_DOWN_2026-11-01.md).

## Vérification

```sh
sh scripts/go.sh test -count=1 -v ./platforms/linux ./apps/gateway/internal/labcontrol
sh scripts/go.sh test -race -count=1 ./platforms/linux ./apps/gateway/internal/labcontrol
```

Les tests contrôlent les options, les propriétés du journal, les budgets, les erreurs de synchronisation, l’absence de transmission du journal aux outils, les octets source et l’ordre des preuves. Les tests de processus couvrent fin normale, refus de contexte, signaux gérés et SIGKILL après `applied`, sans outil vivant à ce point. Ils ne démontrent pas la récupération d’un outil orphelin pendant son exécution.

La compilation et l’aide du processus sont vérifiables sans privilèges ; son lancement effectif nécessite les cinq références préparées par le lanceur. Les modes natifs du [superviseur](LAB_CAKE_GO_GUARD.md) sont implémentés ; leur [préparation figée et leur relecture](LAB_CAKE_GO_NATIVE.md) sont définies, avec [résultats natifs DOWN validés](VALIDATION_CAKE_GO_DOWN_2026-11-01.md). Le [raccordement au superviseur Python](LAB_CAKE_GO_GUARD.md) est maintenant implémenté et testé en simulation, avec contrôles historiques conservés. Le [contrat du contrôle Go puis trafic](LAB_CAKE_GO_ACTIVE.md) conserve ce cycle DOWN complet avant activation par le superviseur. La [phase Go et la gestion des groupes](LAB_CAKE_GO_PHASE.md) sont maintenant implémentées et testées en simulation ; l’[activation et les relectures de continuité](LAB_CAKE_GO_TOPOLOGY.md) sont également implémentées en simulation ; la suite développe le pilote de trafic à accusé.
