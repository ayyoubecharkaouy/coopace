# Séries de latence sans et avec transfert synthétique

## Objectif et état

Le chemin IPv4 et le [transfert borné de 8 Mio](VALIDATION_VIRTUAL_LOAD_2026-10-29.md) sont validés séparément. Le mode `run-series` prépare leur association : six séries de latence, dont trois pendant un transfert, sur une même instance du laboratoire.

Le code et les tests simulés sont livrés. **Un premier essai natif est validé** : six séries, 60 connexions réussies sans échec, trois transferts complets et recouvrement vérifié. Le [compte rendu](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) conserve les résultats, empreintes et limites. La création d'un réseau virtuel rapide, sans goulot configuré, ne garantit pas de congestion. Cet essai mesure une différence descriptive, sans intervention d'optimisation.

## Paramètres fixés avant la collecte

| Paramètre | Valeur |
| --- | --- |
| Topologie | Une instance client → passerelle → serveur, créée et nettoyée par `lab-network.sh`. |
| Paires | Trois, chacune avec une série `idle` et une série `loaded`. |
| Ordre | Paire 1 : idle puis loaded ; paire 2 : loaded puis idle ; paire 3 : idle puis loaded. |
| Mesure | Dix établissements TCP par série vers `10.203.0.6:46001`, timeout de 250ms, pause de 250ms. |
| Pause entre phases | Au moins 500ms, sans charge propre encore active. |
| Chaque charge | Client → `10.203.0.6:46002`, 8 Mio, plafond moyen applicatif de 1 Mio/s, émission bornée à 12s et réception à 15s. |
| Volume total | 24 Mio synthétiques, en trois transferts complets. |
| Cible de latence | Une nouvelle écoute par phase, limitée à 100 acceptations et 15s, arrêtée volontairement après la mesure. |
| Limites du pilote | Disponibilité : 5s par outil ; commande de mesure/comparaison : 8s ; contrôle applicatif global : 90s. |

L'alternance réduit la dépendance à un ordre unique ; trois paires ne suffisent pas à éliminer les biais ni à estimer une distribution de performances fiable. Chaque paire reste distincte : les percentiles ne sont pas moyennés entre séries. Avec dix réussites, p95 et p99 sont le maximum observé.

`idle` signifie ici l'absence du transfert synthétique propre au scénario. Le noyau et le CPU restent partagés avec l'hôte ; son repos physique n'est pas établi. `loaded` ne signifie pas saturation WAN.

## Déroulement et critères

Le script shell crée les espaces neufs, effectue les contrôles ICMP, puis lance `scripts/lab-series.py`. Ce pilote de développement utilise Python 3 et sa bibliothèque standard pour gérer les processus existants. Il reste un outil de laboratoire ; les choix Go pour les applications de bureau et Kotlin pour Android restent ceux du projet.

Pour chaque phase, le pilote attend l'écoute de la cible de latence. En phase loaded, il attend aussi le récepteur de charge, puis l'annonce `STARTED` émise après la première écriture du générateur. Il lance ensuite la commande de mesure de l'agent. L'écoute de latence est arrêtée volontairement après la série ; son message d'annulation attendu ne constitue pas une erreur de mesure. Le transfert et sa réception doivent terminer normalement avant la prochaine phase.

Le rapport de charge conserve `first_write_at` et `last_write_at`. La fenêtre entière `started_at` → `finished_at` de la série loaded doit être comprise entre ces deux écritures. Les horodatages UTC sont comparés à la nanoseconde, sans déduire l'activité depuis le seul PID ou le début du processus. Une fenêtre incohérente ou un recouvrement incomplet arrête l'essai. Ce contrôle établit un recouvrement avec la fenêtre d'écritures applicatives ; il ne prouve pas une émission continue de paquets sur le lien, car le noyau peut tamponner les données.

La charge doit aussi respecter le volume exact et le plafond moyen du protocole précédent. Chaque paire est validée par `coopace latency compare` à partir des rapports bruts, dans des fichiers temporaires privés. Le lecteur existant contrôle le schéma complet, les paramètres, échantillons et statistiques avant d'afficher la comparaison.

**Les échecs de connexion sont conservés.** Le code `1` de `coopace latency` est admis uniquement pour un rapport complet et valide avec zéro réussite ; il ne fait pas disparaître la série. Une erreur de configuration, de processus ou un JSON incomplet arrête l'essai. Le code `0` final indique des séries complètes et validées, pas une absence d'échecs ni une amélioration.

## Reproduire l'essai natif

Depuis le dépôt, compiler les trois binaires avec le compte habituel pour incorporer les nouveaux marqueurs du générateur :

