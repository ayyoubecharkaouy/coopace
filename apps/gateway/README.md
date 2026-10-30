# Application passerelle

État : diagnostic en lecture seule implémenté sous Linux et commande de simulation CAKE statique disponible sans collecte réseau. L'environnement isolé produit un rapport partiel, Netlink étant interdit ; un [inventaire complet dans la passerelle virtuelle](../../docs/VALIDATION_VIRTUAL_LAB_2026-10-29.md) est validé sur le PC utilisateur. L'inventaire du réseau du foyer reste à consigner. Gestion des files, routage, activation et restauration ne sont pas implémentés dans cette application.

Cette application Go fournit d'abord l'inventaire local. Elle accueillera le pilotage de l'observation et de la gestion du trafic qui traverse réellement la passerelle, avec les règles du noyau et l'adaptation du système pour appliquer des politiques autorisées, en évaluer les effets et restaurer la configuration.

```text
gateway/
├── cmd/coopace-gateway/     # Point d'entrée de la commande dédiée
└── internal/
    ├── cli/                # Commandes inspect/plan et affichage
    ├── diagnostic/         # Inventaire et adaptation système
    ├── planning/           # Scénario local et simulation sans collecte
    └── buildinfo/          # Provenance du binaire, partagée sans inventaire
```

Depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
```

Cette commande ne démarre aucun service et ne modifie aucune configuration. Les données indisponibles restent explicites ; aucun outil trouvé ni réglage actif ne suffit à déclarer la passerelle prête. Le [diagnostic, les sources et le protocole préalable aux interventions](../../docs/GATEWAY_DIAGNOSTIC.md) décrivent les limites et les prochaines validations.

`inspect --json` émet un inventaire local v1 sur stdout, avec valeurs inconnues à `null`, horodatage UTC et provenance de compilation disponible. Les types d’export restent dans `internal/diagnostic`, séparés des modèles du noyau et du protocole réseau. La lecture de provenance est partagée via `internal/buildinfo`. Le [protocole de référence initiale](../../docs/GATEWAY_BASELINE.md) et son modèle préparent l’étape 4.2 ; la plateforme du foyer et les références WAN restent à confirmer.

Les outils de `scripts/` ont leur propre cycle de vie : connectivité, transfert, séries synthétiques et [supervision indépendante](../../docs/LAB_GUARD.md). Leurs validations ne changent pas les capacités de cette application et ne constituent pas une restauration de passerelle réelle.

Le moteur réseau dépendra du système : CAKE/SQM est envisagé sous Linux ; une passerelle Windows exige une intégration et une validation spécifiques. Les privilèges et leur séparation restent à définir.

La [première planification CAKE statique hors ligne](../../docs/STATIC_CAKE_PLANNING.md) est implémentée et testée dans le noyau Go. La [commande `plan --scenario FICHIER [--json]`](../../docs/GATEWAY_PLANNING.md) réalise maintenant ce raccordement : scénario local de 16 Kio maximum, validation stricte, motifs et provenance sur stdout. Elle ne réalise aucune collecte ni application réseau. L’exécuteur supervisé reste à développer.
