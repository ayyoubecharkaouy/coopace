# Collecte des six phases après Go

## État et portée

Le raccordement interne est implémenté dans `scripts/lab_cake_go_campaign.py` et `scripts/lab_cake_go_campaign_collect.py`. Il réutilise le propriétaire unique, la phase Go sur lien DOWN, l’activation et le contrôle de passage IPv4, puis lance le [pilote privé des six phases](LAB_CAKE_GO_CAMPAIGN_TRAFFIC.md). Les paramètres et les bornes du [contrat v1](LAB_CAKE_GO_CAMPAIGN.md) sont conservés.

Les tests utilisent des processus, pipes et groupes Linux réels, avec outils et noyau réseau simulés. **La [première campagne Go native](VALIDATION_CAKE_GO_CAMPAIGN_2026-11-05.md) est validée dans les deux modes.** L’[évaluation pure des mesures](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) est livrée séparément ; son [raccordement global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) est livré. La [commande de campagne](LAB_CAKE_GO_CAMPAIGN_CLI.md) est livrée ; la [préparation des entrées](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) est livrée, la relecture et le [lanceur natif](LAB_CAKE_GO_CAMPAIGN_RUN.md) sont livrés.

## Répartition des responsabilités

| Module | Responsabilité |
| --- | --- |
| `lab_cake_go_campaign.py` | Inventaire incluant ping et les sources de campagne, journal de 16 Mio, assemblage interne des modes `run` et `check-crash` |
| `lab_cake_go_campaign_collect.py` | Dialogue, vérification des outils annoncés, relevés CAKE, arrêt des identités et vidage avant chaque transition |
| `lab_cake_go_active.py` | Propriétaire commun, enchaînement Go/activation/passage/collecte, conservation des preuves et nettoyage final |
| `lab_cake_go_campaign_protocol.py` | Lecteurs stricts et automate des six phases |
| `lab_cake_go_campaign_traffic.py` | Création et récupération des outils de chaque phase |

Le journal et le type de rapport sont injectables dans l’assemblage commun. Le comportement par défaut des contrôles historiques à flux unique reste celui de leurs propres commandes et formats.

## Frontières vérifiées

Avant `start`, le collecteur revérifie l’inventaire et la topologie, puis conserve le relevé initial de phase. Avant `continue`, il contrôle les PID annoncés : exécutable, arguments, parent, groupe, session, identité de démarrage et namespace réseau. Les rôles attendus sont une cible en idle, puis cible/récepteur/émetteur en loaded.

La capture conserve le temps monotone du `read` contenant le LF avant synchronisation de la preuve et validation JSON. Lorsqu’un `end` est attendu, le journal durable reçoit `phase_end_observed`, l’empreinte de la ligne et ce temps. Le collecteur vérifie ensuite que chaque identité annoncée a disparu. Un processus encore présent, même zombie, interdit `advance`. Une réutilisation de PID est conservée comme telle ; cette vérification ne signale aucun processus.

Le vidage demande deux lectures avec `backlog_bytes` et `queued_packets` à zéro, espacées d’au moins 500 ms, sous 3 s depuis cette observation de fin. Chaque échantillon conserve les temps monotones de début et de fin de lecture, la paire et la condition. La même échéance limite aussi l’envoi de `advance`, après les dernières vérifications et l’intention durable : une lecture vide à temps ne permet pas une autorisation tardive. Les lectures de vidage font partie des échantillons de phase. Les différences de compteurs sont recalculées depuis le relevé précédant `start` jusqu’au dernier relevé de vidage.

Chaque contrôle possède une intention durable avant écriture, puis une preuve d’envoi. La collecte conserve les octets stdout/stderr, refuse les messages prématurés ou groupés aux frontières et vérifie les deux EOF ainsi que le code réel du pilote. Le propriétaire récupère le groupe et nettoie ses ressources avant le succès global.

## Bornes et panne

Le délai global reste 180 s, celui du pilote 150 s, et la disponibilité de chaque phase 15 s après `start`. Les accusés restent bornés à 5 s. La collecte est limitée à 720 échantillons et 4 Mio ; les captures stdout/stderr à 2 Mio/256 Kio. Le journal du superviseur est limité à 16 Mio. Les écritures de preuve utilisent la capture synchronisée existante ; une erreur interdit la poursuite.

En `check-crash`, la première phase idle est collectée et vidée. Le collecteur tue ensuite le seul pilote au premier `ready` chargé, après vérification des trois outils et avant `continue`. Il exige le code -9, trois descendants récupérés et le nettoyage confirmé. La phase chargée reste interrompue et son résultat absent.

## Rapport intermédiaire

Le rapport porte `kind: lab_cake_go_campaign_collection`. Les six phases et leurs preuves se trouvent dans `traffic_group.phases`. Chaque phase contient son état, les identités, le résultat reçu, les échantillons, l’observation de fin et la différence de compteurs. Le champ historique `flow` reste `null` : les résultats chargés appartiennent aux phases.

`traffic_group.state` vaut `collected`, `crash_verified` ou `failed`. `assessment` reste `not_implemented` et `congestion`, `comparison`, `coopace_benefit` restent `not_assessed`. L’état global `complete` indique la réussite opérationnelle et le nettoyage ; il ne constitue aucune qualification scientifique.

L’entrée `collect(...)` ne produit pas le rapport final. L’entrée `run(...)` produit maintenant le [rapport global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) `lab_cake_go_campaign` après contrôle des preuves et nettoyage. Stabilisation, recouvrement, fenêtres chargées, percentiles, débit qualifié et décisions séparées seront recalculés par l’évaluation. Des tentatives TCP toutes échouées mais cohérentes restent collectées sans décision positive. Les relecteurs natifs historiques ne doivent pas accepter ce type intermédiaire.

## Vérification et suite

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go_campaign_collect.py' -v
```

Les tests couvrent les six phases, les trois résultats chargés, l’ordre après passage IPv4, les temps de vidage, la panne avec trois orphelins, les tentatives TCP échouées, les mauvaises identités/phases, les erreurs de preuve, les délais, une file non vidée, une remise à zéro des compteurs, un nettoyage incertain et le refus de démarrer après une phase Go ou un passage invalides. La vérification d’un PID réutilisé est également testée sans signal.

Validation locale du 2 novembre 2026 : la suite Python complète passe, avec 239 tests en 744,506 s. Après resserrement de l’échéance jusqu’à l’envoi de `advance` et ajout du cas de vérifications tardives, les sept tests ciblés du collecteur passent en 235,443 s. La suite complète n’a pas été répétée après cette correction isolée au collecteur de campagne. Les outils réseau sont simulés ; aucun certificat natif de campagne n’est produit. Le certificat historique du passage IPv4 et ses 46 empreintes d’artefacts restent conformes.

Le [raccordement global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) de l’évaluation est livré et testé. La [commande de campagne](LAB_CAKE_GO_CAMPAIGN_CLI.md) est livrée. La [préparation des entrées](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) est livrée. La [campagne native](VALIDATION_CAKE_GO_CAMPAIGN_2026-11-05.md) confirme désormais les deux modes et leur nettoyage. Les validations natives historiques et leurs certificats restent distincts.
