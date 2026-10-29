# Premier transfert synthétique natif — 29 octobre 2026

## Résultat observé

L'utilisateur a exécuté `sudo sh scripts/lab-network.sh run-load` depuis son terminal Linux. Le rapport et le journal confirment 8 388 608 octets synthétiques envoyés et reçus, avec une émission d'environ huit secondes et un nettoyage normal réussi. Le code de sortie exact est à récupérer : il n'a pas été enregistré dans la commande initialement montrée. Il n'est pas remplacé par une valeur supposée dans le bilan local.

Les contrôles fonctionnels sont conformes aux paramètres du [protocole fixé avant l'essai](VIRTUAL_LOAD.md). Ce résultat ne valide pas encore une série de latence au repos/sous charge ni une saturation du réseau.

## Provenance et fichiers

- Commit de préparation et de compilation : `ba638e073803fd99959803952e1dad86206d5f12`.
- Programme : Go `go1.27.3`, Linux `amd64`.
- Dossier local : `.local/experiments/load-validation-ba638e0/`.
- Émission : `2026-10-29T18:32:25.419625683Z` à `2026-10-29T18:32:33.419942882Z`.
- Empreintes du binaire et du script recontrôlées après l'essai : conformes à `prepared.json`.

La préparation et le protocole sont conservés tels qu'ils étaient avant l'essai. `validation.json` consigne les observations ultérieures et les empreintes des pièces. Les données brutes restent locales et exclues de Git.

| Pièce | SHA-256 |
| --- | --- |
| `report.json` | `b73782856c528ef1bd056e1b7fb10ce4a95778b9dfd34a269203a3df4ed4b209` |
| `run.log` | `960dab8670e58aedb03613785286c9971261c4d485980b17648960d0a7681bf9` |

## Contrôles

| Élément | Observation |
| --- | --- |
| Cible et direction | Client vers `10.203.0.6:46002`, un flux TCP synthétique. |
| Volume demandé / écrit | 8 388 608 / 8 388 608 octets. |
| Réception | Le journal confirme exactement 8 388 608 octets reçus. |
| Plafond moyen demandé | 1 048 576 octets/s. |
| Moyenne applicative observée | 1048534.425872 octets/s, soit 0.999960352 Mio/s. |
| Durée d'émission | 8000.317198 ms, au moins 8s et inférieure au délai applicatif de 12s. |
| ICMP sans forwarding | Aucune réponse à la sonde. |
| ICMP après activation | Trois réponses sur trois. |
| Nettoyage normal | Suppression réussie dans le journal ; les trois noms `cp-h6IIMZWj-c/g/s` et `/tmp/coopace-lab.h6IIMZWj` ne sont plus visibles depuis le développement. |
| Code de sortie exact | Non enregistré dans la commande initiale ; demande de récupération en cours. |

La moyenne a été recalculée depuis le volume et la durée. Les horodatages sont cohérents avec cette durée. Les blocs sont plafonnés à 16 Kio ; la cadence moyenne ne constitue pas un plafond instantané sur le lien. Les délais de réception de 15s, les interruptions et les volumes invalides n'ont pas été injectés dans cet essai natif ; leurs tests restent en mémoire ou simulés.

## Suite

Compléter le code de sortie s'il est encore disponible, puis intégrer la mesure de latence pendant ce flux et les répétitions comparables sans et avec trafic synthétique. Conserver les horaires pour vérifier le recouvrement réel. L'étape 4.2 reste ouverte ; les performances WAN, l'équité, les ressources et la restauration indépendante ne sont pas validées par cet essai.
