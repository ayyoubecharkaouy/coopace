# Scénario de laboratoire et référence initiale — étape 4.2

## État actuel

Cette étape prépare une expérience reproductible : un export local d'inventaire est disponible et un modèle de protocole peut être complété. Un premier scénario Linux virtuel est défini ; la plateforme du foyer, le chemin réel du trafic et les seuils restent à confirmer. Aucune référence WAN au repos/sous charge, aucune intervention sur le trafic du foyer et aucun résultat d'optimisation ne sont revendiqués.

Pour avancer sans détourner le trafic du foyer, un [scénario Linux virtuel](VIRTUAL_LAB.md) utilise des ressources réseau neuves et des sondes IPv4 synthétiques, avec nettoyage. Un [premier essai natif ICMP/TCP](VALIDATION_VIRTUAL_LAB_2026-10-29.md) a réussi sur le PC Linux utilisateur, avec inventaire complet dans cet espace, cinq connexions réussies sans échec et nettoyage normal. Des [séries avec transfert synthétique](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) sont également validées, sans saturation démontrée. Le [protocole de goulot contrôlé](VIRTUAL_BOTTLENECK.md) fixe les critères de l'expérience suivante ; sa mise en œuvre et les références WAN restent à réaliser. Ce choix de laboratoire ne fixe pas la plateforme d'une future passerelle du foyer.

Le diagnostic reste implémenté sous Linux uniquement. Le choix de cette plateforme pour le prototype n'impose pas Linux au produit final ; une passerelle Windows exige son diagnostic et son moteur spécifiques. Le [périmètre produit](PRODUCT.md) reste la référence.

## Conserver l'inventaire initial

Depuis la racine du dépôt Linux, sans élévation de privilèges :

```sh
mkdir -p .local/bin .local/experiments
sh scripts/go.sh build -o .local/bin/coopace-gateway ./apps/gateway/cmd/coopace-gateway
./.local/bin/coopace-gateway inspect --json > .local/experiments/inventory-before.json
```

Contrôler le code de sortie immédiatement après la commande (`echo $?` sous le shell). `0` signifie qu'un rapport a été produit, éventuellement partiel ; consulter `partial` et les rubriques avant de l'utiliser. Une annulation ou une erreur ne produit pas un inventaire complet exploitable. La redirection est volontaire ; le programme ne crée aucun fichier automatiquement.

L'option `--json` change uniquement le format de sortie. Elle utilise les mêmes lectures que [le diagnostic de l'étape 4.1](GATEWAY_DIAGNOSTIC.md), sans requête réseau active ni modification de configuration. La sortie standard contient un seul objet JSON, sans préambule texte ; les erreurs vont sur la sortie d'erreur.

### Format local v1

| Champ | Signification |
| --- | --- |
| `schema_version`, `kind` | `1` et `gateway_inventory`. Format indépendant du JSON de latence et du protocole réseau du groupe. |
| `coopace_version`, `os`, `architecture` | Version applicative et plateforme du programme exécuté. |
| `collected_at` | Date UTC de fin de collecte ; les lectures restent successives, sans instantané atomique. |
| `build.go_version` | Version Go incorporée au programme, si disponible. |
| `build.vcs`, `build.vcs_revision`, `build.vcs_modified` | Provenance incorporée lors de la compilation ; `null` lorsqu'elle manque. Le booléen faux signifie une compilation depuis un arbre connu sans modification locale, pas une absence d'information. |
| `scope`, `mode` | `process_network_namespace` et `read_only`. |
| `partial` | Vrai si au moins une rubrique de lecture est indisponible. Faux ne signifie pas que la topologie ou la couverture est validée. |
| `traffic_coverage`, `restoration` | `unverified` et `not_implemented` ; aucune aptitude à intervenir n'est déduite du rapport. |
| `inventory` | Interfaces, flags de forwarding, capacité effective, routes par défaut, files visibles et outils. |

Chaque rubrique de lecture contient `available`, `value` et, si indisponible, `reason`. Une donnée inconnue a `value: null`, un booléen connu peut être `false`, et une liste connue vide reste `[]`. Le motif est explicatif, sans vocabulaire d'erreurs normalisé. Les outils ont `name`, `available` et `path` ; le chemin est nul lorsque l'outil n'est pas disponible.

