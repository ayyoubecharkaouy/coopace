# Goulot virtuel contrôlé — protocole v1

## État et question

**La première campagne native est validée, avec congestion observée selon les critères v1.** Le [compte rendu du 30 octobre](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) conserve les six phases, 60 connexions réussies, trois transferts et le contrôle de panne. Son [fonctionnement, ses sorties et son contrôle de panne](LAB_CAMPAIGN.md) sont documentés séparément ; les paramètres et critères v1 ci-dessous restent inchangés. Un [contrôle fonctionnel préalable](LAB_ACTIVE.md), avec un seul transfert et une collecte périodique, est implémenté, testé avec des outils simulés et [validé en natif](VALIDATION_LAB_ACTIVE_2026-10-30.md). Le [cycle de vie d'une file TBF sur lien désactivé](LAB_QUEUE.md) est implémenté, testé avec des outils simulés et [validé en natif](VALIDATION_LAB_QUEUE_2026-10-29.md). Les [premières séries natives sans goulot](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) valident la collecte et son recouvrement avec un transfert, sans démontrer de congestion.

Cette expérience répond à la question suivante : une limitation connue sur la sortie de la passerelle produit-elle une file observable et une augmentation répétée de la durée d'établissement TCP sous charge ? Elle prépare ensuite une référence CAKE manuelle, avant tout pilotage Coopace.

Les paramètres ci-dessous sont ceux fixés avant la première collecte. Toute modification après un essai exigera une nouvelle version du protocole et un nouveau dossier de résultats ; conserver aussi les essais invalides et sans congestion démontrée. Les commandes actuelles `run`, `run-tcp`, `run-load` et `run-series` gardent leur comportement.

## Point d'application

```text
client eth0           passerelle neuve                    serveur eth0
10.203.0.2 -> lan 10.203.0.1 -> wan 10.203.0.5 -> 10.203.0.6
                               [file de sortie]
```

Conserver les trois espaces réseau neufs, les routes spécifiques et les contrôles ICMP du [laboratoire existant](VIRTUAL_LAB.md). Le seul nouvel objet prévu est une file racine sur `wan`, **dans l'espace passerelle créé par cette exécution**. Les données de charge et les SYN client → serveur empruntent cette sortie ; les réponses reviennent sans limitation ajoutée. Le nom `wan` désigne ici un lien virtuel.

Le mécanisme retenu est TBF avec sa FIFO par défaut : il fournit une limitation moyenne et une réserve de jetons autorisant des rafales ; `limit` borne les octets en attente. Ces propriétés sont décrites dans le [manuel TBF du projet iproute2](https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2/+/6e15d27aae947510efd824c7ce4bc7ea3b8a5aae/man/man8/tc-tbf.8). Le choix de TBF sert à créer la référence congestionnée, pas à revendiquer une optimisation.

| Paramètre de file | Valeur prévue |
| --- | --- |
| Type et identifiant | Racine `tbf`, handle `10:`, sans file enfant ajoutée. |
| Débit | `4mbit` : 4 000 000 bits/s, soit 500 000 octets/s avant distinction entre charge utile et octets comptés par la file. |
| Réserve de jetons `burst` | 65 536 octets. |
| Capacité de FIFO `limit` | 131 072 octets. |
| Limitation de pointe | Aucune `peakrate` ajoutée. |
| Interfaces et sens | Uniquement sortie `wan` de la passerelle virtuelle ; aucun réglage sur l'hôte, `lan` ou le serveur. |

À titre de dimensionnement, vider 131 072 octets à 500 000 octets/s représente environ 262ms. Ce calcul n'est ni une mesure ni une garantie de latence : rafales, segmentation, retransmissions et ordonnancement restent à observer. La réserve de 65 536 octets évite de dimensionner le scénario uniquement pour de petits paquets ; elle ne garantit pas la compatibilité avec toutes les tailles de paquets agrégés.

Utiliser une création explicite de file, jamais un remplacement silencieux. Lire l'état initial ; refuser une file racine préexistante autre que l'état attendu du lien neuf. Relire ensuite le type, le handle et les paramètres effectifs. Un outil absent, une option non reconnue ou un refus du noyau arrête l'essai. Aucun chargement manuel de module ou changement d'offload sur l'hôte n'est prévu.

## Collecte prévue

La file TBF restera identique pendant toutes les phases ; `idle` désignera l'absence du transfert propre au scénario. Les anciens résultats sans file ne serviront pas de référence interchangeable pour cette expérience.

| Paramètre | Valeur prévue |
| --- | --- |
| Paires | Trois : idle → loaded, loaded → idle, idle → loaded. |
| Latence | Dix établissements TCP vers `10.203.0.6:46001` par phase, intervalle 250ms, timeout **1s** par tentative. |
| Cible temporaire | 100 acceptations au maximum, durée 30s ; arrêt explicite après chaque mesure. |
| Charge de chaque phase loaded | 8 388 608 octets vers `10.203.0.6:46002`, plafond moyen applicatif de 1 048 576 octets/s. |
| Délais de charge | Émetteur 25s, récepteur 28s. Les délais actuels de 12s/15s restent propres aux modes sans goulot. |
| Stabilisation | Attendre au moins 1s après la première écriture de charge avant de lancer la mesure loaded. |
| Entre phases | Transfert entièrement reçu, processus arrêtés et file vide à deux lectures espacées d'au moins 500ms. Arrêt si ce contrôle dépasse 3s. |
| Observation de la file | Lectures JSON détaillées avec statistiques, horodatées avant/après chaque phase et toutes les 250ms pendant la mesure. |
| Limites du pilote | Disponibilité d'un outil 5s, commande de latence 16s, campagne 150s. |

Le temps nominal du transfert au débit configuré est d'environ 16,8s, avant les effets de protocole et de rafale. Il justifie d'allonger les délais plutôt que de réutiliser ceux du réseau sans goulot. La charge proposée dépasse le débit de la file ; cela ne suffit pas à prouver que le TCP l'alimente durablement.

Conserver chaque tentative, y compris les échecs. Avec dix réussites, p95/p99 sont le maximum observé ; aucune moyenne des percentiles entre séries ni estimation fiable de distribution n'en sera déduite. Un timeout ne devient pas une durée nulle. Si une série n'a aucune réussite, ses percentiles sont indisponibles et le critère de latence ci-dessous ne peut pas être satisfait.

Vérifier que la fenêtre complète de mesure loaded est comprise dans la fenêtre première/dernière écriture de charge, comme dans les [séries existantes](VIRTUAL_SERIES.md). Ce contrôle conservateur peut échouer si le noyau a déjà accepté toutes les données alors que leur livraison continue : conserver alors l'essai comme non exploitable selon ce protocole, sans prolonger artificiellement les horodatages. Les statistiques de file apportent une observation complémentaire, sans établir une saturation continue entre deux lectures.

## Preuves et critères fixés avant l'essai

Deux décisions distinctes seront consignées : validité technique de la collecte et présence d'une congestion selon les critères suivants. Le code de sortie du pilote attestera la collecte et le nettoyage ; la décision expérimentale figurera séparément dans le résultat.

| Décision | Conditions cumulatives |
| --- | --- |
| Collecte techniquement valide | Trois paires complètes, paramètres effectifs conformes, rapports strictement validés, recouvrement vérifié, trois réceptions exactes de 8 Mio, statistiques de file disponibles et nettoyage vérifié. |
| Goulot alimenté pendant chaque mesure loaded | Compteurs de la file en progression et au moins trois lectures avec octets en attente strictement positifs, espacées chacune d'au moins 200ms dans la fenêtre de mesure. |
| Débit cohérent avec le scénario | Pour chaque transfert, débit utile reçu compris entre 350 000 et 525 000 octets/s, calculé sur une durée monotone entre premier octet reçu et fin de réception. Cette tolérance exploratoire de 70 à 105% du débit configuré tient compte des protocoles et de la réserve initiale. |
| Effet sur la latence | Dans au moins deux des trois paires, `p50_loaded - p50_idle >= 10ms`, avec au moins une connexion réussie par série. Rapporter aussi tous les échecs, même lorsque ce seuil est satisfait. |
| Congestion observée selon ce protocole | Collecte valide, critères de file et de débit satisfaits dans les trois phases loaded, et critère de latence satisfait. |

Les seuils de 10ms et de débit servent à qualifier ce petit laboratoire ; ils ne proviennent pas d'un objectif de service du foyer. Une collecte valide qui ne satisfait pas ces critères conclura **« congestion non démontrée selon ce protocole »**. Une collecte incomplète conclura **« essai non exploitable »**. Aucun de ces résultats ne sera transformé en bénéfice d'optimisation.

Le rapport d'émission ne fournit pas le débit reçu nécessaire. Le [rapport optionnel du récepteur](LAB_INSTRUMENTATION.md) fournit maintenant le volume exact, les premières/dernières lectures et la durée monotone jusqu'à EOF ; sa [première validation native en boucle locale](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) est consignée, et son intégration à cette collecte est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md). Le débit moyen d'écriture dans la socket ne mesure pas la livraison. Conserver aussi les sorties brutes et dates des lectures de file, octets/paquets envoyés, backlog, drops, overlimits et requeues disponibles. Les drops de la file, les échecs de connexion et les pertes de paquets ne sont pas des métriques interchangeables.

