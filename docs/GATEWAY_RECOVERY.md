# Préparer et contrôler le retour aux files initiales

État : enregistrement de captures, import strict, évaluation du profil `noqueue-root-v1` et comparaison de deux observations implémentés. Les commandes sont utilisables depuis la CLI publique et ne modifient pas le réseau. Le [moteur supervisé de laboratoire](LAB_QUEUE_RECOVERY.md) est implémenté et ses [deux cycles natifs sont validés](VALIDATION_QUEUE_RECOVERY_2026-11-12.md). L'exécuteur de restauration du foyer reste à développer.

Cette étape exploite la [capture locale confirmée sur `wlp3s0`](VALIDATION_GATEWAY_SNAPSHOT_2026-11-12.md). Le logiciel sait maintenant reconnaître un premier état initial, refuser les dépendances non prises en charge et vérifier si une observation ultérieure correspond aux champs sélectionnés de cet état.

La commande directe `restore-plan --interface wlp3s0` est également confirmée par le retour utilisateur du 12 novembre 2026 : profil `noqueue-root-v1` reconnu, candidat aux essais de restauration. La collecte et l'évaluation en lecture seule fonctionnent ensemble sur ce PC ; l'enregistrement avec `--output`, la comparaison native et l'exécution de restauration restent à confirmer séparément.

## Utilisation sur le PC utilisateur

Évaluation immédiate, sans fichier et sans `sudo` :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway restore-plan --interface wlp3s0
```

Pour conserver une référence et contrôler une observation ultérieure :

```sh
mkdir -p .local/checkpoints
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --interface wlp3s0 --output .local/checkpoints/wifi-before.json
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway restore-plan --snapshot .local/checkpoints/wifi-before.json
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway restore-check --before .local/checkpoints/wifi-before.json --interface wlp3s0
```

Choisir un nouveau nom pour chaque référence : `--output` refuse un fichier existant, y compris un lien symbolique. Il produit toujours un fichier JSON, indépendamment du format affiché sur stdout ; `--json` reste facultatif pour l'affichage. Le fichier temporaire privé est écrit, synchronisé et fermé avant publication par lien dur, sans écrasement. Les permissions sont `0600` sous Linux. Cette publication n'est pas un journal de récupération ni une garantie de persistance de l'entrée du répertoire après une coupure machine. Une erreur d'affichage peut survenir après l'enregistrement réussi du fichier.

La dernière commande effectue uniquement une nouvelle collecte et une comparaison. Sans intervention entre les observations, un résultat positif indique une stabilité des champs contrôlés ; il ne démontre pas qu'une restauration a eu lieu.

Les deux opérations peuvent aussi fonctionner hors ligne :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway restore-plan --snapshot docs/examples/queue-snapshot-noqueue.json --json
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway restore-check --before AVANT.json --after APRES.json --json
```

`AVANT.json` et `APRES.json` sont à remplacer par deux captures réelles distinctes. Le fichier `docs/examples/queue-snapshot-noqueue.json` est un exemple synthétique anonymisé, avec version `example-simulated` ; il ne rapporte aucune exécution native.

## Profil pris en charge pour l'évaluation

`noqueue-root-v1` nécessite les six sections disponibles, une seule racine `noqueue`, handle `0:`, des options présentes et vides, aucune classe ni aucun filtre dans les trois sélections. Le lien doit annoncer `noqueue` et son adresse matérielle doit correspondre à l'identité relevée.

Les champs de qdisc autorisés sont `kind`, `handle`, `root`, `dev`, `options`, `refcnt`, `bytes`, `packets`, `drops`, `overlimits`, `requeues`, `backlog` et `qlen`. Les compteurs présents doivent être des entiers uint64. Un parent, un bloc partagé, des options supplémentaires ou un autre champ non reconnu entraînent un refus. CAKE déjà présent, TBF, fq_codel, mq et les hiérarchies de classes ne sont pas pris en charge par cette première évaluation.

Un profil reconnu donne `candidate_for_lab_validation`, avec les étapes prévues et les prérequis non vérifiés : ressources possédées, continuité du namespace, outils épinglés, journal durable, superviseur indépendant et essais natifs de fin normale/panne. Les conditions réelles de couverture et de consentement restent également ouvertes. Un profil non pris en charge donne `refused`, avec un motif explicite. Un candidat n'est pas déclaré restaurable sur le réseau réel.

