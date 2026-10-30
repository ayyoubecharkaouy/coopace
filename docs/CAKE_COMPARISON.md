# TBF et CAKE statique — protocole comparatif v1

## État et question

**Protocole défini avant collecte ; adaptation CAKE et pilote comparatif non implémentés. Aucun essai CAKE réalisé.** Le [goulot TBF déjà qualifié](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) permet de préparer cette comparaison. Ses résultats historiques ne deviennent pas le bras TBF d'une nouvelle expérience.

Question : dans le même scénario IPv4 synthétique, CAKE statique à 4 Mbit/s réduit-il la pénalité de durée d'établissement TCP sous charge, tout en préservant le débit utile, les connexions et le comportement au repos ? Il s'agit de comparer deux configurations de files existantes. « Manuel » signifie paramètres statiques explicitement choisis, sans adaptation Coopace ; le laboratoire peut les appliquer par un pilote supervisé.

Cette expérience prépare la référence du moteur existant demandée par le [périmètre produit](PRODUCT.md). Elle ne compare pas encore CAKE à un contrôleur Coopace et ne mesure pas le réseau du foyer. Tout changement de paramètres, ordre ou seuil après un essai exigera un nouveau protocole et un nouveau dossier ; conserver les résultats défavorables et incomplets.

## Deux configurations fixes

Reprendre exactement les trois espaces client/passerelle/serveur, adresses, routes spécifiques et contrôles ICMP de la [campagne TBF](LAB_CAMPAIGN.md). Chaque campagne utilise une topologie neuve, une seule racine `10:` sur la sortie virtuelle `wan` et un seul moteur pendant ses six phases. Aucun empilement CAKE sur TBF, changement en place, NAT, route par défaut ou raccordement physique.

| Paramètre | TBF | CAKE |
| --- | --- | --- |
| Débit nominal de sortie | `4mbit` | `bandwidth 4mbit`, fixe |
| Configuration de référence | FIFO de TBF, `burst 65536`, `limit 131072`, sans peakrate | Une classe `besteffort`, isolation `flows` |
| Compensation et direction | Paramètres de la référence TBF v1 | `raw`, `mpu 0`, `egress` |
| Réglage du temps | Aucun délai injecté | `rtt 100ms`, aucun délai injecté |
| Autres options | Aucun autre objet ajouté | `nonat`, `nowash`, `split-gso`, `no-ack-filter`, `fwmark 0` |
| Budget de file/mémoire | Limite de FIFO 131 072 octets | `memlimit 1048576`, budget mémoire de 1 Mio |

Les arguments CAKE prévus pour le futur ajout dans l'espace possédé sont :

```text
cake bandwidth 4mbit besteffort flows nonat nowash raw mpu 0
rtt 100ms split-gso no-ack-filter egress memlimit 1048576 fwmark 0
```

Ce bloc décrit des arguments ; aucune commande privilégiée exécutable n'est livrée ici. Le [manuel officiel iproute2 v6.1.0](https://github.com/iproute2/iproute2/blob/v6.1.0/man/man8/tc-cake.8) décrit ces options. Le RTT règle CAKE, sans ajouter 100ms au chemin. Le budget `memlimit` inclut les structures des paquets et n'est pas une longueur de FIFO équivalente à celle de TBF. La comparaison porte donc sur les configurations complètes, avec leurs mécanismes de limitation, isolation, gestion de file et segmentation.

Avant chaque campagne, lire l'état initial du lien neuf DOWN, refuser toute racine étrangère, ajouter le moteur sans remplacement, puis vérifier tous les paramètres après ajout, activation, contrôles ICMP et fin du pilote. CAKE doit annoncer un débit de 500 000 octets/s, un RTT de 100 000µs et le budget mémoire demandé. Vérifier aussi les options non numériques et une seule classe de statistiques. Conserver paramètres demandés et effectifs ; un champ requis absent, ambigu ou non vérifiable rend l'essai non exploitable, sans correction silencieuse.

Consigner noyau, `tc -V`, Python, version Go, provenance et empreintes des trois binaires, sources et protocole. Les six campagnes doivent utiliser le même environnement et les mêmes binaires. La présence du manuel ou de l'analyseur tc ne prouve pas la disponibilité de CAKE dans le noyau : seul un ajout/relevé réussi dans un espace neuf le confirmera. Un refus arrête l'essai ; aucun chargement manuel de module, installation ou repli vers un autre moteur n'est prévu.

## Ordre et volume prévus

Trois blocs comparatifs contiennent chacun deux campagnes complètes :

| Bloc | Première campagne | Deuxième campagne |
| --- | --- | --- |
| 1 | TBF | CAKE |
| 2 | CAKE | TBF |
| 3 | TBF | CAKE |