La lecture des statistiques utilise les options JSON, valeurs brutes et statistiques de `tc` (`-j -s -r`), exécuté explicitement dans l'espace passerelle. Les [lectures et différences](LAB_INSTRUMENTATION.md) sont implémentées et [validées en natif](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) à zéro sur liens désactivés ; les progressions et la collecte périodique sont maintenant [validées en natif](VALIDATION_LAB_ACTIVE_2026-10-30.md) sur un transfert. Les remises à zéro restent testées avec des outils simulés. La collecte périodique est intégrée au contrôle fonctionnel préalable ; son intégration à la campagne de trois paires est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md). Voir le [manuel tc d'iproute2](https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2/+/refs/heads/main/man/man8/tc.8). Une différence de compteurs n'est exploitable que si le même objet est resté présent et si ses compteurs n'ont pas diminué.

## Nettoyage et restauration avant la création de file

Le périmètre de cet essai est jetable : arrêter les processus possédés puis supprimer les trois espaces créés retire aussi leurs liens, routes, forwarding et file. La configuration du foyer n'entre pas dans ce périmètre. Le comportement prévu en cas de panne est **l'arrêt et la suppression du laboratoire**, sans maintien d'un service réseau.

Avant d'exécuter le nouveau scénario, préparer et vérifier :

