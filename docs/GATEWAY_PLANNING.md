# Simulation locale de la planification CAKE

## Commande et état

`coopace-gateway plan --scenario FICHIER [--json]` raccorde la [règle du noyau](STATIC_CAKE_PLANNING.md) à l'application passerelle. La commande évalue un scénario déclaré, affiche ses motifs et sa provenance, puis termine. Elle n'appelle ni le diagnostic système, ni les outils réseau, ni les pilotes de laboratoire. Aucun profil n'est appliqué.

Cette sous-étape prépare l'intégration du profil CAKE statique évalué dans le laboratoire IPv4. Le contrat JSON local est indépendant de l'inventaire passerelle et des messages du groupe. La lecture des scénarios et la simulation fonctionnent sans privilèges ; une compilation Windows ne constitue pas une validation native de CAKE sur Windows.

Depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway plan --scenario docs/examples/cake-plan-propose.json
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway plan --scenario docs/examples/cake-plan-abstain.json --json
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway plan --scenario docs/examples/cake-plan-keep.json
```

Les trois [exemples](examples/cake-plan-propose.json) sont fictifs : ils démontrent proposition, [abstention](examples/cake-plan-abstain.json) et [conservation](examples/cake-plan-keep.json). Les valeurs `true` n'attestent ni les permissions de la machine, ni un accord utilisateur réel, ni la présence d'un laboratoire. Elles restent des hypothèses déclarées jusque dans la sortie. Un résultat de simulation n'est pas une autorisation d'exécution.

## Scénario local v1

Le fichier doit être ordinaire, sans lien symbolique, en JSON UTF-8 valide et d'au plus **16 384 octets**, espaces compris. La lecture reste bornée si le fichier grandit. Les clés inconnues, dupliquées ou non canoniques, les valeurs nulles requises, types incorrects, documents concaténés et imbrications excessives sont refusés. Le lecteur vérifie l'annulation avant et après chaque lecture ; il ne fournit pas une échéance stricte pour un stockage bloqué.

Tous les champs suivants sont requis, y compris chaque booléen lorsque sa valeur est fausse :

| Champ | Valeur et portée |
| --- | --- |
| `schema_version` | Entier `1`. |
| `kind` | `static_cake_scenario`. |
| `scope` | `owned_ipv4_lab`, `existing_gateway` ou chaîne vide explicitant un périmètre inconnu. Seul le premier peut proposer le profil du laboratoire. |
| `queue` | `unconfigured`, `reference_conformant`, `other_configuration`, `unknown` ou chaîne vide explicitant une file non évaluée. |
| `checks.reference_validated` | Référence déclarée validée pour le scénario. |
| `checks.local_consent` | Accord local déclaré pour l'intervention envisagée, distinct des accords de groupe. |
| `checks.path_validated` | Chemin de trafic déclaré vérifié. |
| `checks.ownership_validated` | Propriété des ressources jetables déclarée vérifiée. |
| `checks.supervision_ready` | Supervision du nettoyage déclarée prête. |
| `checks.permissions_checked` | Permissions déclarées vérifiées. |

Une omission ou `null` produit une erreur de fichier, sans recommandation. Une valeur fausse reste explicitement non confirmée. Une file inconnue ou différente entraîne une abstention ; une référence déclarée conforme produit `keep_reference`. Dans le laboratoire, une file non configurée exige les six prérequis pour produire `propose_reference`. Une passerelle existante reste hors du périmètre de proposition, même avec six valeurs vraies.

## Sortie et codes

Par défaut, la sortie texte présente la décision, le profil éventuel, des motifs en français, l'empreinte du scénario et la version du programme. `--json` écrit un seul objet JSON v1 `static_cake_plan` sur stdout ; les erreurs vont sur stderr.

| Champ de sortie | Signification |
| --- | --- |
| `mode`, `basis` | Toujours `simulation` et `declared_scenario`. |
| `execution_authorized` | Toujours `false`, y compris pour une proposition. |
| `decision`, `reference`, `reasons` | Décision du noyau, identifiant de référence ou `null` en cas d'abstention, motifs dans leur ordre stable. |
| `scenario` | Hypothèses complètes décodées, avec les valeurs fausses conservées. |
| `scenario_sha256`, `scenario_bytes` | Empreinte SHA-256 des octets exacts du fichier, espaces inclus, et volume effectivement lu. Le chemin local n'est pas exporté. |
| `evaluated_at` | Date UTC de l'évaluation. |
| `coopace_version`, `os`, `architecture` | Version applicative et plateforme du programme de simulation ; aucun support réseau cible n'en est déduit. |
| `build` | `go_version`, `vcs`, `vcs_revision`, `vcs_modified` incorporés au binaire. Une valeur absente est `null` ; un arbre connu propre conserve `false`. |

Le profil éventuel reste `cake-ipv4-lab-4mbit-v1`. Le programme ne choisit pas d'interface, ne mesure aucune capacité WAN et ne génère aucune commande d'application. La référence évaluée à 4 Mbit/s ne devient pas un réglage par défaut du foyer.

Une simulation valide sort avec `0`, qu'elle propose, conserve ou s'abstienne. Arguments invalides : `2` ; fichier invalide/inaccessible ou erreur de sortie : `1` ; annulation par le contexte : `130`. Aucun fichier de résultat n'est créé automatiquement et le scénario n'est pas modifié. Une redirection shell peut conserver le résultat explicitement.

## Organisation et vérification

`apps/gateway/internal/planning/scenario.go` porte la lecture et le contrat local ; `report.go` orchestre la règle et exporte le rapport. `internal/cli/plan.go` porte les arguments et l'affichage. `internal/buildinfo` partage uniquement la provenance du binaire avec le diagnostic, sans lancer un inventaire. Le noyau et le protocole du groupe gardent leurs formats et dépendances.

```sh
sh scripts/go.sh test -count=1 -v ./apps/gateway/... ./packages/core
```

Les tests couvrent les trois décisions, l'abstention pour une passerelle existante, les champs requis, refus de JSON ambigu, limites de lecture, annulation, intégrité du scénario, erreurs de sortie, provenance et absence de collecte du diagnostic. Les tests Go, l'analyse statique et les compilations Linux/Windows sont distincts des validations natives privilégiées du moteur.

La prochaine sous-étape devra définir le contrat d'un exécuteur limité au laboratoire supervisé : résolution exacte du profil, faits récents, accord local effectif, propriété, supervision et relecture après ajout. La restauration d'une passerelle réelle, la couverture IPv4/IPv6/DNS et le coût système restent des prérequis à l'automatisation sur ce réseau.