Les métadonnées viennent de [runtime/debug](https://pkg.go.dev/runtime/debug#BuildInfo). Leur présence dépend des conditions de compilation et de l'option [buildvcs de Go](https://pkg.go.dev/cmd/go#hdr-Compile_packages_and_dependencies). Elles décrivent le programme compilé, pas l'état actuel du dépôt au moment du diagnostic. Si elles manquent, consigner manuellement le commit et l'empreinte du binaire dans le protocole ; ne pas déduire un commit à partir de la seule version `dev`.

L'inventaire n'est pas une sauvegarde restaurable : options de files, classes, filtres, règles de pare-feu et configuration complète de routage ne sont pas conservés. Le rapport exclut les adresses IP/MAC des champs d'inventaire, conserve des noms d'interfaces et des chemins locaux, et n'est envoyé ni au groupe ni au ML.

## Compléter le protocole avant les mesures

Copier le [modèle d'expérience](templates/GATEWAY_EXPERIMENT.md) dans le dossier local :

```sh
cp docs/templates/GATEWAY_EXPERIMENT.md .local/experiments/scenario.md
```

Compléter d'abord la plateforme candidate et les éléments suivants :

1. Le schéma des liens, les appareils de test, le trafic couvert et le chemin observé séparément pour IPv4 et IPv6. Un PC connecté au routeur n'est pas automatiquement sur le chemin des autres appareils.
2. L'état initial, les éléments déjà inconnus, le commit ou le binaire utilisé et les fichiers de collecte associés.
3. La cible autorisée, la méthode, la charge contrôlée, la durée et le nombre de répétitions. Fixer ces paramètres avant de recueillir les mesures et consigner les autres usages connus.
4. Les critères d'acceptation et d'arrêt : latence sous charge, échecs, débit utile minimal, équité et ressources. Aucun seuil chiffré générique n'est imposé sans scénario ni référence réelle.
5. Le périmètre de restauration et la manière de la vérifier avant une première modification. Le choix entre maintien du passage et blocage en cas de panne doit être explicite.

Les champs non renseignés ou les observations indisponibles restent identifiés comme tels. Le protocole n'est pas « validé » tant que le chemin, les mesures et les seuils ne sont pas fixés. Ce modèle documentaire n'est pas chargé comme une configuration d'exécution.

## Recueillir la référence sans intervention Coopace

Une fois le protocole complété, conserver plusieurs séries au repos puis sous une charge connue lancée séparément. La commande `coopace latency` peut produire les premiers rapports TCP selon [LATENCY.md](LATENCY.md). Sa condition `idle` ou `loaded` est une déclaration ; elle ne détecte pas automatiquement la charge.

Ne pas assimiler ces durées d'établissement TCP à un RTT ICMP, à une perte de paquets ou à une gigue normalisée. Une comparaison ultérieure doit conserver la même méthode et la même cible, examiner les échecs et ajouter les métriques manquantes nécessaires à la question étudiée. Avec peu d'échantillons, p95/p99 ne constituent pas des estimations fiables de la distribution.

Le diagnostic `inspect --json` ne lance pas ces séries ni une charge de saturation. Aucun serveur, appareil de test ou outil de charge n'est sélectionné automatiquement à cette étape.

Après une collecte réelle, `coopace latency compare --idle FICHIER --loaded FICHIER` permet de comparer hors ligne les exports TCP v1. La sous-commande recalcule les statistiques, refuse les paramètres incompatibles et conserve les échecs et valeurs indisponibles ; voir [LATENCY.md](LATENCY.md#comparer-les-rapports-au-repos-et-sous-charge). Elle n'effectue aucune collecte et ne permet pas de clôturer l'étape 4.2 sans un scénario renseigné et des mesures réelles.

## Comparaison et restauration à préparer ensuite

L'expérience distinguera la configuration initiale, le moteur configuré manuellement et le pilotage Coopace sans ML. Les règles d'acceptation doivent être définies avant de comparer. Conserver les répétitions, les dégradations et les cas sans bénéfice ; ne pas sélectionner uniquement les meilleurs résultats.

Avant toute modification, la restauration doit couvrir les objets qui seront réellement modifiés, fonctionner indépendamment du processus de pilotage et être testée lors de son interruption, avec IPv4, IPv6 et DNS. Le modèle demande de consigner ces preuves ; aucun mécanisme de restauration n'est encore implémenté ou validé.

Les prochaines décisions dépendent de l'inventaire réel et du choix de la plateforme. Cette préparation ne remplace pas une expérience exécutée et n'autorise aucune intervention automatique.
