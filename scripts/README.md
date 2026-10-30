# Outils de développement

Exécuter les commandes ci-dessous depuis la racine du dépôt ; les scripts `.sh` utilisent `sh`.

| Script | Rôle |
| --- | --- |
| `setup-go.sh` | Installer le SDK Go vérifié dans le projet, sous Linux x86_64. |
| `go.sh` | Utiliser le SDK et les caches locaux pour développer et compiler. |
| `lab-network.sh plan` | Prévisualiser le laboratoire virtuel, sans privilèges ni opération réseau. |
| `lab-network.sh run` | Créer, sonder et nettoyer explicitement des espaces réseau neufs sur un hôte Linux autorisé. |
| `lab-network.sh run-tcp` | Mesurer cinq établissements TCP vers le serveur neuf, puis arrêter le serveur et nettoyer le laboratoire. |
| `lab-network.sh run-load` | Transférer 8 Mio synthétiques avec un plafond moyen de 1 Mio/s, puis attendre la réception complète et nettoyer. |
| `lab-network.sh run-series` | Recueillir trois paires de séries sans/avec le flux, vérifier le recouvrement et comparer les rapports complets. |
| `lab-guard.py plan` | Prévisualiser le contrôle du nettoyage indépendant, sans création de ressource. |
| `lab-guard.py check` / `check-crash` | Contrôler la récupération des processus et espaces neufs après fin normale ou mort forcée du pilote. |
| `lab-guard.py plan-queue` | Prévisualiser la création et la relecture d'une file TBF dans le laboratoire. |
| `lab-guard.py check-queue` / `check-queue-crash` | Vérifier TBF sur un lien désactivé, puis nettoyer après fin normale ou mort forcée du pilote. |
| `lab-guard.py check-queue-stats` / `check-queue-stats-crash` | Ajouter deux lectures de statistiques TBF, avec compteurs cumulés et jauges distincts. |
| `lab-active.py plan` | Prévisualiser le contrôle fonctionnel du chemin actif sous TBF, sans création de ressource. |
| `lab-active.py check` / `check-crash` | Un transfert et dix sondes sous TBF avec collecte périodique, ou mort forcée du pilote avec trois outils récupérés. |
| `lab-campaign.py plan` | Prévisualiser les trois paires sous la même TBF et leurs critères, sans création de ressource. |
| `lab-campaign.py run` / `check-crash` | Collecter six phases et qualifier la congestion, ou vérifier la récupération après mort forcée ; preuves conservées dans `--artifacts`. |
| `lab-cake.py plan` | Prévisualiser le contrôle CAKE sur lien désactivé, sans création de ressource. |
| `lab-cake.py check` / `check-crash` | Ajouter et relire CAKE/statistiques sur lien DOWN, puis récupérer pilote/descendant et supprimer les espaces possédés. |
| `lab-cake-active.py plan` | Prévisualiser le contrôle fonctionnel CAKE avec transfert et sondes, sans création de ressource. |
| `lab-cake-active.py check` / `check-crash` | Un transfert sous CAKE ou mort forcée du pilote, avec journal requis via `--evidence FICHIER_NEUF`. |

Le mode `run` exige les privilèges documentés et le binaire passerelle construit au préalable avec le compte habituel. Il est réservé au laboratoire et n'est pas lancé automatiquement. Voir [VIRTUAL_LAB.md](../docs/VIRTUAL_LAB.md) pour le scénario, les limites et le premier résultat natif ICMP/TCP consigné.

`run-tcp` utilise les mêmes privilèges et requiert plutôt les binaires `coopace` et `coopace-lab-tcp`. Le sous-dossier [lab-tcp](lab-tcp/README.md) contient cette cible de développement en Go, avec durée et nombre de connexions limités. Il ne s'agit pas d'un serveur distribué avec le produit ni d'un générateur de charge.

`run-load` requiert plutôt le binaire du sous-dossier [lab-load](lab-load/README.md), qui contient l'émetteur et le récepteur de données synthétiques. Les paramètres et le protocole de son premier essai natif sont dans [VIRTUAL_LOAD.md](../docs/VIRTUAL_LOAD.md).