1. Un responsable du nettoyage extérieur aux espaces, indépendant du pilote de mesures, armé avant la création de file. Il connaît uniquement les noms et processus effectivement créés ; une collision ne lui donne aucun droit de suppression sur un objet existant.
2. Une détection de disparition du pilote sans ambiguïté de réutilisation de PID, ainsi qu'une échéance indépendante maximale de 180s. Après déclenchement, le nettoyage dispose de 10s ; un dépassement reste un échec consigné, sans annonce de restauration réussie.
3. L'arrêt et la récupération des seuls processus possédés avant suppression des espaces. Ne pas supprimer seulement le nom d'un espace en laissant un processus le maintenir actif.
4. Des vérifications explicites de disparition des noms et de la réservation temporaire, puis la publication du rapport final seulement si le nettoyage réussit. Conserver les données intermédiaires dans le dossier de l'expérience pour diagnostiquer un échec.
5. Des tests simulés d'échec de création/relecture de file, d'interruption, de mort du pilote et d'échec de nettoyage. Valider ensuite en exécution native le succès normal et la mort forcée du pilote, avant la campagne de mesures.

Un [premier superviseur indépendant](LAB_GUARD.md) est implémenté pour les contrôles de fin normale et de mort forcée du pilote, avec récupération du descendant. Ses premiers essais sans file puis le [cycle de vie TBF sur lien désactivé](VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés en natif ; les erreurs d'ajout/relecture sont couvertes par les tests simulés. Son intégration à la campagne de mesures avec goulot actif est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md), y compris la mort forcée du pilote après la première écriture. Il ne promet pas de survivre à sa propre destruction, à celle de tous les processus ou à une panne de l'hôte. Ces cas pourront laisser des ressources et nécessiter une récupération ciblée à partir du journal. Ce nettoyage jetable ne valide pas la restauration indépendante d'une passerelle réelle avec IPv4, IPv6 et DNS, toujours requise par le [protocole passerelle](GATEWAY_BASELINE.md).

## Comparaisons ultérieures et ordre de développement

La référence suivante sera CAKE statique, configuré explicitement au même débit nominal de 4mbit dans une nouvelle instance du laboratoire. Prévoir une seule classe `besteffort`, isolation `flows`, `nonat`, compensation `raw`, RTT de réglage 100ms, `split-gso`, sans filtrage des ACK. Ces options décrivent le moteur existant dans le [manuel CAKE d'iproute2](https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2-next/+/refs/heads/master/man/man8/tc-cake.8) ; le RTT de réglage n'est pas un délai injecté. Le [protocole comparatif TBF/CAKE statique v1](CAKE_COMPARISON.md) fixe maintenant six campagnes neuves, leurs ordres et leurs seuils avant collecte ; le [contrôle de cycle de vie CAKE DOWN](VALIDATION_LAB_CAKE_2026-10-30.md) est validé en natif, tandis que le [contrôle fonctionnel CAKE actif](LAB_CAKE_ACTIVE.md) est implémenté et testé avec des commandes réseau simulées, en attente de validation native. Le pilote comparatif reste à développer.

Comparer TBF/FIFO à CAKE au même débit étudiera ces deux configurations de files. Cela ne simulera pas une liaison physique indépendante de CAKE et ne démontrera pas un bénéfice propre à Coopace. Le pilotage Coopace viendra seulement après cette référence manuelle. Équité entre hôtes, ressources, trafic descendant, UDP/QUIC, IPv6 et DNS resteront à évaluer séparément.

Les contrôles natifs du superviseur sans file et du [cycle de vie de la file sur lien désactivé](VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés. Le [rapport du récepteur et les statistiques de file](LAB_INSTRUMENTATION.md) sont implémentés et leurs [premiers contrôles natifs](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) sont validés. Le [contrôle fonctionnel actif](LAB_ACTIVE.md) intègre maintenant le passage TCP et la collecte périodique ; sa [première validation native](VALIDATION_LAB_ACTIVE_2026-10-30.md) est consignée. Les [trois paires et leurs contrôles de passage](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) sont validés. Le [protocole comparatif avec CAKE statique](CAKE_COMPARISON.md) est maintenant défini. La prochaine sous-étape est la validation native du contrôle fonctionnel CAKE actif et de panne ; chaque nouvelle collecte exige un nouveau dossier avec protocole, commit et empreintes figés. L'étape 4.2 reste ouverte.
