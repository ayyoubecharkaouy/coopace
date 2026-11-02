# Évaluation pure des mesures de campagne Go

## État et portée

`scripts/lab_cake_go_campaign_assess.py` fournit `assess(phases, crash=False)`. Ce module est autonome : aucune lecture de preuves, horloge, création de processus ou action réseau. Il reçoit les six dictionnaires de phase du [collecteur](LAB_CAKE_GO_CAMPAIGN_COLLECT.md), sans les modifier. Il réutilise les validations des résultats du [dialogue v1](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md).

**Le raccordement au rapport global reste à réaliser.** Le collecteur conserve donc son rapport intermédiaire et `assessment: not_implemented`. L’évaluateur produit un objet distinct `lab_cake_go_campaign_measurements`, jamais un certificat ni le rapport final `lab_cake_go_campaign`.

## Calculs

Les p50/p95/p99 sont recalculés au rang le plus proche depuis les seules tentatives réussies. Un échec reste compté ; si toutes les tentatives échouent, les percentiles et différences indisponibles restent `null`. Les résumés de percentiles stockés dans les entrées ne sont pas utilisés.

Les trois différences signées loaded − idle sont calculées séparément, sans moyenne de percentiles. Les soustractions utilisent les valeurs décimales avant conversion d’affichage, pour préserver les petits écarts entre grandes valeurs.

Le débit utile reçu est recalculé depuis le volume et la durée entre première et dernière lecture, en nanosecondes. La durée et le débit déclarés sont contrôlés avec la tolérance relative existante de 1e-9. Les bornes inclusives [350 000 ; 525 000] octets/s sont comparées avec des produits entiers ; un arrondi du débit affiché ne détermine pas la qualification.

## Vérifications des mesures

L’évaluateur exige les six phases complètes dans l’ordre contractuel et au plus 720 relevés. Les résultats stricts, volumes exacts et conditions sont revérifiés. Les échantillons doivent appartenir à leur paire/condition, aller de `before_start` à `drain`, encadrer les sondes ainsi que les transferts chargés et conserver des horodatages strictement croissants. Les cinq compteurs entiers de 64 bits doivent rester monotones, y compris entre phases. Les différences stockées sont ignorées et recalculées.

Pour chaque phase chargée, la stabilisation doit être d’au moins une seconde et la fenêtre complète des sondes comprise dans les écritures applicatives. Au moins deux relevés doivent appartenir à la fenêtre de sondage, bornes incluses ; leur différence est recalculée. La charge est qualifiée seulement si les octets progressent dans chacune des trois fenêtres et si les trois débits reçus respectent les bornes fixées.

## Résultats et limites

| Champ | Signification dans cet objet de calcul |
| --- | --- |
| `measurements_valid` | `true` si les mesures sont exploitables ; `false` si incomplètes/incohérentes ; `null` en mode panne |
| `load_scenario` | `qualified` ou `not_qualified` si exploitable ; `non_exploitable` sinon ; `not_assessed` en mode panne |
| `connections` | `confirmed` pour 60 réussites, `degraded` si des tentatives échouent ; `not_assessed` si inexploitable ou en mode panne |
| `phases`, `pairs` | Résumés recalculés et différences signées ; en cas d’erreur, les résumés déjà calculés peuvent rester partiels |
| `reasons` | Diagnostic d’inexploitabilité |

Ces décisions portent seulement sur les données reçues. Elles ne remplacent pas la validité technique globale du contrat : provenance, identité des processus et ressources, dialogue durable, délais monotones, vidages et nettoyage devront être vérifiés lors du raccordement puis de la relecture indépendante. Aucun champ `technical_valid` n’est produit. Les décisions finales de charge/connexions devront rester non évaluées si ces preuves globales manquent. `congestion`, `comparison` et `coopace_benefit` restent `not_assessed`.

Le mode panne ne valide pas les preuves de récupération ; il laisse simplement les décisions de mesure non évaluées. La commande publique, la préparation figée et les essais natifs de campagne restent ultérieurs.

## Vérification et suite

```sh
PYTHONPATH=scripts/tests python3 -B -m unittest test_lab_cake_go_campaign_assess test_lab_cake_go_campaign_protocol test_lab_cake_go_traffic.ProtocolTests -v
```

Validation locale du 2 novembre 2026 : 29 tests ciblés passent en 0,388 s, dont neuf nouveaux pour les calculs, quatorze de dialogue de campagne et six du protocole à flux unique. Les cas couvrent les percentiles, les différences signées, les échecs partiels/totaux, les bornes exactes et leurs voisins, la charge insuffisante, les horodatages, volumes et compteurs incohérents, le mode panne et la conservation des entrées. Aucun processus ni réseau n’est lancé par les nouveaux tests de calcul. La suite complète n’a pas été relancée pour cet ajout autonome.

Prochaine sous-étape : raccorder cet objet de calcul aux preuves du superviseur pour construire le rapport global, avec tests d’intégration, avant la commande publique et la préparation/relecture natives.
