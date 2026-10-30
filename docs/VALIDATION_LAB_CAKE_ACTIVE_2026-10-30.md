# Premier contrôle natif du chemin actif CAKE — 30 octobre 2026 (UTC)

## Résultat et portée

Les **quatre contrôles ont un code `0`** : transfert normal et mort forcée du pilote sous TBF, puis les deux mêmes modes sous CAKE. Les contrôles TBF revérifient l'activation et le pilote communs ; CAKE dispose de son propre validateur et de ses journaux de relevés.

Le chemin actif CAKE est validé pour un transfert synthétique complet, dix sondes TCP, collecte périodique et nettoyage après mort forcée. Les rapports gardent `congestion: not_assessed`. Il ne s'agit pas des six campagnes du [protocole comparatif](CAKE_COMPARISON.md) : aucune phase idle, aucun bloc alterné et aucune qualification de bénéfice CAKE ou Coopace ne sont produits ici. Voir le [contrôle fonctionnel](LAB_CAKE_ACTIVE.md) et son [préalable DOWN](VALIDATION_LAB_CAKE_2026-10-30.md).

## Transferts et sondes vérifiés

Les deux modes normaux ont chacun écrit et reçu exactement 8 388 608 octets, avec EOF et rapports conformes, soit 16 Mio utiles complets. Les vingt tentatives de mesure TCP ont réussi, sans échec. Les fenêtres des sondes sont entièrement comprises dans les écritures applicatives ; la stabilisation dépasse 1s dans les deux contrôles.

| Observation descriptive | TBF normal | CAKE normal |
| --- | --- | --- |
| Volume reçu | 8 388 608 octets | 8 388 608 octets |
| Durée monotone première lecture → EOF | 17 422.237605ms | 17 546.961814ms |
| Débit utile applicatif reçu | 481 488.554466 octets/s | 478 066.122724 octets/s |
| Connexions réussies / échouées | 10 / 0 | 10 / 0 |
| p50 d'établissement TCP | 204.672512ms | 1.459793ms |
| Minimum / maximum TCP | 186.144721 / 255.603996ms | 1.248882 / 2.180536ms |
| Stabilisation avant sondes | 1 030.054491ms | 1 027.059562ms |

Ces observations sont conservées séparément, sans calcul de gain comparatif. Le scénario CAKE commence son émission à `2026-10-30T12:39:22.078084588Z` et termine la réception à `12:39:39.625533994Z`. Ses sondes vont de `12:39:23.105423838Z` à `12:39:25.375036482Z`. Les volumes, durées, débits et statistiques ont été recalculés depuis les rapports et les dix tentatives originales. Avec dix réussites, p95/p99 correspondent au maximum observé et restent exploratoires.

## Configuration et relevés CAKE

Toutes les lectures sont conformes après ajout, après activation, pendant les observations et après fin du pilote : une racine CAKE `10:` sur `wan`, 500 000 octets/s, `besteffort`, `flows`, mode raw, RTT 100 000µs, budget mémoire 1 048 576 octets et options statiques du protocole. Le producteur est iproute2-6.1.0 ; les omissions justifiées restent distinctes des statistiques manquantes. Le forwarding IPv4 est activé et relu dans la passerelle neuve ; le transfert confirme le passage positif. Aucun contrôle ICMP n'est ajouté dans ce mode.

Le contrôle CAKE normal conserve 71 échantillons. Son journal contient 77 événements, dont 75 lectures de file : état initial, relectures de configuration et échantillons. Le journal crash contient huit événements, dont six lectures de file. Les objets bruts, configurations et statistiques normalisées ont été revalidés et rapprochés exactement des rapports, en retirant seulement les étiquettes de phase ajoutées après le relevé. Les deux journaux commencent par les ressources possédées et finissent par `cleaned`, avec les sorties, descendants et flux attendus.

Les commandes de statistiques CAKE normales durent de 10.738989 à 13.406209ms ; les pauses entre lectures périodiques vont de 254.199116 à 256.139974ms. Le vidage est confirmé par des lectures nulles espacées de 523.801872ms. Aucune baisse des cinq compteurs racine n'est observée. La différence avant pilote → après sa fin est recalculée :

