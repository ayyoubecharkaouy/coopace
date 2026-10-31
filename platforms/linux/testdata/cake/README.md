# Relevés de référence CAKE iproute2-6.1.0

Ces deux fixtures sont extraites de relevés natifs déjà validés le 30 octobre 2026. Elles conservent les objets `qdiscs` du rapport, remis en forme en JSON avec indentation ; ce ne sont pas les octets originaux de stdout de `tc`. Aucun nom d'espace, chemin privé, adresse, contenu applicatif ou identifiant d'appareil n'y est ajouté.

| Fixture | Origine locale et sélection | SHA-256 du rapport source |
| --- | --- | --- |
| `down.json` | `cake-validation-326e9f7/cake-check.json`, `queue.after_add.qdiscs`. | `d29e537d3eb301b3644bf38d09cc655ad59987c5430140adcd473cb22ff2319d` |
| `active.json` | `comparison-validation-c0edb80/comparison/02-block-1-cake/campaign.json`, première phase loaded, premier échantillon `running` avec progression d'octets. | `cc5ef399f7e84ca428d3b08e7635932529fffdde360970e427d8eb842c842a01` |

Les sources et comptes rendus sont décrits dans la [validation DOWN](../../../../docs/VALIDATION_LAB_CAKE_2026-10-30.md) et la [comparaison native](../../../../docs/VALIDATION_CAKE_COMPARISON_2026-10-30.md). Les dossiers d'expérience complets restent locaux et exclus de Git.

Les tests Go lisent ces fichiers sans outil réseau ni privilège. Les variantes de refus, champs indisponibles, compteurs proches de la borne uint64 et types incorrects sont créées en mémoire ; elles ne sont pas présentées comme des mesures natives. La lecture de ces fixtures ne valide pas l'application de CAKE par un processus Go.