À l'intérieur de chaque campagne, conserver les trois paires idle/loaded, loaded/idle, idle/loaded. Les paires de même indice sont comparées entre moteurs **dans le même bloc**. L'ordre alterné est fixé, sans sélection du meilleur essai ; avec trois blocs il n'est pas parfaitement équilibré. Ce petit protocole exploratoire ne démontre pas une généralité statistique.

Au total, hors contrôles préalables : **six topologies, 36 phases, 360 tentatives TCP et 18 transferts de 8 Mio, soit 144 Mio utiles attendus**. Il y a neuf comparaisons de paires, sans réemploi d'un ancien relevé. Attendre au moins 2s après nettoyage confirmé avant la campagne suivante. Chaque campagne garde les bornes pilote 150s, superviseur 180s et nettoyage 10s. Le lanceur exécute les six campagnes successivement ; il ne tue pas le superviseur par SIGKILL pour faire respecter une durée globale.

Reprendre sans modification les paramètres de mesure : dix connexions vers `10.203.0.6:46001`, timeout 1s, pause 250ms ; cible 100 acceptations/30s ; charge de 8 388 608 octets vers `10.203.0.6:46002`, plafond applicatif 1 048 576 octets/s, émission 25s et réception 28s. Attendre au moins 1s après première écriture avant les sondes loaded et vérifier leur recouvrement complet avec les écritures. Arrêter/récupérer les outils et vérifier deux lectures de file vide espacées d'au moins 500ms, sous 3s, avant la phase suivante.

## Mesures et disponibilité

Conserver chaque tentative, les échecs, le rapport complet d'émission et de réception, les durées monotones, les paramètres et les relevés de file. Appliquer la même validation stricte des rapports TCP et reproduire `latency compare` pour chaque paire au sein de chaque moteur. Ce comparateur actuel ne calcule pas une comparaison TBF/CAKE ; un agrégateur distinct reste à développer.

Lire `tc -j -s -r` avant/après les phases et périodiquement avec une pause d'au moins 250ms après chaque lecture. Conserver les dates réelles et durées, les cinq compteurs cumulés `bytes`, `packets`, `drops`, `overlimits`, `requeues` et les jauges `backlog`, `qlen`. Une baisse, même entre phases, invalide la différence concernée ; aucun champ manquant ne devient zéro. Les compteurs ne sont ni les octets utiles ni un taux de perte de bout en bout.

