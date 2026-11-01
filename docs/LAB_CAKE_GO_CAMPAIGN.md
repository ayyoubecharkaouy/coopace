# Campagne CAKE après Go — contrat v1

## État et objectif

**Contrat défini avant collecte ; [lecteurs et automate purs](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md) implémentés et testés. Le pilote et le collecteur restent à développer ; aucune campagne n’a été exécutée.** Les commandes proposées ici ne sont pas encore disponibles.

La [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) confirme une séquence Go DOWN → activation → passage → transfert, et le nettoyage après panne du pilote. La campagne étendra cette séquence à trois paires repos/charge sur les mêmes ressources, avec une seule installation CAKE par Go.

L’objectif est de valider la collecte répétée et de qualifier le scénario de charge de cette intégration. Les écarts repos/charge seront descriptifs. Une comparaison de politiques ou un bénéfice propre au pilotage Coopace demandera un autre protocole et des bras neufs. Les [campagnes CAKE Python](LAB_CAKE_CAMPAIGN.md) et la [comparaison TBF/CAKE historique](CAKE_COMPARISON.md) fournissent les paramètres de référence, pas les données de cette nouvelle campagne.

Une modification de l’ordre, des paramètres, des bornes ou des critères devra être consignée dans une nouvelle révision de ce protocole avant collecte, avec un dossier neuf. Les résultats défavorables ne justifient ni changement de seuil après coup ni choix du meilleur essai.

## Ressources et ordre fixés

Un seul propriétaire conserve trois espaces neufs `cg-JETON-c/g/s`, le veth `wan` et sa CAKE pendant toute la campagne. La topologie, les routes spécifiques, les outils et le profil `cake-ipv4-lab-4mbit-v1` sont ceux du [contrôle de passage](LAB_CAKE_GO_PATH.md). Aucun réglage de CAKE ne change entre phases.

1. Vérifier sources, outils et provenance des quatre binaires Go ; armer le délai global avant création des ressources.
2. Exécuter une seule phase Go normale : code 0, 14 appels, 36 lignes durables. Récupérer son groupe avant toute activation.
3. Activer les mêmes ressources, puis exécuter les six commandes de passage corrigées : forwarding relu à 0, une requête sans réponse ; forwarding relu à 1, trois requêtes et trois réponses. Les sondes n’utilisent pas `-w`.
4. Après passage accepté, lancer un seul pilote de campagne dans le deuxième groupe. Exécuter les six phases ci-dessous, avec des outils neufs à chaque phase.
5. Après chaque phase, récupérer ses outils et confirmer le vidage avant d’autoriser la suivante. Conserver le leader de campagne jusqu’aux derniers signaux collectifs.
6. Après fin du pilote, récupérer son groupe, relire topologie et CAKE, revérifier les preuves Go et les empreintes, puis nettoyer les seuls espaces possédés. Publier le succès opérationnel après nettoyage confirmé.

| Position | Paire | Condition |
| --- | --- | --- |
| 1 | 1 | `idle` |
| 2 | 1 | `loaded` |
| 3 | 2 | `loaded` |
| 4 | 2 | `idle` |
| 5 | 3 | `idle` |
| 6 | 3 | `loaded` |

Cette campagne utilise une topologie et répète trois paires de mesures. Elle n’est pas une série de trois contrôles isolés avec réinstallation de CAKE. Une répétition ultérieure de la campagne entière exigera un autre dossier et une autre topologie ; tous les essais seront conservés.

## Mesures inchangées

Chaque phase lance une cible TCP neuve sur `10.203.0.6:46001`, au plus 100 acceptations pendant 30 s, et dix établissements avec timeout 1 s et pause 250 ms. La condition déclarée correspond à la phase. `idle` signifie absence du transfert synthétique ; les sondes TCP et le trafic automatique local peuvent encore alimenter les compteurs.

Chaque phase `loaded` ajoute une réception et une émission de 8 388 608 octets sur `10.203.0.6:46002`, plafond applicatif 1 048 576 octets/s, délais 28 s en réception et 25 s en émission. La mesure débute au moins 1 s après première écriture ; sa fenêtre complète doit rester dans les écritures applicatives.

Une campagne normale attend donc **60 tentatives TCP et trois réceptions de 8 Mio, soit 24 Mio utiles**, hors contrôles de panne. Les échecs de connexion restent des tentatives échouées ; les durées indisponibles ne deviennent pas zéro. Le débit utile reçu est calculé sur la durée entre première et dernière lecture.

Les cinq compteurs racine et les jauges CAKE sont relus avant/après chaque phase et périodiquement, avec pause minimale 250 ms après fin d’une lecture, sans rattrapage. Options, identités et monotonie sont contrôlées pendant toute la campagne. Les compteurs des classes ne sont pas ajoutés aux compteurs racine ; drops de file et octets de file restent distincts des pertes TCP et du volume utile.

