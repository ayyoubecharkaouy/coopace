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

Le mode `run` exige les privilèges documentés et le binaire passerelle construit au préalable avec le compte habituel. Il est réservé au laboratoire et n'est pas lancé automatiquement. Voir [VIRTUAL_LAB.md](../docs/VIRTUAL_LAB.md) pour le scénario, les limites et le premier résultat natif ICMP/TCP consigné.

`run-tcp` utilise les mêmes privilèges et requiert plutôt les binaires `coopace` et `coopace-lab-tcp`. Le sous-dossier [lab-tcp](lab-tcp/README.md) contient cette cible de développement en Go, avec durée et nombre de connexions limités. Il ne s'agit pas d'un serveur distribué avec le produit ni d'un générateur de charge.

`run-load` requiert plutôt le binaire du sous-dossier [lab-load](lab-load/README.md), qui contient l'émetteur et le récepteur de données synthétiques. Les paramètres et le protocole de son premier essai natif sont dans [VIRTUAL_LOAD.md](../docs/VIRTUAL_LOAD.md).

`run-series` exige Python 3 et les trois binaires `coopace`, `coopace-lab-tcp` et `coopace-lab-load`. Le shell appelle `lab-series.py` avec ses propres noms d'espaces et sa réservation privée ; ce pilote de développement possède ses processus et utilise la CLI existante. Voir [VIRTUAL_SERIES.md](../docs/VIRTUAL_SERIES.md) pour les paramètres et le premier essai natif consigné.

Le superviseur se lance avec `python3 -I scripts/lab-guard.py plan`. Ses contrôles sans file exigent les privilèges documentés dans [LAB_GUARD.md](../docs/LAB_GUARD.md), sans binaire Go ; leurs [premiers essais natifs](../docs/VALIDATION_LAB_GUARD_2026-10-29.md) sont validés. Les contrôles avec file exigent aussi `tc` et utilisent le module voisin `lab_queue.py`, chargé par chemin explicite. Leur périmètre est décrit dans [LAB_QUEUE.md](../docs/LAB_QUEUE.md) et leurs [premiers essais natifs](../docs/VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés, avec revérification des modes sans file. Aucun de ces modes ne modifie les commandes de `lab-network.sh`.

L'[instrumentation de réception et de file](../docs/LAB_INSTRUMENTATION.md) ajoute `coopace-lab-load receive --json` et les contrôles TBF de statistiques. Les tests en mémoire et simulés sont disponibles ; leur validation native reste à consigner. Aucune campagne avec goulot actif n'est encore lancée.

Les tests Python de `tests/` utilisent des outils simulés et des fichiers temporaires. Ils n'installent pas de SDK réel et ne créent aucun réseau :

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
```
