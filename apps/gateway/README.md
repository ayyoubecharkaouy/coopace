# Application passerelle

État : diagnostic en lecture seule implémenté sous Linux et commande de simulation CAKE statique disponible sans collecte réseau. L'environnement isolé produit un rapport partiel, Netlink étant interdit ; un [inventaire complet dans la passerelle virtuelle](../../docs/VALIDATION_VIRTUAL_LAB_2026-10-29.md) est validé sur le PC utilisateur. L'inventaire du réseau du foyer reste à consigner. Le backend du contrôle CAKE DOWN est assemblé en privé et testé avec des outils simulés ; un [processus interne avec journal durable](../../docs/LAB_CAKE_ENTRY.md) est disponible pour le futur lanceur supervisé. La gestion du trafic du foyer, le routage, l’activation et la restauration ne sont pas implémentés.

Cette application Go fournit d'abord l'inventaire local. Elle accueillera le pilotage de l'observation et de la gestion du trafic qui traverse réellement la passerelle, avec les règles du noyau et l'adaptation du système pour appliquer des politiques autorisées, en évaluer les effets et restaurer la configuration.

```text
gateway/
├── cmd/
│   ├── coopace-gateway/     # Commandes publiques inspect/plan
│   └── coopace-cake-worker/ # Processus interne du contrôle DOWN
└── internal/
    ├── cli/                # Commandes inspect/plan et affichage
    ├── diagnostic/         # Inventaire et adaptation système
    ├── planning/           # Scénario local et simulation sans collecte
    ├── labcontrol/         # Session, transport et assemblage du backend DOWN
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

La [première planification CAKE statique hors ligne](../../docs/STATIC_CAKE_PLANNING.md) est implémentée et testée dans le noyau Go. La [commande `plan --scenario FICHIER [--json]`](../../docs/GATEWAY_PLANNING.md) réalise maintenant ce raccordement : scénario local de 16 Kio maximum, validation stricte, motifs et provenance sur stdout. Elle ne réalise aucune collecte ni application réseau. Le [contrat de l’exécuteur supervisé](../../docs/LAB_CAKE_EXECUTOR.md) est maintenant défini pour un premier contrôle CAKE sur lien DOWN ; le [catalogue et les validateurs purs côté Go](../../docs/CAKE_GO_VALIDATION.md) sont maintenant implémentés dans l’adaptation Linux. Le [contexte de session interne](../../docs/LAB_CAKE_CONTEXT.md) est maintenant implémenté et testé dans `internal/labcontrol`. Le [transport hérité et le pilote privé](../../docs/LAB_CAKE_TRANSPORT.md) sont testés avec de vrais processus et outils simulés. Le [backend natif borné](../../docs/LAB_CAKE_BACKEND.md) est maintenant implémenté dans `platforms/linux` et assemblé en privé par `internal/labcontrol/native_linux.go`, avec tests utilisant des outils simulés. L’[entrée interne et le journal durable](../../docs/LAB_CAKE_ENTRY.md) sont maintenant livrés dans `cmd/coopace-cake-worker` et `internal/labcontrol`. Le [raccordement au superviseur](../../docs/LAB_CAKE_GO_GUARD.md) est maintenant testé avec des opérations simulées ; les [contrôles natifs DOWN sont validés](../../docs/VALIDATION_CAKE_GO_DOWN_2026-11-01.md) en fin normale et après SIGKILL ; la CLI publique conserve `inspect` et `plan`.

Le [contrat Go puis trafic](../../docs/LAB_CAKE_GO_ACTIVE.md) conserve le processus Go DOWN actuel : il termine avant activation des mêmes ressources par le superviseur. La [phase Go et la gestion des groupes](../../docs/LAB_CAKE_GO_PHASE.md) sont maintenant extraites et testées avec ressources simulées ; [activation et relectures de continuité](../../docs/LAB_CAKE_GO_TOPOLOGY.md) implémentées et testées en simulation ; pilote de trafic et collecte combinée restent à développer ; les commandes publiques `inspect` et `plan` gardent leur périmètre.