Les différences Go DOWN, activation, passage ICMP, six phases et campagne entière sont conservées séparément. Chaque différence de phase commence immédiatement avant l’autorisation de démarrer ses outils. Celle de campagne commence après le passage IPv4, avant la première phase ; elle peut aussi inclure les intervalles et vidages.

## Dialogue distinct et lié à la phase

Le dialogue privé à flux unique du [pilote actuel](LAB_CAKE_GO_TRAFFIC.md) garde son format et son comportement. Le nouveau pilote utilisera des lignes JSON v1 distinctes, sans accusé anonyme `OK` et sans EOF entre les phases.

| Message pilote → superviseur | Champs attendus en plus de `schema_version`, `kind`, `session_id` |
| --- | --- |
| `begin` | `event`, `pair`, `condition` |
| `ready` | `event`, `pair`, `condition`, `helper_pids` |
| `end` | `event`, `pair`, `condition`, `result` |
| `complete` | `event` uniquement |

`kind` vaut `lab_cake_go_campaign_event`. `pair` est un entier strict de 1 à 3, `condition` vaut `idle` ou `loaded`, et `session_id` est le jeton possédé de huit caractères. Le JSON refuse clés dupliquées, nombres non finis, champs inconnus, mauvais types et messages hors ordre. `helper_pids` contient un ou trois entiers stricts positifs distincts selon la condition. Pour `idle`, `result` contient exactement `latency` et `measurement_exit_code` ; pour `loaded`, il reprend les six champs et la validation de `lab_cake_go_traffic.validated_flow`.

Les contrôles retour contiennent exactement `schema_version`, `kind: lab_cake_go_campaign_control`, `session_id`, `pair`, `condition`, `action`. Ils utilisent les actions `start`, `continue`, `advance` dans cet ordre pour chaque phase :

1. Le pilote annonce `begin`, sans lancer d’outil de phase. Le superviseur contrôle le contexte et prend le relevé initial, journalise l’intention puis envoie `start`.
2. En `idle`, le pilote lance la cible et annonce son seul PID dans `ready`. En `loaded`, il lance cible/récepteur/émetteur et annonce leurs trois PID dans cet ordre après première écriture. Le superviseur vérifie exécutables, arguments, parent, groupe, session, start-time et namespace des identités annoncées avant `continue`.
3. Le pilote peut alors lancer les dix sondes. Après récupération du sondage et des outils de phase, il envoie `end`. À réception de la ligne complète, le superviseur consigne immédiatement `phase_end_observed` avec son temps monotone, avant les vérifications du résultat et de l’arrêt des identités annoncées. Une présence du même processus interdit la transition ; une réutilisation de PID doit être distinguée par son identité de démarrage, sans signaler un PID étranger.
4. Le superviseur impose deux lectures vides espacées d’au moins 500 ms sous 3 s depuis cette observation, vérifications comprises. Ce point de départ doit être relisible dans le journal. Il envoie `advance` seulement après validation et vidage ; le pilote peut alors annoncer le prochain `begin`.
5. Après le dernier `advance`, le pilote annonce une unique fin `complete`, puis termine. Le superviseur vérifie la fin du canal et récupère le groupe avant nettoyage.

Un `continue` d’une autre paire, un `start` répété ou un résultat ancien ne peut ouvrir la phase courante. Un EOF avant le dernier `advance` est un échec. Les données supplémentaires détectées avant sortie sont refusées ; le superviseur impose aussi son automate, puisqu’un message après sortie du pilote n’est plus observable.

## Bornes fixées

| Élément | Borne |
| --- | --- |
| Propriétaire global | 180 s depuis avant création ; aucune remise à zéro |
| Phase Go / outils / frontières | Bornes existantes 30 s / 2 s / 5 s |
| Passage ICMP | Bornes existantes : sysctl 2 s, sonde négative 4 s, positive 6 s |
| Pilote de campagne | 150 s, limité aussi par le temps global restant |
| Attente d’un contrôle / disponibilité totale de phase | 5 s / 15 s |
| Sondage d’une phase | 16 s ; délais des outils chargés inchangés |
| Vidage par phase | 3 s depuis `phase_end_observed`, double lecture vide à au moins 500 ms |
| Collecte de campagne | 720 échantillons, 4 Mio cumulés |
| Ligne événement `end` | 256 Kio, LF inclus |
| Autres événements et contrôles | 1 Kio par ligne, LF inclus |
| Sorties du pilote | stdout 2 Mio cumulés, stderr 256 Kio |
| Journal durable du superviseur | 16 Mio ; journal Go séparé, borne existante 8 Mio |
| Récupération finale et nettoyage | Budget indépendant existant de 10 s |

Les budgets du pilote et des phases ne prolongent jamais les 180 s. Lecture, écriture et attente doivent rester annulables ; une troncature ou une erreur de preuve interdit un succès. Les intentions sont synchronisées avant action, les résultats conservés après récupération. Un arrêt incertain conserve les espaces concernés selon le contrat existant.

## Calculs et critères avant collecte