`run-series` exige Python 3 et les trois binaires `coopace`, `coopace-lab-tcp` et `coopace-lab-load`. Le shell appelle `lab-series.py` avec ses propres noms d'espaces et sa réservation privée ; ce pilote de développement possède ses processus et utilise la CLI existante. Voir [VIRTUAL_SERIES.md](../docs/VIRTUAL_SERIES.md) pour les paramètres et le premier essai natif consigné.

Le superviseur se lance avec `python3 -I scripts/lab-guard.py plan`. Ses contrôles sans file exigent les privilèges documentés dans [LAB_GUARD.md](../docs/LAB_GUARD.md), sans binaire Go ; leurs [premiers essais natifs](../docs/VALIDATION_LAB_GUARD_2026-10-29.md) sont validés. Les contrôles avec file exigent aussi `tc` et utilisent le module voisin `lab_queue.py`, chargé par chemin explicite. Leur périmètre est décrit dans [LAB_QUEUE.md](../docs/LAB_QUEUE.md) et leurs [premiers essais natifs](../docs/VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés, avec revérification des modes sans file. Aucun de ces modes ne modifie les commandes de `lab-network.sh`.

L'[instrumentation de réception et de file](../docs/LAB_INSTRUMENTATION.md) ajoute `coopace-lab-load receive --json` et les contrôles TBF de statistiques. Les tests en mémoire et simulés sont disponibles ; les [premiers contrôles natifs](../docs/VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) sont validés pour la réception locale et les statistiques sur liens désactivés. La [première campagne avec goulot actif](../docs/VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) est maintenant validée.

Les tests Python de `tests/` utilisent des outils simulés et des fichiers temporaires. Ils n'installent pas de SDK réel et ne créent aucun réseau :

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

Le [contrôle fonctionnel actif](../docs/LAB_ACTIVE.md) se lance séparément avec `python3 -I -B scripts/lab-active.py`. Il réutilise le superviseur, `lab_queue.py` et les outils de processus de `lab-series.py`, chargés par chemin explicite. Il exige aussi `sysctl` et les trois binaires Go déjà cités. Il est testé avec des commandes réseau simulées et de vrais processus ; sa [première validation native](../docs/VALIDATION_LAB_ACTIVE_2026-10-30.md) confirme transfert, sondes, collecte et nettoyage normal ou après mort forcée. Il ne remplace pas la campagne de trois paires du protocole de goulot.

La [campagne TBF](../docs/LAB_CAMPAIGN.md) utilise `python3 -I -B scripts/lab-campaign.py plan`, `run --artifacts DOSSIER` et `check-crash --artifacts DOSSIER`. Son module `lab_campaign.py` coordonne six phases sous le même superviseur et conserve les preuves intermédiaires. Elle requiert aussi `ping` et `CAP_NET_RAW` pour les contrôles de passage. Les tests avec commandes réseau simulées passent ; sa [première validation native](../docs/VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) confirme six phases, trois réceptions, congestion observée selon v1 et nettoyage après mort forcée.

Le [contrôle CAKE DOWN](../docs/LAB_CAKE.md) utilise le module séparé `lab_cake.py`, le superviseur existant et une préparation commune du veth. Il exige le profil JSON identifié iproute2-6.1.0 ; options omises et statistiques indisponibles sont distinguées. Aucun binaire Go ni trafic de mesure n'est nécessaire. Les tests avec commandes réseau simulées et vrais processus passent ; sa [première validation native](../docs/VALIDATION_LAB_CAKE_2026-10-30.md) confirme configuration, statistiques et nettoyage dans les deux modes.

Le [contrôle fonctionnel CAKE actif](../docs/LAB_CAKE_ACTIVE.md) utilise les trois binaires Go déjà employés par TBF, le même pilote de transfert et le superviseur. `lab_cake_active.py` conserve le validateur CAKE et les preuves séparément ; la topologie est activée par une fonction commune de `lab_active.py`. Les tests avec commandes réseau simulées passent ; sa [première validation native](../docs/VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md) confirme transfert complet, dix connexions, relevés conservés et récupération des trois outils après mort forcée.