| Compteur racine CAKE | Différence du contrôle normal |
| --- | --- |
| `bytes` | 8 774 612 |
| `packets` | 5 846 |
| `drops` | 148 |
| `overlimits` | 15 572 |
| `requeues` | 0 |

Ces valeurs décrivent la file, distinctes des octets utiles et d'un taux de perte de bout en bout. Les compteurs de classe ne sont pas additionnés à ceux de la racine ; ni mémoire ni backlog ne sont soustraits. La plus grande valeur `memory_used` fournie dans les relevés CAKE est de 32 720 octets, sans l'assimiler à une mesure de RAM courante. `capacity_estimate` n'est pas une mesure WAN.

## Pannes et nettoyage

| Contrôle | Sortie du pilote | Outils orphelins récupérés | Jeton des espaces/réservation |
| --- | --- | --- | --- |
| `tbf-check` | 0 | 0 | `3xnltlf1` |
| `tbf-check-crash` | -9 | 3 | `dtczmqmg` |
| `cake-check` | 0 | 0 | `hdebvqps` |
| `cake-check-crash` | -9 | 3 | `zkd9hjzi` |

Les modes crash imposent SIGKILL au pilote après sa première écriture, puis récupèrent les trois outils avant suppression des espaces. `flow` reste `null`. Les annulations et volumes partiels dans stderr sont attendus : 49 152 octets écrits/reçus sous TBF ; 49 152 écrits et 7 240 reçus sous CAKE. Ces journaux ne sont pas des rapports de transfert complet ; la dernière lecture de file précède l'arrêt des outils.

Les journaux confirment le nettoyage et les quatre rapports ont `cleanup_verified: true`. Les douze noms `cg-JETON-c/g/s` sont absents sous `/run/netns` et `/var/run/netns`, les quatre réservations `/tmp/coopace-guard.JETON` sont absentes et les seize PID consignés ne sont plus présents sous `/proc` au moment de la revue. Ces observations depuis l'environnement de développement complètent l'attestation du superviseur, sans prouver l'absence de références détenues par un processus étranger. Sa propre destruction et la restauration d'un réseau existant restent hors validation.

## Provenance et suite

Commit source : `3b3bae8481ed3a3ffe151cd4a98d8a6b8b02f766`. Dossier local : `.local/experiments/cake-active-validation-3b3bae8/`, préparé le `2026-10-30T12:29:22.679126+00:00`. Les 134 empreintes d'entrée, dont les outils système, sont conformes ; les sources suivies correspondent au commit. Les trois binaires Linux amd64/Go 1.27.3 déclarent ce commit avec `vcs.modified=false`. Le lancement consigne Linux `7.0.0-38-generic` et Python 3.12.3.

| Pièce CAKE | SHA-256 |
| --- | --- |
| `cake-check.json` | `82653419924ca448c7233c73def2eebbdca2b14f3472e45709263566d88ad97a` |
| `cake-check-crash.json` | `a817bb4d4abe05189cffd49c1b5b451311ae0a78358ea102f367057e456c66f4` |
| `cake-check.evidence.jsonl` | `ca27e3a0e0be85b12d50f4fffca2bb9d52c25dbd5b9ad663beec6adee4585041` |
| `cake-check-crash.evidence.jsonl` | `c043713fe6a0d3014dfc63c216e9c27e10c0feb94a0b55c8deecdbbaad397d2a` |

Les protocoles figés et données brutes restent inchangés ; aucun trafic n'a été relancé pendant la revue. `prepared.json` garde son état historique `not_run`. Le nouveau `validation.json` consigne les calculs et empreintes de trente et une pièces, dont le script de revue ; les journaux de preuves et binaires restent locaux et exclus de Git.

La prochaine sous-étape intègre CAKE aux campagnes avec phases idle/loaded et contrôles de passage, puis développera l'orchestration des six campagnes et l'agrégateur des neuf comparaisons. Les paramètres et critères comparatifs v1 restent inchangés ; l'étape 4.2, les références WAN et les validations du produit restent ouvertes.
