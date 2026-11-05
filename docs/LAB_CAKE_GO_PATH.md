# Contrôle du passage IPv4 après Go — contrat v1

## État et objectif

Le contrat et les lecteurs purs de `scripts/lab_cake_go_path.py` sont livrés avec neuf tests. Le [raccordement au superviseur](LAB_CAKE_GO_PATH_CONTROL.md) est maintenant implémenté et testé avec réseau simulé ; l’exécuteur de commandes est testé avec de vrais sous-processus sans réseau. **La [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) est confirmée pour les deux modes.** L’entrée séparée `scripts/lab-cake-go-path.py` expose `plan`, `check` et `check-crash`.

La [validation native Go puis trafic](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) confirme un transfert sur les ressources conservées après Go. Ce nouveau contrôle doit ajouter une preuve causale limitée : sans forwarding dans la passerelle possédée, aucune réponse à une requête ICMP ; après réactivation, trois requêtes et trois réponses. Les contrôles historiques des campagnes Python restent des preuves de leurs propres révisions.

Ce test porte sur le chemin IPv4 fixe du laboratoire. Il ne prouve ni une couverture du foyer, une amélioration Internet, l’absence universelle de route de contournement, ni le comportement IPv6/DNS.

## Placement et séquence

La phase Go normale, la récupération de son groupe et l’[activation](LAB_CAKE_GO_TOPOLOGY.md) précèdent ce contrôle. `wan`, sa CAKE et les trois espaces restent possédés par le même superviseur. Aucun pilote de trafic, cible TCP ou transfert ne doit démarrer avant l’acceptation du passage.

| Ordre | Commande dans les seuls espaces possédés | Acceptation |
| --- | --- | --- |
| Avant contrôle | Topologie active, forwarding `1`, file et identités relus | Continuité avec Go confirmée |
| 1 | `sysctl -q -w net.ipv4.ip_forward=0` dans la passerelle | Code 0 |
| 2 | `sysctl -n net.ipv4.ip_forward` dans la passerelle | Code 0 et ligne exacte `0` |
| 3 | `ping -4 -n -c 1 -W 1 10.203.0.6` depuis le client | Code 1, un envoi et zéro réponse |
| 4 | `sysctl -q -w net.ipv4.ip_forward=1` dans la passerelle | Code 0 |
| 5 | `sysctl -n net.ipv4.ip_forward` dans la passerelle | Code 0 et ligne exacte `1` |
| 6 | `ping -4 -n -c 3 -W 1 10.203.0.6` depuis le client | Code 0, trois envois et trois réponses |
| Après contrôle | Topologie, forwarding `1`, file et identités relus | Même CAKE, compteurs monotones |

Les commandes sont précédées de `ip netns exec ESPACE` avec les chemins canoniques épinglés des outils. Leur liste est fermée et ordonnée ; pas de shell, adresse publique, route par défaut, NAT ou interface physique. La locale des outils est `LANG=C`, `LC_ALL=C`.

Une étape défaillante interdit les étapes suivantes et le lancement du trafic TCP. En particulier, un résultat négatif inattendu interdit la sonde positive. Le superviseur récupère la commande courante, puis supprime les seuls espaces possédés selon les garanties existantes. Il ne tente pas de modifier le forwarding de l’hôte pour « restaurer » un laboratoire abandonné.

Pendant le forwarding désactivé, la relecture complète qui exige `1` ne doit pas être appelée. Les identités possédées et la file doivent continuer à être contrôlées ; la vérification complète reprend seulement après la relecture de `1`. Une incertitude sur l’arrêt d’un processus interdit la suppression de ses espaces.

## Interprétation des captures

`validate_forwarding(stdout, expected)` accepte uniquement les octets `0\n` ou `1\n` correspondant à l’état attendu. Un succès de la commande d’écriture ne remplace jamais cette relecture.

`validate_probe(stdout, exit_code, forwarding=...)` accepte un profil explicite de sortie iputils en locale C, pour `10.203.0.6` et le payload par défaut. Il exige une capture complète comprenant l’en-tête de cible, un seul titre de statistiques et un seul résumé immédiatement après ce titre.

| Résultat | Interprétation |
| --- | --- |
| Code 1 et résumé `1 transmis / 0 reçu / 100 %` avec forwarding relu à 0 | Blocage attendu de cette sonde |
| Code 0 et résumé `3 transmis / 3 reçus / 0 %` avec forwarding relu à 1 | Passage attendu de ces sondes |
| Code 1 seul, capture vide ou incompréhensible | Aucune preuve interprétable |
| Code 2, signal, dépassement de délai ou erreur de lancement | Échec technique, jamais un blocage validé |
| Réponse sans forwarding, résultat partiel, mauvaise cible ou comptes incohérents | Refus de la preuve |

