# Application passerelle

État : premier diagnostic en lecture seule implémenté à l'étape 4.1 sous Linux. Gestion des files, routage, activation et restauration non implémentés. Le lancement réel dans l'environnement isolé produit un rapport partiel, Netlink étant interdit ; l'inventaire complet sur le PC utilisateur reste à confirmer.

Cette application Go fournit d'abord l'inventaire local. Elle accueillera le pilotage de l'observation et de la gestion du trafic qui traverse réellement la passerelle, avec les règles du noyau et l'adaptation du système pour appliquer des politiques autorisées, en évaluer les effets et restaurer la configuration.

```text
gateway/
├── cmd/coopace-gateway/     # Point d'entrée de la commande dédiée
└── internal/
    ├── cli/                # Commande inspect et affichage du rapport local
    └── diagnostic/         # Orchestration et sélection de l'adaptateur système
```

Depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
```

Cette commande ne démarre aucun service et ne modifie aucune configuration. Les données indisponibles restent explicites ; aucun outil trouvé ni réglage actif ne suffit à déclarer la passerelle prête. Le [diagnostic, les sources et le protocole préalable aux interventions](../../docs/GATEWAY_DIAGNOSTIC.md) décrivent les limites et les prochaines validations.

Le moteur réseau dépendra du système : CAKE/SQM est envisagé sous Linux ; une passerelle Windows exige une intégration et une validation spécifiques. Les privilèges et leur séparation restent à définir.
