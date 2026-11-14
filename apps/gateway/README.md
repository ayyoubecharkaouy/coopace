# Application passerelle

État : diagnostic Linux `inspect`, capture détaillée `snapshot`, simulation CAKE statique `plan`, évaluation `restore-plan` et comparaison `restore-check` disponibles. La gestion du trafic du foyer, son routage et l'exécution de la restauration de sa configuration ne sont pas implémentés. Le laboratoire possède son propre superviseur et ses validations natives ; il reste distinct de ces commandes publiques.

Cette application Go assemble l'observation locale et les adaptations du système. Elle accueillera les interventions autorisées sur le trafic qui traverse réellement la passerelle, leur évaluation et le retour à la configuration précédente.

```text
gateway/
├── cmd/
│   ├── coopace-gateway/     # Diagnostic et préparation de restauration
│   ├── coopace-cake-worker/ # Processus interne Go sur lien DOWN
│   └── coopace-session-worker/ # Pilote de décision Go sans privilèges
└── internal/
    ├── cli/                # Arguments et affichage des commandes publiques
    ├── diagnostic/         # Inventaire réduit et adaptation système
    ├── snapshot/           # Capture détaillée locale des files et export
    ├── recovery/           # Préparation et comparaison avant/après, sans exécution
    ├── planning/           # Scénario local et simulation sans collecte
    ├── labcontrol/         # Transport/journal, backend DOWN et pilote de session
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

[`snapshot --interface NOM [--json]`](../../docs/GATEWAY_SNAPSHOT.md) observe explicitement une interface Linux : détails du lien, qdisc, classes et filtres racine/ingress/egress. Les options JSON restent locales et peuvent contenir des adresses et identifiants. Les lectures sont successives, bornées et non exhaustives ; elles ne constituent pas une sauvegarde restaurable. Les tests utilisent des sources simulées ; le [rapport utilisateur sur `wlp3s0`](../../docs/VALIDATION_GATEWAY_SNAPSHOT_2026-11-12.md) confirme les six sections et la compatibilité des classes vides.

La compatibilité avec les anciennes sorties de classes est bornée : une première sortie vide doit être confirmée par une seconde lecture texte réussie et vide avant de devenir `[]`. Les preuves de cette conversion restent dans le rapport ; les configurations de classes non JSON demeurent indisponibles.

[`plan --scenario FICHIER [--json]`](../../docs/GATEWAY_PLANNING.md) applique la [règle Go de planification statique](../../docs/STATIC_CAKE_PLANNING.md) à un scénario déclaré strict, de 16 Kio maximum. Elle propose le profil du laboratoire, conserve la référence ou s'abstient. Elle n'effectue aucune collecte ni application réseau.

La [préparation du retour à l'état initial](../../docs/GATEWAY_RECOVERY.md) fournit `restore-plan --snapshot FICHIER` ou `--interface NOM`, puis `restore-check --before FICHIER` avec `--after FICHIER` ou `--interface NOM`. Le premier profil reconnu est une racine noqueue sans dépendances visibles. Les captures sont importées avec contrôles de cohérence et empreinte SHA-256 ; les comparaisons distinguent correspondance, différence et résultat indéterminé. `snapshot --output FICHIER` enregistre une nouvelle référence privée sans écrasement. L'exécuteur de restauration du produit sur le foyer reste à développer.

Ces commandes ne démarrent aucun service. Seule l'option explicite `snapshot --output` enregistre un rapport. Aucune interface WAN, couverture du trafic ou autorisation d'intervention n'est déduite d'un inventaire. Le [protocole de référence initiale](../../docs/GATEWAY_BASELINE.md) définit les preuves restant à recueillir avant une intervention réelle.

Le processus privé `coopace-cake-worker` appartient au [contrôle supervisé CAKE](../../docs/LAB_CAKE_GO_GUARD.md), avec session, outils épinglés et journal durable. Ses [contrôles natifs DOWN](../../docs/VALIDATION_CAKE_GO_DOWN_2026-11-01.md), le [passage IPv4 puis trafic](../../docs/VALIDATION_CAKE_GO_PATH_2026-11-01.md) et la [campagne répétée Go](../../docs/VALIDATION_CAKE_GO_CAMPAIGN_2026-11-05.md) sont validés. Le superviseur Python active les ressources après la fin du processus Go, mesure le trafic et nettoie ses propres espaces jetables, y compris après panne du pilote. Ce nettoyage ne restaure pas la configuration d'une passerelle existante.

Le [contrôle de restauration du laboratoire](../../docs/LAB_QUEUE_RECOVERY.md) raccorde ces commandes Go à un superviseur Python : état initial noqueue, installation CAKE possédée, retrait ciblé après fin normale/panne du pilote, puis comparaison avant suppression des espaces. Les [deux essais réseau natifs sont validés](../../docs/VALIDATION_QUEUE_RECOVERY_2026-11-12.md), avec relecture de 105 pièces par mode. Ce moteur ne fournit aucune commande publique d'application sur une interface du foyer.

CAKE/SQM est envisagé sous Linux ; une passerelle Windows exige une intégration et une validation spécifiques. OpenWrt n'est pas validé. Les privilèges et leur séparation pour les interventions du produit restent à définir.

Le [pilote privé de session](../../docs/GATEWAY_SESSION.md) raccorde maintenant un automate Go au moteur de restauration du laboratoire. Il importe la référence initiale et son empreinte, exige l’accord local, demande l’application au superviseur et vérifie la capture CAKE. Le superviseur restaure après la sortie ou la panne du pilote sans privilèges. Tests en simulation réussis et [deux essais natifs validés](../../docs/VALIDATION_GATEWAY_SESSION_2026-11-14.md), avec retour à noqueue après fin normale ou SIGKILL.
