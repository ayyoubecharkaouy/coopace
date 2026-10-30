# Première planification CAKE statique — contrat hors ligne v1

## État et objectif

`packages/core/cake_plan.go` fournit `PlanStaticCake`, une fonction Go pure, testée sans réseau. Elle transforme des hypothèses explicites en recommandation : proposer la référence du laboratoire, conserver une référence déjà conforme ou s'abstenir. Elle prépare l'intégration du moteur CAKE existant après la [comparaison native TBF/CAKE](VALIDATION_CAKE_COMPARISON_2026-10-30.md).

Cette sous-étape appartient à la préparation de l'étape 4.2. La CLI passerelle conserve seulement `inspect` ; aucun exécuteur, nouvelle commande, réglage réseau ou contrôleur adaptatif n'est ajouté. L'étape 5 de coordination et le ML restent différés. Le gain d'une surcouche Coopace devra être évalué séparément de la référence CAKE.

## Référence et périmètre

L'identifiant `cake-ipv4-lab-4mbit-v1` désigne **le profil complet** déjà évalué : `bandwidth 4mbit`, `besteffort`, `flows`, `nonat`, `nowash`, `raw`, `mpu 0`, `rtt 100ms`, `split-gso`, `no-ack-filter`, `egress`, `memlimit 1048576`, `fwmark 0`. Ses paramètres restent ceux du [protocole comparatif](CAKE_COMPARISON.md).

Ce débit appartient au laboratoire IPv4 synthétique. Il n'est ni une valeur par défaut pour le foyer ni une estimation de capacité WAN. La recommandation retourne l'identifiant de référence, sans sélectionner d'interface ni fabriquer de commande shell. Le futur adaptateur devra résoudre cet identifiant vers exactement ce profil et en relire les options effectives.

Le seul périmètre pouvant produire une proposition est `owned_ipv4_lab` : ressources jetables possédées, passage IPv4 vérifié et supervision du nettoyage. `existing_gateway` et un périmètre absent donnent une abstention, y compris lorsque tous les autres prérequis sont déclarés vrais. Une valeur de périmètre inconnue est une erreur de contrat.

## Entrées et décisions

L'appelant fournit `CakePlanningInput` : périmètre, état évalué de la file et six prérequis. Ces données sont des hypothèses de planification ; la fonction ne collecte ni ne prouve leur véracité.

| État de file dans le laboratoire | Recommandation |
| --- | --- |
| Absent ou `unknown` | `abstain`, motif `queue_not_assessed`. |
| `other_configuration` | `abstain`, motif `other_configuration_preserved` ; aucun remplacement proposé. |
| `reference_conformant` | `keep_reference`, avec l'identifiant du profil ; aucune nouvelle modification proposée. |
| `unconfigured` et prérequis incomplets | `abstain`, sans identifiant de profil ; tous les prérequis non confirmés sont expliqués. |
| `unconfigured` et six prérequis confirmés | `propose_reference`, avec l'identifiant du profil du laboratoire. |

Une file de type `cake` dans l'inventaire ne suffit pas à déclarer `reference_conformant` : l'adaptateur devra avoir vérifié le profil entier, sa racine et sa portée. Une file différente reste préservée, même si les prérequis sont confirmés. Un état non reconnu est une erreur, sans recommandation utilisable.

Les six prérequis de `CakePlanningChecks` sont, dans l'ordre stable des motifs : référence validée, accord local pour l'intervention envisagée, chemin de trafic validé, propriété des ressources validée, supervision prête et permissions vérifiées. Une valeur fausse signifie **non confirmé**, sans remplacer une observation indisponible par un constat technique négatif. Les motifs restent distincts.

Le consentement local d'intervention est séparé de l'adhésion au groupe, du partage des observations et du relais. La planification ne déduit aucun de ces accords de `GroupConsent`, d'un rôle, d'une capacité déclarée, d'un outil trouvé, du forwarding ou de privilèges observés. L'inventaire actuel n'est pas automatiquement convertible en autorisation.

`keep_reference` exprime uniquement l'absence d'une nouvelle modification proposée sur un profil déclaré conforme. Ce n'est pas la gestion d'une session active : expiration, révocation, incident et restauration appartiendront à un cycle de vie distinct. Un exécuteur devra revérifier les faits récents, la propriété et l'accord local avant toute action. Un ancien résultat `propose_reference` ne pourra pas servir de jeton d'autorisation.

## Organisation et vérification

Le modèle et la règle restent dans le même paquet `core`, dans `cake_plan.go` ; leurs tests et l'exemple sont dans `cake_plan_test.go`. Aucun format JSON ou message de groupe n'est défini par ces types, conformément aux [frontières du projet](ARCHITECTURE.md). L'entrée n'est pas modifiée ; chaque résultat possède ses propres motifs.

```sh
sh scripts/go.sh test -count=1 -v ./packages/core
```

Les tests vérifient les valeurs par défaut, les six prérequis séparément, leurs motifs cumulés, les périmètres absents/réels, les files inconnues ou différentes, la conservation du profil conforme, les valeurs de contrat invalides et l'absence de contamination entre évaluations. La suite Go, `go vet` et les compilations Linux et Windows amd64 passent. Cela valide une règle hors ligne, pas une activation native de CAKE depuis Go.

## Sous-étape suivante

Raccorder ce planificateur à un scénario local explicitement déclaré dans l'application passerelle, avec lecture bornée, validation stricte, motifs et provenance sur stdout. Ce mode de simulation devra rester distinct d'un exécuteur privilégié et de l'inventaire en lecture seule. Il permettra d'examiner les propositions et abstentions avant de développer l'application du profil dans le laboratoire supervisé.

Avant tout réseau réel : définir le profil à partir de son scénario et de ses mesures, la couverture IPv4/IPv6/DNS, le consentement local persistant et révocable, les limites de durée et la restauration indépendante vérifiée. Les conditions du [produit](PRODUCT.md#conditions-de-poursuite) continuent de s'appliquer : garder une intégration simple si le moteur existant suffit et différer l'automatisation lorsque ces prérequis ne sont pas maîtrisés.
