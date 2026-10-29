# Outils de développement

Exécuter ces scripts depuis la racine du dépôt avec `sh`.

| Script | Rôle |
| --- | --- |
| `setup-go.sh` | Installer le SDK Go vérifié dans le projet, sous Linux x86_64. |
| `go.sh` | Utiliser le SDK et les caches locaux pour développer et compiler. |
| `lab-network.sh plan` | Prévisualiser le laboratoire virtuel, sans privilèges ni opération réseau. |
| `lab-network.sh run` | Créer, sonder et nettoyer explicitement des espaces réseau neufs sur un hôte Linux autorisé. |
| `lab-network.sh run-tcp` | Mesurer cinq établissements TCP vers le serveur neuf, puis arrêter le serveur et nettoyer le laboratoire. |

Le mode `run` exige les privilèges documentés et le binaire passerelle construit au préalable avec le compte habituel. Il est réservé au laboratoire et n'est pas lancé automatiquement. Voir [VIRTUAL_LAB.md](../docs/VIRTUAL_LAB.md) pour le scénario, les limites et la validation native encore à effectuer.

`run-tcp` utilise les mêmes privilèges et requiert plutôt les binaires `coopace` et `coopace-lab-tcp`. Le sous-dossier [lab-tcp](lab-tcp/README.md) contient cette cible de développement en Go, avec durée et nombre de connexions limités. Il ne s'agit pas d'un serveur distribué avec le produit ni d'un générateur de charge.

Les tests Python de `tests/` utilisent des outils simulés et des fichiers temporaires. Ils n'installent pas de SDK réel et ne créent aucun réseau :

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py' -v
```