```sh
mkdir -p .local/bin .local/experiments
sh scripts/go.sh build -o .local/bin/coopace ./apps/agent/cmd/coopace
sh scripts/go.sh build -o .local/bin/coopace-lab-tcp ./scripts/lab-tcp
sh scripts/go.sh build -o .local/bin/coopace-lab-load ./scripts/lab-load
sh scripts/lab-network.sh plan
```

Choisir des fichiers neufs, puis lancer depuis le terminal Linux :

```sh
sudo sh scripts/lab-network.sh run-series > .local/experiments/series-report.json 2> .local/experiments/series.log
printf '%s\n' "$?" | tee .local/experiments/series.exit
```

Prévoir environ quarante secondes en fonctionnement normal ; il ne s'agit pas d'une borne globale dure. Les commandes de configuration et opérations système restent soumises aux limites décrites dans [VIRTUAL_LAB.md](VIRTUAL_LAB.md). Les délais applicatifs arrêtent les attentes du pilote, sans fournir de superviseur indépendant.

## Format et conservation

La sortie standard contient un seul objet JSON local v1, de type `synthetic_latency_series`, après arrêt des processus et nettoyage des espaces. Les erreurs et étapes vont sur stderr. Une erreur, une interruption gérée ou un nettoyage refusé ne publie pas de rapport de réussite.

| Champ | Contenu |
| --- | --- |
| `pairs` | Trois objets avec numéro, ordre réel et phases `idle` / `loaded`. |
| `pairs[].idle.latency`, `pairs[].loaded.latency` | Rapports locaux `tcp_connect` v1 complets, avec leurs échecs éventuels. |
| `measurement_exit_code` dans chaque phase | Code réellement observé de la mesure : 0 ou 1 conforme aux réussites. |
| `load` dans chaque phase | Nul pour idle ; rapport `synthetic_tcp_send` pour loaded. |
| `pairs[].comparison` | Texte de comparaison stricte et descriptive produit par la CLI existante. |
| `overlap_check` | `application_write_window`, critère imposé avant publication. |
| `total_synthetic_bytes` | 25 165 824 octets. |
| `saturation`, `traffic_coverage` | `unverified` et `synthetic_ipv4_only`. |

Les rapports de charge anciens restent conservés tels quels ; leurs horodatages d'écriture absents ne sont pas inventés. Le nouveau mode exige les nouveaux champs et l'annonce de démarrage. Le JSON groupé n'est pas une entrée directe de `latency compare` ; ses rapports imbriqués en sont les exports individuels. Les comparaisons par paire sont déjà incluses.

Conserver le commit, les empreintes des trois binaires et des deux scripts, le rapport complet, le journal et le code de sortie, y compris pour un essai échoué. Aucun résultat WAN, IPv6, DNS, UDP/QUIC, équité ou ressources n'est déduit de ces séries. Les seuils de performance et les références avant/après politique restent à définir avant une telle expérience.

## Arrêt, nettoyage et tests

Le pilote possède chaque processus qu'il démarre et l'arrête puis l'attend avant sa sortie. Les gestionnaires HUP/INT/TERM enregistrent une demande ; le pilote la traite après avoir enregistré tout nouveau processus. Le shell suit le PID du pilote et l'arrête avant de supprimer ses seuls espaces. Les marqueurs et fichiers de comparaison restent dans un sous-dossier temporaire privé créé exclusivement par le pilote ; il le supprime à la sortie normale ou après une erreur gérée.

Un SIGKILL ou une panne peut laisser des noms et des fichiers. Les outils réseau ont leurs propres délais, mais cela ne garantit pas la suppression des espaces ni une restauration de production. Un sous-dossier `series-*` peut subsister sous la réservation exacte du journal et empêcher son retrait ; inspecter uniquement ce dossier et ses ressources avant une récupération ciblée. Aucune suppression globale de fichiers, d'espaces ou de processus n'est effectuée.

Les tests Python vérifient l'ordre, les paramètres, les rapports invalides, le recouvrement à la nanoseconde, les séries sans réussite, la borne des sorties et le nettoyage après interruption. Des processus locaux de test sont effectivement démarrés et arrêtés, sans accès réseau. Les tests Go contrôlent aussi l'annonce de première écriture et les nouveaux horodatages avec des connexions en mémoire. Ces contrôles ne constituent pas l'essai natif du scénario complet.

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
sh scripts/go.sh test -count=1 -v ./scripts/lab-load
```

La [feuille de route](ROADMAP.md) garde l'étape 4.2 ouverte. Le premier essai natif et son analyse descriptive sont [consignés](VALIDATION_VIRTUAL_SERIES_2026-10-29.md). Le [protocole de goulot contrôlé](VIRTUAL_BOTTLENECK.md) définit maintenant la prochaine référence et ses critères ; son implémentation, sa collecte et le nettoyage indépendant restent à réaliser avant de piloter une politique de files.
