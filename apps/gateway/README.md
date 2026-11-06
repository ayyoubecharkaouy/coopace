# Application passerelle

État : diagnostic Linux `inspect`, capture détaillée `snapshot` et simulation CAKE statique `plan` disponibles. La gestion du trafic du foyer, son routage et la restauration de sa configuration ne sont pas implémentés. Le laboratoire possède son propre superviseur et ses validations natives ; il reste distinct de ces commandes publiques.

Cette application Go assemble l'observation locale et les adaptations du système. Elle accueillera les interventions autorisées sur le trafic qui traverse réellement la passerelle, leur évaluation et le retour à la configuration précédente.

```text
gateway/
├── cmd/
│   ├── coopace-gateway/     # Commandes publiques inspect/snapshot/plan
│   └── coopace-cake-worker/ # Processus interne Go sur lien DOWN
└── internal/
    ├── cli/                # Arguments et affichage des commandes publiques
    ├── diagnostic/         # Inventaire réduit et adaptation système
    ├── snapshot/           # Capture détaillée locale des files et export
    ├── planning/           # Scénario local et simulation sans collecte
    ├── labcontrol/         # Session, transport, journal et backend DOWN
    └── buildinfo/          # Provenance du binaire, sans inventaire
```

Depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect --json
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway snapshot --help
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway plan --scenario docs/examples/cake-plan-propose.json
```

`inspect` inventorie les interfaces visibles, le forwarding, les permissions, les outils, les routes par défaut et les types de files. `inspect --json` émet l'inventaire local v1 réduit, avec valeurs inconnues à `null` et provenance disponible. L'[inventaire complet du laboratoire virtuel](../../docs/VALIDATION_VIRTUAL_LAB_2026-10-29.md) est validé ; celui du foyer reste à consigner. Les sources et limites figurent dans [GATEWAY_DIAGNOSTIC.md](../../docs/GATEWAY_DIAGNOSTIC.md).

[`snapshot --interface NOM [--json]`](../../docs/GATEWAY_SNAPSHOT.md) observe explicitement une interface Linux : détails du lien, qdisc, classes et filtres racine/ingress/egress. Les options JSON restent locales et peuvent contenir des adresses et identifiants. Les lectures sont successives, bornées et non exhaustives ; elles ne constituent pas une sauvegarde restaurable. Les tests utilisent des sources simulées ; la collecte complète sur l'interface du foyer reste à effectuer.

[`plan --scenario FICHIER [--json]`](../../docs/GATEWAY_PLANNING.md) applique la [règle Go de planification statique](../../docs/STATIC_CAKE_PLANNING.md) à un scénario déclaré strict, de 16 Kio maximum. Elle propose le profil du laboratoire, conserve la référence ou s'abstient. Elle n'effectue aucune collecte ni application réseau.

Ces commandes ne démarrent aucun service et n'enregistrent pas de rapport automatiquement. Aucune interface WAN, couverture du trafic ou autorisation d'intervention n'est déduite d'un inventaire. Le [protocole de référence initiale](../../docs/GATEWAY_BASELINE.md) définit les preuves restant à recueillir avant une intervention réelle.

Le processus privé `coopace-cake-worker` appartient au [contrôle supervisé CAKE](../../docs/LAB_CAKE_GO_GUARD.md), avec session, outils épinglés et journal durable. Ses [contrôles natifs DOWN](../../docs/VALIDATION_CAKE_GO_DOWN_2026-11-01.md), le [passage IPv4 puis trafic](../../docs/VALIDATION_CAKE_GO_PATH_2026-11-01.md) et la [campagne répétée Go](../../docs/VALIDATION_CAKE_GO_CAMPAIGN_2026-11-05.md) sont validés. Le superviseur Python active les ressources après la fin du processus Go, mesure le trafic et nettoie ses propres espaces jetables, y compris après panne du pilote. Ce nettoyage ne restaure pas la configuration d'une passerelle existante.

CAKE/SQM est envisagé sous Linux ; une passerelle Windows exige une intégration et une validation spécifiques. OpenWrt n'est pas validé. Les privilèges et leur séparation pour les interventions du produit restent à définir.
