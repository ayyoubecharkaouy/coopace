# Rapport global de campagne après Go

## État et entrées internes

Le raccordement est implémenté dans `lab_cake_go_campaign.py` et `lab_cake_go_campaign_report.py`. Le [contrat v1](LAB_CAKE_GO_CAMPAIGN.md), le [collecteur](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) et les [calculs purs](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) conservent leurs paramètres.

| Entrée Python interne | Résultat |
| --- | --- |
| `lab_cake_go_campaign.collect(...)` | Collecte intermédiaire `lab_cake_go_campaign_collection`, sans verdict scientifique |
| `lab_cake_go_campaign.run(...)` | Rapport global `lab_cake_go_campaign`, après collecte, nettoyage et contrôle des preuves |

La [commande de campagne](LAB_CAKE_GO_CAMPAIGN_CLI.md) est maintenant livrée séparément ; la [préparation des entrées](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) est livrée, la relecture et le lanceur natifs restent à développer. Aucun certificat natif de campagne n’est produit.

## Moment de publication

Le propriétaire commun accepte un finaliseur optionnel. Son comportement par défaut reste celui des contrôles historiques. Il appelle le finaliseur de campagne après récupération des groupes, nettoyage, fermeture et vérification des captures, puis synchronisation et fermeture du journal. Après le finaliseur, les empreintes sont encore vérifiées et une interruption ou échéance dépassée interdit la publication positive. Le rapport est écrit une seule fois, avec création exclusive, après ces contrôles.

Une erreur opérationnelle, de capture, de journal ou de nettoyage interdit l’évaluation positive. Les preuves partielles et le rapport échoué sont conservés. `control_complete` dans le journal signifie la fin opérationnelle ; ce message ne prouve pas que les mesures sont exploitables. Un échec ultérieur du finaliseur produit un rapport global `failed` et un code non nul.

## Contrôle des preuves avant calcul

Le finaliseur revérifie les tailles et SHA-256 du journal et des captures stdout/stderr avec lectures bornées. Il exige la séquence globale environnement → ressources → Go → passage IPv4 → trafic → récupération → preuves combinées → nettoyage confirmé. Les contrôles opérationnels existants ont déjà revérifié les outils, sources, preuves Go et topologie ; leurs échecs interdisent le calcul.

Il rapproche les événements stdout du journal et rejoue le dialogue de campagne, avec intentions durables et envois associés. Il rapproche aussi les résultats de phase, identités des outils et relevés du rapport avec leurs événements durables. Chaque fin de phase est liée à l’empreinte de sa ligne capturée. L’arrêt des identités, les lectures vides et l’autorisation de transition sont contrôlés avec les temps monotones conservés : une série finale de lectures vides espacée d’au moins 500 ms, puis `advance` avant trois secondes depuis `end` observé.

Les calculs purs sont ensuite exécutés sur les phases conservées. Les types, percentiles stockés ou déclarations de qualification du pilote ne servent pas de preuve d’un gain réseau.

## Décisions et codes

| Situation | `technical_valid` | Charge / connexions | Sortie |
| --- | --- | --- | --- |
| Preuves et mesures complètes conformes | `true` | Résultats des calculs, séparés | Code 0, même si charge insuffisante ou connexions dégradées |
| Mesures incohérentes ou preuves refusées | `false` | `non_exploitable` / `not_assessed` | Code non nul, rapport `failed` |
| Erreur opérationnelle ou nettoyage incertain | `false` | `non_exploitable` / `not_assessed` | Code non nul ; aucun calcul positif |
| Contrôle de panne conforme | `null` | `not_assessed` / `not_assessed` | Code 0 ; récupération validée sans qualification des mesures |

Le rapport expose `phases` et `assessment` à sa racine, en conservant les détails de `traffic_group`. En mode normal, `assessment` contient l’objet de calcul ; il peut conserver ses diagnostics si les mesures sont inexploitables. Si une preuve globale manque, cet objet reste absent. `congestion`, `comparison` et `coopace_benefit` restent `not_assessed`.

Le verdict est produit dans le processus du superviseur, à partir de son exécution et des preuves qu’il vient de fermer. **Il ne remplace pas une relecture indépendante de toutes les commandes brutes, ni la vérification d’un dossier figé et de sa provenance.** La validation native positive prévue par le contrat reste ultérieure.

## Vérification et suite

Les tests utilisent des données synthétiques pour le verdict positif et les altérations de preuves. Les tests d’intégration utilisent un noyau réseau simulé et de vrais groupes de processus : panne, interruption après le verdict, erreur de journal final, nettoyage incertain et refus d’une collecte complète dont les dates de mesure sont incohérentes. Ce dernier cas vérifie qu’un code 0 du pilote ne suffit pas à produire un succès global.

Validation locale du 2 novembre 2026 : 39 tests ciblés passent en 95,628 s, comprenant huit nouveaux tests du rapport, les calculs et lecteurs purs, ainsi que deux contrôles historiques Go/trafic. Après conservation stricte des fins de ligne lors de la lecture des captures et ajout d’un neuvième test (CRLF/troncature, empreinte mise à jour), les cinq tests de verdict et le contrôle intégré de panne passent en 16,612 s. La suite complète n’a pas été relancée pour cette étape. Aucune validation réseau native de campagne n’est produite.

La [commande de campagne `plan/run/check-crash`](LAB_CAKE_GO_CAMPAIGN_CLI.md) est livrée. La [préparation des entrées](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) est livrée. La prochaine sous-étape est la relecture indépendante et le lanceur natif, avant les essais dans des dossiers neufs.
