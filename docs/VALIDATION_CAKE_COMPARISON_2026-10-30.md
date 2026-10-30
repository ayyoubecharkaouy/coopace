# Première comparaison native TBF/CAKE — 30 octobre 2026 (UTC)

## Résultat et portée

Les quatre commandes ont un code **`0`** : contrôles de panne TBF et CAKE, six campagnes comparatives, puis relecture hors ligne. La décision **`static_cake_improvement_v1` est confirmée** : collecte exploitable, références TBF qualifiées, charge cohérente, garde-fous respectés et amélioration de latence dans les trois blocs. Chacun satisfait trois paires sur trois, contre deux exigées par le [protocole v1 fixé avant collecte](CAKE_COMPARISON.md).

Cette expérience valide le bénéfice de la configuration CAKE statique face à TBF dans ce laboratoire synthétique IPv4. Elle établit une référence du moteur existant pour Coopace ; le gain d'un futur contrôleur Coopace reste à évaluer. Les références WAN du foyer, la couverture IPv6/DNS, l'équité, le coût système et la restauration d'une passerelle réelle restent ouverts. L'étape 4.2 n'est pas clôturée par ce résultat.

## Collecte et critères vérifiés

Les blocs suivent TBF/CAKE, CAKE/TBF, TBF/CAKE. Chaque campagne possède trois espaces neufs et six phases idle/loaded, loaded/idle, idle/loaded. Les six campagnes conservent **360 connexions TCP réussies sans échec** et **18 réceptions exactes de 8 388 608 octets**, soit 144 Mio utiles. Les anciens essais ne sont pas réutilisés comme bras de comparaison.

Les paramètres effectifs sont revalidés dans tous les relevés : TBF à 4 Mbit/s, burst 65 536 et limite 131 072 octets ; CAKE à 4 Mbit/s avec les options statiques du protocole, une classe et budget mémoire de 1 048 576 octets. Le producteur est iproute2-6.1.0. La comparaison porte sur ces deux configurations complètes, avec leurs mécanismes et budgets respectifs.

La congestion TBF v1 est confirmée dans chacun des trois bras : progression des octets et lectures positives espacées pendant les sondes, débits cohérents et hausse de p50 requise. Les fenêtres de sondes loaded restent dans les écritures applicatives, après au moins 1s de stabilisation. Les octets progressent dans les 18 fenêtres ; toutes les réceptions, durées et débits ont été revalidés.

Les valeurs ci-dessous sont les différences signées p50 loaded−idle, calculées séparément pour chaque paire. Les comparaisons apparient uniquement les mêmes indices du même bloc.

| Bloc | Paire | Pénalité TBF (ms) | Pénalité CAKE (ms) | Réduction de pénalité (ms) | Rapport débit CAKE/TBF |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 237.487915 | 1.285819 | 236.202096 | 0.992898 |
| 1 | 2 | 204.230705 | 1.175586 | 203.055119 | 0.992963 |
| 1 | 3 | 204.811842 | 1.244464 | 203.567378 | 0.992878 |
| 2 | 1 | 189.050898 | 1.207159 | 187.843739 | 0.992976 |
| 2 | 2 | 204.049674 | 1.196502 | 202.853172 | 0.992883 |
| 2 | 3 | 237.492300 | 1.176804 | 236.315496 | 0.992962 |
| 3 | 1 | 241.879450 | 1.283551 | 240.595899 | 0.992982 |
| 3 | 2 | 213.272092 | 1.217829 | 212.054263 | 0.992882 |
| 3 | 3 | 204.195356 | 1.165382 | 203.029974 | 0.992932 |

Les neuf paires satisfont `D_T >= 10ms`, `D_C <= 0,5 × D_T` et `D_T − D_C >= 10ms`. Aucun percentile n'est moyenné. Les différences et seuils ont été vérifiés indépendamment avec des décimaux à partir des tentatives et rapports originaux.

| Observation | TBF | CAKE |
| --- | --- | --- |
| Plage des neuf p50 TCP loaded | 189.226840–242.119291ms | 1.389349–1.502324ms |
| Plage des neuf p50 TCP idle | 0.175942–0.255644ms | 0.171127–0.223967ms |
| Plage des neuf débits utiles reçus | 481 470.181000–481 523.139335 octets/s | 478 091.301491–478 125.706575 octets/s |
| Plage des neuf p95/p99 TCP loaded | 234.778604–255.969277ms | 1.523770–2.655963ms |

Les 18 débits appartiennent à [350 000 ; 525 000] octets/s. Les neuf rapports CAKE/TBF sont compris entre 0.992878476258 et 0.992982162463, au-dessus du seuil 0,90. Les 18 comparaisons d'échecs TCP sont conformes : zéro des deux côtés. Les neuf garde-fous idle passent ; les différences CAKE−TBF vont de −0.068714 à +0.039516ms, sous la borne +2ms. Aucun garde-fou n'est déclenché ni indisponible.

Avec dix tentatives par phase, p95/p99 correspondent au maximum observé et restent exploratoires. Il s'agit de durées d'établissement TCP, dans un petit protocole à trois blocs ; ces mesures ne constituent pas une généralité statistique ou une mesure applicative du foyer.