Pour chaque paire `i`, conserver les différences signées `p50_loaded(i) − p50_idle(i)`, ainsi que p95/p99, nombres d’échecs et débit utile reçu. Recalculer les percentiles au rang le plus proche depuis les tentatives réussies, sans moyenne de percentiles. Une valeur indisponible reste `null`. Avec dix tentatives, les percentiles hauts restent exploratoires.

| Dimension | Critère |
| --- | --- |
| Validité technique | Six phases dans l’ordre, rapports stricts et provenance conforme, trois volumes exacts, stabilisation et recouvrement, différences exploitables et vidages/nettoyage confirmés |
| Fenêtre chargée — condition de validité technique | Au moins deux relevés CAKE dans la fenêtre de mesure ; différence de compteurs disponible |
| Charge qualifiée | Dans chacune des trois phases chargées, progression des octets dans cette fenêtre et débit reçu dans [350 000 ; 525 000] octets/s, bornes incluses |
| Connexions confirmées | Dix réussites et zéro échec dans chacune des six phases, soit 60 réussites |
| Validation native positive de campagne | Validité technique, fenêtres exploitables, charge qualifiée, connexions confirmées et preuves revérifiées hors ligne |

L’intervalle de débit est repris du [protocole CAKE statique](CAKE_COMPARISON.md). Ni backlog durablement positif, ni augmentation minimale de p50 ne sont exigés pour CAKE. Les seuils ne seront pas ajustés aux résultats. Le traitement numérique doit respecter les frontières inclusives sans arrondi binaire défavorable.

Une erreur opérationnelle, un contexte incohérent ou une collecte incomplète donne code non nul et bilan non exploitable, avec preuves partielles. Une collecte complète techniquement exploitable conserve code 0 même si la charge n’est pas qualifiée ou si des connexions échouent : ces deux dimensions sont déclarées séparément et interdisent une validation native positive. Un échec TCP correctement mesuré ne déclenche pas une reprise sélective ; les phases suivantes restent à collecter si le fonctionnement technique demeure conforme.

Le rapport normal prévu porte `schema_version: 1`, `kind: lab_cake_go_campaign`, une liste de six phases et des décisions séparées : `technical_valid` booléen, `load_scenario` parmi `qualified`/`not_qualified`/`non_exploitable`, `connections` parmi `confirmed`/`degraded`/`not_assessed`. Les connexions sont évaluées dès qu’une collecte complète est techniquement exploitable ; sinon elles restent `not_assessed`. `congestion`, `comparison` et `coopace_benefit` restent `not_assessed`. Un code 0 ou une faible latence ne constitue pas à lui seul une preuve d’amélioration.

## Panne, conservation et suite

Le futur contrôle `check-crash` utilisera un autre laboratoire neuf, la même phase Go et les mêmes contrôles de passage. Après la première phase idle et son vidage, il tuera uniquement le pilote au premier `ready` chargé, après vérification des trois outils et avant `continue`. Il exigera Go 0, pilote -9, trois orphelins récupérés et nettoyage confirmé. Cette collecte partielle gardera ses résultats disponibles, sans décision de campagne qualifiée et sans compter son flux dans les trois transferts attendus du mode normal.

Un contrôle de panne réussi gardera code 0, `technical_valid: null` et `load_scenario`/`connections: not_assessed`. Il validera la récupération demandée, sans se présenter comme une collecte complète.

Une préparation figera commit, protocole, sources, quatre binaires et outils, avec dossiers distincts `run` et `check-crash`. Les rapports, contrôles, identités, codes, sorties, commandes brutes et horodatages seront préservés, y compris après échec. Une revue indépendante devra recalculer l’ordre, les captures, les bornes observables, les fenêtres, les différences et les verdicts ; elle ne déduira pas la réussite d’un booléen du pilote. Les anciens relecteurs conserveront leurs types de rapports distincts.

Les lecteurs et l’automate purs sont [livrés](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md) dans `lab_cake_go_campaign_protocol.py`. Restent à implémenter le pilote privé de phases, le collecteur/l’évaluation de campagne et l’entrée séparée `lab-cake-go-campaign.py` (`plan`, `run`, `check-crash`). La possession, la phase Go, l’activation et le passage seront réutilisés ; toute extraction commune gardera les comportements existants et leurs tests.

Les quatorze tests des lecteurs et de l’automate couvrent limites, fragments, sessions/indices, transitions interdites et erreurs de mesure. **Prochaine sous-étape : pilote privé des six phases**, avec I/O annulables et outils de test simulés. Son raccordement au collecteur, l’évaluation puis la préparation/relecture et les essais natifs suivront. Aucune commande réseau de campagne ni nouveau binaire n’est livré à ce stade.

La comparaison future avec une référence devra notamment harmoniser les contrôles ICMP, la préparation et les observations avant trafic ; des campagnes historiques réalisées à d’autres révisions ne sont pas des bras appariés. Couverture du foyer, IPv6/DNS, restauration réelle, équité, coût système et bénéfice du contrôleur Coopace restent ouverts.