Pour CAKE, garder aussi les statistiques de classe et de mémoire disponibles. Le [code d'export JSON iproute2 v6.1.0](https://github.com/iproute2/iproute2/blob/v6.1.0/tc/q_cake.c) décrit les options, `tins`, `memory_used` et `memory_limit`. Une seule entrée `tins` et une limite mémoire vérifiable sont requises ici. Ce producteur omet `mpu` quand il vaut zéro et peut omettre `atm` en mode raw : reconnaître ces deux cas seulement avec un profil de producteur identifié, conserver l'omission et sa justification dans la normalisation. Ce n'est pas une autorisation de remplacer un compteur absent par zéro. Les autres détails absents restent explicitement indisponibles. L'adaptation CAKE devra avoir ses propres validations ; ne pas réutiliser le validateur TBF sur ce schéma. Ne pas sommer les compteurs racine et ceux de la classe, ni interpréter `capacity_estimate` comme une mesure de capacité WAN.

Le bras TBF doit satisfaire son [protocole v1 de congestion](VIRTUAL_BOTTLENECK.md) à chaque bloc. Pour CAKE, exiger des compteurs d'octets en progression dans chaque fenêtre loaded, la réception complète et le débit dans l'intervalle ci-dessous. **Ne pas exiger un backlog CAKE durablement positif** : une file brève ou vide aux instants lus ne constitue pas un échec de la gestion de file.

## Calculs et critères préalables

Pour chaque bloc `b` et indice de paire `i`, calculer séparément :

```text
D_T(b,i) = p50_loaded_TBF  - p50_idle_TBF
D_C(b,i) = p50_loaded_CAKE - p50_idle_CAKE
écart de pénalité = D_T(b,i) - D_C(b,i)
rapport de débit = débit_reçu_CAKE(b,i) / débit_reçu_TBF(b,i)
```

Garder les différences signées. Les percentiles indisponibles restent indisponibles ; la paire ne satisfait alors pas le critère de latence et reste dans le dénominateur des trois paires. Aucun échec TCP ne devient une durée nulle. Ne pas moyenner les percentiles ni choisir un sous-ensemble de blocs. Appliquer les seuils inclusifs avec une représentation évitant les erreurs d'arrondi aux frontières.

| Condition | Critère fixé |
| --- | --- |
| Collecte exploitable | Six campagnes complètes, paramètres vérifiés, rapports stricts, 18 réceptions exactes, recouvrement/stabilisation conformes, statistiques exploitables et nettoyage confirmé. |
| Référence TBF qualifiée | Congestion observée selon TBF v1 dans chacun des trois bras TBF neufs. Sinon aucune conclusion d'amélioration. |
| Débit cohérent | Les 18 débits reçus sont compris entre 350 000 et 525 000 octets/s ; les compteurs progressent pendant les fenêtres loaded. |
| Débit préservé | Dans chacune des neuf comparaisons, rapport de débit CAKE/TBF supérieur ou égal à 0,90. |
| Connexions préservées | Pour chacune des 18 comparaisons de phases idle ou loaded, nombre d'échecs CAKE inférieur ou égal à celui de TBF. |
| Repos préservé | Pour chacune des neuf paires, `p50_idle_CAKE <= p50_idle_TBF + 2ms`. Une valeur indisponible ne satisfait pas ce garde-fou. |
| Latence améliorée dans un bloc | Dans au moins deux de ses trois paires : `D_T >= 10ms`, `D_C <= 0,5 × D_T` et `D_T - D_C >= 10ms`. |
| Amélioration CAKE selon ce protocole | Collecte exploitable, référence TBF qualifiée, débit cohérent/préservé, connexions/repos préservés, et critère de latence satisfait dans les trois blocs. |

Ces seuils de moitié, 10ms, 90% et 2ms sont des critères exploratoires de ce laboratoire, pas des engagements du produit. Le RTT configuré n'est pas ajusté à partir des résultats CAKE. Rapporter aussi p95/p99, mais sans seuil de décision sur ces queues de distribution avec dix tentatives seulement. CPU/mémoire système, équité entre appareils, trafic descendant, UDP/QUIC, IPv6 et DNS restent à évaluer dans d'autres protocoles.

Séparer validité technique et conclusion expérimentale :

- Collecte incomplète, statistiques manquantes, paramètres incorrects ou nettoyage non confirmé : **non exploitable**, preuves conservées et code non nul.
- Collecte complète mais référence TBF non qualifiée : **référence non qualifiée**, aucune amélioration conclue.
- Référence qualifiée mais intervalle de débit cohérent ou progression de charge CAKE non respectés : **scénario de charge non qualifié**, aucune amélioration conclue.
- Référence et charge qualifiées mais garde-fou de débit préservé, échecs ou repos non satisfait : **garde-fou non satisfait**, détailler les régressions chiffrées et les valeurs indisponibles séparément ; cette décision prime sur une baisse de latence.
- Référence et garde-fous conformes mais critère de latence incomplet : **amélioration non démontrée**.
- Toutes les conditions réunies : **amélioration de cette configuration CAKE dans ce scénario selon v1**.

Une collecte exploitable garde un code `0` même si elle ne démontre pas d'amélioration ou déclenche un garde-fou ; le résultat scientifique doit être explicite. Un résultat défavorable ne provoque ni modification de configuration pendant les campagnes ni reprise sélective : terminer la collecte bornée si le fonctionnement technique reste conforme. Une panne technique arrête le lanceur, qui conserve aussi les campagnes déjà terminées.

## Nettoyage, preuves et prochaine implémentation

Avant les six campagnes, développer puis valider séparément l'ajout/relecture de CAKE sur lien DOWN, sa réception/statistique sur chemin actif, le nettoyage normal et la mort forcée du pilote après première écriture. Réutiliser le superviseur indépendant validé, ses identités d'espaces, le leader non récupéré avant les derniers signaux et ses limites de nettoyage. Tester aussi rejet d'une configuration inattendue, champs manquants, interruption et échec de suppression. Les contrôles natifs CAKE doivent réussir avant la collecte comparative, sans entrer dans ses 18 transferts.

Le retrait des espaces possédés supprime uniquement leurs liens, routes, forwarding et file. Ce nettoyage jetable ne devient pas une restauration du foyer. En cas de doute sur une identité ou l'arrêt d'un processus, conserver le journal et signaler le nettoyage incomplet. Ne pas détruire d'objet étranger ni promettre la survie à la destruction du superviseur.

Préparer un dossier neuf avec une copie figée de ce protocole, commit, versions, empreintes et binaires. Prévoir six sous-dossiers indexés par bloc/moteur, plus les contrôles préalables séparés. Conserver stdout/stderr/codes, rapports de phases, journaux intermédiaires, relectures tc et comparaisons hors ligne, y compris pour les essais invalides. Les données restent locales, sans contenu applicatif, identifiants d'appareils du foyer ni transmission au groupe/ML. Ne publier un bilan de nettoyage réussi qu'après confirmation du superviseur.

La prochaine sous-étape est l'adaptation CAKE et son contrôle de cycle de vie DOWN, séparés du module TBF existant. Viendront ensuite le contrôle actif et de panne, l'orchestration des six campagnes et l'agrégateur des neuf comparaisons. Les commandes actuelles restent TBF ; ce document n'annonce aucun mode CAKE disponible. Le pilotage Coopace ne viendra qu'après une référence statique évaluée.