## Preuves, continuité et relecture

Les six campagnes conservent 1 539 échantillons de file : 765 sous TBF et 774 sous CAKE. Les journaux des campagnes TBF ont chacun 277 événements ; ceux des campagnes CAKE en ont 543. Les configurations, statistiques brutes/normalisées, différences de compteurs et lectures de vidage ont été revalidées et rapprochées des journaux. Les six contrôles ICMP donnent zéro réponse sans forwarding puis trois avec forwarding.

Les pauses périodiques vont de 250.193496 à 262.036954ms. Les vidages des 36 phases sont confirmés par deux lectures nulles espacées de 522.470286 à 525.246713ms. Aucune baisse de compteur n'est observée. Les compteurs de file restent distincts des octets utiles, des statistiques de classe et d'un taux de perte de bout en bout ; la mémoire CAKE rapportée garde sa signification de maximum historique pour ce producteur.

Les cinq intervalles entre retour confirmant le nettoyage et début de la campagne suivante vont de 2 090.656877 à 2 097.897138ms, au-dessus des 2s exigées. L'environnement et les empreintes des binaires, outils et sources d'exécution sont inchangés pendant les six campagnes.

La session va de `2026-10-30T15:51:17.873645+00:00` à `15:58:21.088934+00:00`, soit environ sept minutes. Les 18 comparaisons de la vraie CLI `latency compare` ont été reproduites pendant la revue. Le bilan recalculé correspond au rapport interne et aux sorties `comparison.json`/`reanalyze.json`, ces dernières étant identiques octet par octet. Aucun trafic n'a été relancé pendant cette analyse.

## Pannes et nettoyage

Les deux contrôles préalables terminent une phase idle de dix connexions puis tuent le pilote après la première écriture du premier transfert loaded. Chacun a une sortie de pilote `-9`, récupère trois outils orphelins et confirme le nettoyage. Les volumes partiels et annulations sont attendus : 49 152 octets écrits/reçus sous TBF, 49 152 écrits et 7 240 reçus sous CAKE. Ils restent hors des 18 transferts complets comparatifs.

| Exécution | Jeton des espaces et de la réservation |
| --- | --- |
| Contrôle de panne TBF | `s_axxzqu` |
| Contrôle de panne CAKE | `g72rac02` |
| Bloc 1 TBF | `mr2t1p9u` |
| Bloc 1 CAKE | `utudfyi7` |
| Bloc 2 CAKE | `rqfsadou` |
| Bloc 2 TBF | `g1mdm8lt` |
| Bloc 3 TBF | `luix7xz6` |
| Bloc 3 CAKE | `ivjfl556` |

Les huit rapports ont `cleanup_verified: true`. Les six pilotes normaux sortent avec `0`, sans descendant orphelin à récupérer. Les journaux confirment l'arrêt des processus puis le retrait des ressources. Les **24 noms** `cg-JETON-c/g/s` sont absents sous `/run/netns` et `/var/run/netns`, les **huit réservations** `/tmp/coopace-guard.JETON` sont absentes et les **68 PID consignés** ne sont plus présents sous `/proc` au moment de la revue.

Ces observations complètent l'attestation du superviseur sans prouver l'absence de références détenues par un processus étranger. La destruction du superviseur et la restauration d'une passerelle existante restent hors validation.

## Provenance et suite

Commit source : `c0edb808e203e5fff6e5412542e7b52f1c920bf1`. Dossier local : `.local/experiments/comparison-validation-c0edb80/`, préparé le `2026-10-30T15:39:54.907675+00:00`. Les **152 empreintes d'entrée** sont conformes ; les sources suivies correspondent au commit. Les trois binaires Linux amd64/Go 1.27.3 déclarent cette révision avec `vcs.modified=false`. Le lancement consigne Linux `7.0.0-38-generic` et Python 3.12.3.

| Pièce | SHA-256 |
| --- | --- |
| `comparison.json`, `reanalyze.json`, `comparison/comparison.json` | `31db7948c2e2a97977a53e5f136d7b44c4ae13c7d19f840b09641404bf7549ce` |
| `comparison/session.json` | `f66a5399b80b087aaea5dfd1cfa8eabf4bb7a19cd80a40c4e77442500c915b78` |
| `comparison/environment.json` | `0d4adac60dacf8a59eb739cfff913f661caf40bd164118cc10cd072ddc036256` |

Les fichiers figés et données brutes restent inchangés. `prepared.json` garde son état historique `not_run`. Le nouveau `validation.json` consigne les calculs indépendants et les empreintes de 101 pièces, dont le script de revue ; les preuves et binaires restent locaux et exclus de Git.

La suite doit définir les conditions d'intégration de CAKE dans la passerelle Coopace et les critères d'évaluation d'un premier pilotage déterministe face à cette référence. Le [périmètre produit](PRODUCT.md) demande de conserver une solution simple si le moteur existant suffit et de différer l'automatisation réelle tant que restauration, couverture et coût système ne sont pas maîtrisés. Le ML reste différé.
