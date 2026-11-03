# Lecteurs et automate purs de la campagne Go

## État et portée

Le [contrat de campagne v1](LAB_CAKE_GO_CAMPAIGN.md) dispose de ses lecteurs et de son automate dans `scripts/lab_cake_go_campaign_protocol.py`. **Le [pilote privé](LAB_CAKE_GO_CAMPAIGN_TRAFFIC.md) est maintenant implémenté et testé avec outils simulés. Le [collecteur interne](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) est également implémenté et testé en simulation ; l’[évaluation pure](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) est testée séparément, son [raccordement global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) est livré ; l’[entrée de campagne](LAB_CAKE_GO_CAMPAIGN_CLI.md) est livrée ; aucune campagne réseau native n’a été exécutée.**

Ce module traite uniquement des octets et des états. Il ne lance aucun processus, ne lit pas d’horloge, ne crée aucun réseau et n’exécute ni sonde ni nettoyage. Les aides métier du pilote à flux unique sont importées pour valider les sous-rapports ; son code et son dialogue restent inchangés.

## Interface

| API | Responsabilité |
| --- | --- |
| `parse_event(raw, session)` | Lire une ligne pilote : `begin`, `ready`, `end` ou `complete` |
| `parse_control(raw, session)` | Lire une ligne superviseur : `start`, `continue` ou `advance` |
| `event_frame(...)`, `control_frame(...)` | Encoder puis valider une ligne UTF-8 terminée par LF |
| `LineReader(session, direction)` | Assembler les fragments d’un flux `events` ou `controls` avec budgets cumulés |
| `Dialogue(session)` | Accepter événements et contrôles dans l’ordre des six phases |

Les enveloppes sont fermées aux champs inconnus, avec version et indice de paire entiers stricts. Les clés dupliquées sont refusées à toute profondeur ; UTF-8 invalide, JSON non objet, NaN/Infinity et débordement flottant sont rejetés. Les lignes multiples, incomplètes et CRLF ne sont pas acceptées comme une ligne de protocole.

`ready` exige un PID pour idle, trois pour loaded, tous entiers positifs distincts dans la phase. Ces valeurs ne prouvent pas l’identité ni l’état d’un processus. Une réutilisation de PID entre phases n’est pas interdite par le lecteur ; le superviseur vérifie les identités réelles.

Le résultat idle contient exactement `latency` et `measurement_exit_code`, validés avec `lab_active.latency_document`. Le résultat loaded utilise les six champs et la validation de `lab_cake_go_traffic.validated_flow`, notamment volumes, débits applicatifs et indicateurs recalculés. Les sous-rapports gardent les règles existantes ; leurs métadonnées ne deviennent pas de nouveaux champs de dialogue autorisés.

Une mesure entièrement échouée reste un résultat valide si ses dix tentatives, erreurs et code sont cohérents. Une mesure partiellement réussie peut avoir code 0 tout en conservant ses échecs. Cette lecture ne qualifie ni les connexions de la campagne, ni sa charge, ni ses percentiles ; ces décisions resteront à calculer avec les preuves par le collecteur, l’évaluation et la relecture.

## Fragments et limites

`LineReader.feed(bytes)` renvoie les messages complets validés et conserve seulement la ligne partielle restante. Un fragment UTF-8 peut être coupé entre deux octets ; le décodage attend LF. Plusieurs lignes réunies dans un fragment gardent leurs frontières. Un fragment vide ne signifie pas EOF : `finish()` doit être appelé explicitement.

Les limites incluent LF : 1 024 octets pour événements courts et contrôles, 256 Kio pour `end`. Le flux pilote reste sous 2 Mio. L’ordre normal implique au plus 19 événements et 18 contrôles, donc un maximum de 18 Kio pour ce dernier flux. La ligne en attente ne dépasse jamais son plafond, y compris lorsqu’un fragment fourni est trop grand.

Une erreur de lecture est permanente : ajouter les octets manquants ou fournir ensuite une ligne correcte ne répare pas le lecteur. `finish()` refuse une ligne partielle. Un EOF de cadrage avec zéro ligne reste possible ; il ne prouve pas la fin du dialogue.

Le collecteur conserve le temps monotone de réception des octets terminant la ligne **avant** d’appeler les lecteurs et leurs validations. Cette observation alimente `phase_end_observed`. Le module pur ne mesure ni les échéances ni le vidage.

## Ordre et fin du dialogue

Le superviseur et le pilote suivent le même ordre contractuel : `(1,idle)`, `(1,loaded)`, `(2,loaded)`, `(2,idle)`, `(3,idle)`, `(3,loaded)`. Chaque phase suit :

```text
event begin → control start → event ready → control continue
→ event end → control advance
```

Un indice ne progresse qu’après `advance`. Après le sixième, un unique `complete` est accepté. Mauvaise session/direction/phase, répétition, saut, fin prématurée ou message après EOF rendent l’automate définitivement échoué. Il ne retente pas une transition refusée.

`finish_events()` est permis après `complete`. `finish_controls()` est permis après le dernier `advance`, y compris avant réception de `complete`. La propriété `Dialogue.complete` exige l’événement final et les deux EOF ; elle décrit seulement la complétude du dialogue. Les observations EOF répétées sont idempotentes ; un message ultérieur reste interdit.

Les vérifications de possession, outils/PID, arrêt des helpers et vidage doivent être réalisées **avant** que le superviseur enregistre les contrôles correspondants dans l’automate. Accepter un `continue` ou un `advance` au bon endroit ne constitue aucune autorisation réseau produite par ce module.

## Vérification et suite

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go_campaign_protocol.py' -v
```

Les quatorze tests couvrent le parcours des six phases, les données de mesure échouées ou partielles, les types/champs/sessions, les PID, les résultats incohérents, doublons et encodages invalides, limites exactes, fragments UTF-8, flux regroupés, budgets, répétitions à chaque frontière et EOF à chaque état.

Les six tests purs du protocole à flux unique restent également vérifiés. Ces vingt tests ciblés ne lancent aucune expérience réseau et ne produisent aucun certificat natif. Les preuves de la [validation du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) restent distinctes.

Le [pilote privé des six phases](LAB_CAKE_GO_CAMPAIGN_TRAFFIC.md) est livré avec I/O annulables et tests de processus à outils simulés. Le [collecteur interne](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) le raccorde au superviseur, avec contrôle des PID, journal durable et vidage entre phases testés en simulation. L’[évaluation pure](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) est livrée séparément. Son [raccordement global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) est livré. La [commande de campagne](LAB_CAKE_GO_CAMPAIGN_CLI.md) est livrée. La [préparation des entrées](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) est livrée. Relecture, lanceur et essais natifs suivront.