Une erreur ICMP déclarée `+1 errors` reste admise dans le contrôle négatif si aucune réponse echo n’est reçue ; elle ne devient pas une réussite de ping. Les duplications, erreurs dans le contrôle positif, résumés répétés, sortie localisée ou non prise en charge sont refusés. Les booléens ne remplacent pas des codes ou états entiers.

Les lecteurs produisent des faits de capture, sans état de validation native. Le pourcentage de perte et la durée du résumé restent ceux déclarés par ping ; ils ne mesurent pas une perte TCP, une latence applicative, une capacité Internet ou la durée monotone du processus. Une capture acceptée ne prouve pas à elle seule les arguments réellement lancés, le namespace, l’ordre ou la relecture du forwarding : le raccordement doit établir ces faits séparément.

## Bornes et preuves

Le budget global reste de 180 s, sans remise à zéro après Go ni après activation. Chaque `ip`/`tc`/`sysctl` reste borné à 2 s ; les sondes négative et positive reçoivent respectivement une borne externe de 4 s et 6 s. Les sondes utilisent `-c` et `-W`, sans `-w` : une échéance iputils peut entraîner des envois supplémentaires malgré le compte demandé. Le délai externe reste imposé par le superviseur. Chaque capture stdout/stderr est limitée à 64 Kio ; une troncature interdit le succès. Le nettoyage garde son budget indépendant existant.

Le [raccordement](LAB_CAKE_GO_PATH_CONTROL.md) conserve, avant chaque action, une intention durable, puis ses arguments exacts, code OS, sorties brutes, dates UTC et durée monotone. Les outils — y compris `ping`, sa sortie `-V` et son empreinte ELF — et les sources sont figés avant lancement et revérifiés. Les identités des espaces doivent être recontrôlées avant chaque commande.

Les lectures CAKE avant/après passage restent séparées de la différence de trafic TCP, dont le point de départ demeure juste avant le pilote. Les tentatives ICMP et leurs nombres d’envois constatés restent distincts du volume applicatif reçu. Les compteurs peuvent aussi inclure du trafic local automatique ; ils ne sont pas un comptage exclusif des sondes.

Une relecture indépendante doit recalculer les comptes depuis les captures et vérifier leur correspondance avec les commandes, états relus, transitions et empreintes. Aucun champ `path_verified` ne peut résulter seulement d’un booléen annoncé par l’exécuteur. Les modes et rapports de la [validation native historique](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) gardent leur signification ; ils ne deviennent pas rétroactivement des contrôles négatifs.

## Vérification et progression

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go_path.py' -v
```

Les neuf tests des lecteurs passent au 1er novembre 2026, y compris la capture native du [premier essai refusé](REVIEW_CAKE_GO_PATH_FAILURE_2026-11-01.md). Ils couvrent blocage et passage attendus, erreurs techniques, réponse inattendue, réception partielle, mauvais comptes/cible, ambiguïtés, formats, bornes, types stricts et relecture du forwarding. Les captures de test sont des données de lecture ; aucun processus ni réseau n’est lancé par le module ou cette suite.

Le [raccordement à l’exécuteur borné et au superviseur](LAB_CAKE_GO_PATH_CONTROL.md) est livré avec tests des erreurs, interruptions et refus de démarrer le trafic. Les [outils de préparation et de relecture natives](LAB_CAKE_GO_PATH_NATIVE.md) sont livrés. La [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) confirme les deux modes corrigés. Le [contrat de campagne répétée Go](LAB_CAKE_GO_CAMPAIGN.md) est défini avant collecte : trois paires repos/charge, dialogue lié à la session et critères séparés. Les [lecteurs et l’automate purs](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md) sont implémentés et couverts par quatorze tests. Le [pilote privé des six phases](LAB_CAKE_GO_CAMPAIGN_TRAFFIC.md) est livré et testé avec outils simulés et vrais processus. Le [collecteur des six phases](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) est implémenté et testé avec réseau simulé : contrôle des PID, journal durable et vidage entre phases. L’[évaluation pure des mesures](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) est implémentée et testée. Le [rapport global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) la raccorde maintenant aux preuves du superviseur après nettoyage. La [commande de campagne](LAB_CAKE_GO_CAMPAIGN_CLI.md) est livrée. La [préparation des entrées](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) est livrée séparément. La [relecture des phases](LAB_CAKE_GO_CAMPAIGN_PHASE_REVIEW.md) est livrée séparément. La [relecture globale du dossier figé](LAB_CAKE_GO_CAMPAIGN_GLOBAL_REVIEW.md) est maintenant livrée. Le lanceur et les essais natifs restent ultérieurs. Une campagne comparative de l’intégration Go et tout bénéfice propre à Coopace restent ultérieurs.
