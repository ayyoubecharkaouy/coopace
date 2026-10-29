# Premier essai natif des séries TCP — 29 octobre 2026

## Résultat et portée

L'utilisateur a exécuté le lanceur local de `run-series` depuis son terminal Linux. Le code de sortie conservé est `0`. Les six séries contiennent **60 connexions réussies sur 60, sans échec**. Les trois transferts synthétiques totalisent **24 Mio envoyés et reçus**. Le recouvrement avec les fenêtres d'écritures et le nettoyage normal sont vérifiés.

Cet essai valide le fonctionnement du scénario de collecte et de comparaison. Il ne démontre pas de gain d'optimisation : aucune politique de files ni goulot artificiel n'a été appliqué. La saturation du réseau virtuel n'est pas établie. L'étape 4.2 reste ouverte pour les références pertinentes et la préparation de la restauration.

## Provenance

- Commit de préparation et de compilation : `0510f858310695cce3a83b2af140c8a865c45b9d`.
- Outils : Go 1.27.3, Linux amd64 ; pilote Python 3.12.3 lors de la préparation.
- Dossier local : `.local/experiments/series-validation-0510f85/`.
- Fenêtre des phases : `2026-10-29T21:08:03.595911274Z` à `2026-10-29T21:08:37.217216821Z`.
- Les empreintes des trois binaires et des deux scripts correspondent à la préparation.

Le lanceur a conservé le rapport, le journal et le code exact. `prepared.json`, `protocol.md`, `plan.txt`, `inputs.sha256` et `run.sh` restent les pièces antérieures à l'essai ; `validation.json` consigne les contrôles et leurs empreintes. Les données brutes restent locales et exclues de Git.

| Pièce | SHA-256 |
| --- | --- |
| `report.json` | `764f67a5772f6b8e905d7776487e89b65d32a96bc42212fb1949e30f48642601` |
| `run.log` | `f51a674ac53e0a6d0c1468476b2e73c35366a8bdec99127a672dc6e302d7cdfb` |
| `exit-code` | `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa` |

## Résultats descriptifs

Même topologie, même cible `10.203.0.6:46001`, dix tentatives par série, timeout et intervalle de 250ms. Les trois paires respectent l'ordre préétabli. Chaque condition contient 30 réussites et zéro échec. Les pauses entre phases sont d'au moins 500ms après la phase précédente et la fin éventuelle de sa charge.

| Paire | Ordre | p50 idle (ms) | p50 loaded (ms) | p95 idle (ms) | p95 loaded (ms) |
| --- | --- | --- | --- | --- | --- |
| 1 | idle → loaded | 0.245884 | 0.202414 | 0.395802 | 0.261506 |
| 2 | loaded → idle | 0.219712 | 0.227538 | 0.334895 | 0.453606 |
| 3 | idle → loaded | 0.208944 | 0.207832 | 0.261173 | 0.253737 |

Les trois comparaisons ont été reproduites avec le lecteur strict de l'agent à partir des rapports imbriqués. Leurs sorties correspondent exactement aux textes enregistrés dans le rapport groupé. Les statistiques proviennent des seules réussites ; avec dix essais, p95 et p99 sont le maximum de chaque série. Les percentiles des paires ne sont pas moyennés.

Les variations sont de sens différents selon la paire et la statistique. Elles ne permettent aucune attribution causale ni estimation d'un gain Coopace. Ces durées d'établissement TCP sur un noyau partagé ne sont pas des RTT Internet. `idle` désigne l'absence du transfert propre au scénario, sans prouver le repos de l'hôte.

## Recouvrement et charge

Chaque transfert confirme 8 388 608 octets écrits et reçus. Les moyennes applicatives sont inférieures au plafond de 1 048 576 octets/s ; les durées respectent les limites prévues. La fenêtre entière de chaque série loaded est comprise entre la première et la dernière écriture de sa charge :

| Paire | Marge avant la série (ms) | Marge après la série (ms) | Durée d'émission (ms) |
| --- | --- | --- | --- |
| 1 | 20.635460 | 5707.970559 | 8000.673930 |
| 2 | 20.418333 | 5707.709645 | 8000.420003 |
| 3 | 20.391304 | 5708.305586 | 8000.510394 |

Le contrôle utilise les horodatages à la nanoseconde. Il établit un recouvrement des fenêtres applicatives ; le tamponnement par le noyau empêche d'en déduire une émission continue de paquets ou une saturation du lien.

## Arrêt et nettoyage

Le journal confirme le blocage ICMP sans forwarding, trois réponses après activation, trois réceptions complètes et la suppression réussie des ressources propres. Les noms `cp-MVd59SCa-c/g/s` et la réservation `/tmp/coopace-lab.MVd59SCa` ne sont plus visibles depuis l'environnement de développement.

Les six messages `Serveur TCP de laboratoire arrêté : context canceled` suivent chacun un arrêt volontaire de la cible après la série. Ils sont attendus dans ce protocole et ne signalent pas un échec de transfert ou de mesure. Les interruptions et pannes ne sont pas injectées dans cet essai ; leurs tests restent simulés ou limités aux processus locaux de test. Le nettoyage d'espaces neufs n'est pas une restauration indépendante de passerelle réelle.

## Prochaine activité

Définir un goulot virtuel contrôlé et les critères de comparaison avant un premier essai de gestion des files. Préparer le périmètre de restauration et ses tests avant de piloter une politique. Le présent jeu de séries fournit un contrôle fonctionnel sans goulot ; il ne remplace pas les références WAN ni les métriques IPv6/DNS, débit utile, équité et ressources du [périmètre produit](PRODUCT.md).

Voir le [protocole des séries](VIRTUAL_SERIES.md) et la [feuille de route](ROADMAP.md).