Le [code du noyau Linux](https://github.com/torvalds/linux/blob/v6.12/net/sched/sch_generic.c#L1100) choisit les files par défaut en fonction de l'interface ; la [suppression d'une qdisc](https://github.com/torvalds/linux/blob/v6.12/net/sched/sch_api.c#L1477) passe par son propre cycle de remplacement. Supprimer une future file Coopace ne suffit donc pas à prouver le retour à `noqueue` sur tout appareil. Le plan impose une nouvelle capture et une comparaison après l'opération ; aucune commande de suppression n'est exécutée ou autorisée par ces évaluateurs.

## Comparaison

| Décision | Signification |
| --- | --- |
| `selected_state_matches` | Deux observations cohérentes, avec la seconde postérieure à la première, présentent la même identité, le même MTU/flags et le profil noqueue attendu avec les listes sélectionnées vides. |
| `mismatch` | Une identité, un état de lien ou une configuration de file/dépendance a changé. |
| `indeterminate` | Référence non prise en charge, seconde capture partielle, observations identiques ou chronologie insuffisante. |

La comparaison ignore uniquement les statistiques de qdisc (compteurs, jauges `backlog`/`qlen`) et `refcnt` parmi les champs de qdisc acceptés. Les empreintes SHA-256 portent sur les octets exacts des captures ; deux copies du même fichier ne prouvent pas un retour à l'état initial. La continuité du namespace n'est pas attestée par les captures actuelles. Les snapshots restent séquentiels et ne couvrent pas tout le routage, les filtres partagés, IPv6, DNS, pare-feu et services externes.

Les rapports JSON v1 `queue_recovery_plan` et `queue_recovery_check` contiennent les motifs, la référence et l'observation par empreinte, la plateforme de l'évaluateur et les limites. `execution_authorized` et `network_changes_executed` restent faux ; `restoration` vaut `not_implemented`, `namespace_continuity` et `traffic_coverage` valent `unverified`. Un fichier modifié ou synthétique n'est pas authentifié par son empreinte.

## Import, codes et vérification

L'import accepte des fichiers ordinaires sans lien symbolique, limités à 8 Mio, contenant un unique JSON UTF-8 v1, de profondeur totale limitée à seize, sans clé dupliquée ni nombre non fini. Les métadonnées ont des noms exacts, des champs requis et des types contrôlés ; les clés propres aux producteurs restent conservées dans les valeurs. Les six commandes, leur ordre, l'interface, les horaires, les disponibilités et les preuves éventuelles de classes vides sont vérifiés. Les entiers uint64 gardent leur précision. Une capture valide mais partielle peut être importée ; elle ne devient pas candidate à une restauration.

Les codes du binaire sont `0` pour un candidat ou une correspondance des champs sélectionnés, `3` pour un refus/écart/résultat indéterminé valide, `2` pour les arguments invalides, `1` pour une erreur de fichier, de collecte ou d'écriture, et `130` pour une annulation. L'aide retourne `0`. `go run` peut traduire les codes du binaire en son propre code ; lire aussi sa ligne `exit status`.

Les tests couvrent import/export, preuves incohérentes, limites, compteurs élevés, refus de dépendances, différences de configuration, observations identiques, chronologie, annulation, erreurs de fichiers et sorties, enregistrement exclusif et parcours CLI hors ligne ou avec collecteur simulé. L'[exécuteur de laboratoire](LAB_QUEUE_RECOVERY.md) implémente l'installation possédée, le retrait ciblé, la nouvelle capture et le contrôle de l'état initial après fin normale puis panne du pilote. Ses tests utilisent du réseau simulé et de vrais processus ; ses [deux essais natifs sont également validés](VALIDATION_QUEUE_RECOVERY_2026-11-12.md). L'étape 4.2 reste ouverte pour le réseau réel.

Vérification du 12 novembre 2026 : tests ciblés sans cache, suite Go complète, `go vet ./...` et compilation Windows amd64 réussis. Cinq parcours du binaire Linux sur des captures synthétiques confirment les décisions candidat/correspondance/écart/indéterminé/refus et leurs codes de sortie. Le parcours capture → enregistrement → plan → comparaison est testé avec un collecteur simulé ; aucun essai natif de restauration n’est déclaré par ces contrôles.

Le retour terminal utilisateur de `restore-plan --interface wlp3s0`, reçu ensuite, affiche le candidat attendu et l'empreinte de référence `cab95fdbe13a538b15568bef4a99cbb4c7e42b5294e6ad9260fe3901076069e4`. Il conserve les limites « restauration réseau non implémentée » et « continuité de l'espace réseau et couverture du foyer non établies ». La capture complète correspondant à cette empreinte et le code de sortie ne sont pas fournis dans ce retour ; l'empreinte est transcrite, sans relecture indépendante de son fichier source. Le commit du dépôt au moment de la consignation est `31f0740`, sans attestation de révision du programme par cette sortie texte.

Le [premier pilotage de session Go](GATEWAY_SESSION.md) réutilise maintenant cet import et cette comparaison dans le dialogue avec le superviseur de restauration. Il lie les décisions à la capture initiale et à l'accord local, sans ajouter d'opération réseau aux commandes publiques. Tests en simulation réussis ; [deux essais natifs du raccordement validés](VALIDATION_GATEWAY_SESSION_2026-11-14.md), avec retour à noqueue puis nettoyage.
