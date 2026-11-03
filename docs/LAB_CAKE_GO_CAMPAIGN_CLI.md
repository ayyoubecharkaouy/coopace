# Commande de campagne CAKE après Go

## État et portée

`scripts/lab-cake-go-campaign.py` expose les modes `plan`, `run` et `check-crash`. Elle appelle le [rapport global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) et conserve les paramètres du [contrat v1](LAB_CAKE_GO_CAMPAIGN.md). L’entrée est incluse dans les empreintes de sources vérifiées pendant l’exécution.

La commande est implémentée et testée. La préparation figée et la relecture indépendante restent à développer ; aucune campagne réseau native après Go n’a été exécutée.

## Lecture sans privilèges

Depuis la racine du dépôt :

```sh
python3 -B scripts/lab-cake-go-campaign.py plan
python3 -B scripts/lab-cake-go-campaign.py --help
```

Sans mode, la commande affiche également le plan. Ces lectures ne résolvent pas les chemins fournis, ne recherchent pas les outils système et ne passent pas le contrôle de privilèges. Elles ne créent aucun dossier, processus de laboratoire, namespace ou trafic.

## Exécution explicite

Les trois options suivantes sont obligatoires pour `run` et `check-crash` :

| Option | Entrée attendue |
| --- | --- |
| `--worker` | Chemin du binaire Go `coopace-cake-worker` exécutable |
| `--binaries` | Dossier contenant `coopace`, `coopace-lab-tcp` et `coopace-lab-load` |
| `--artifacts` | Dossier existant, neuf et vide, réservé à ce seul essai |

Les chemins sont rendus canoniques. Une entrée absente, un worker non exécutable ou un dossier de preuves occupé est refusé avant le contrôle des privilèges. Les vérifications ELF et les empreintes détaillées restent celles de l’inventaire, avant création des ressources.

L’exécution exige Linux amd64, Python avec `os.setns`, les privilèges du [garde](LAB_GUARD.md) et les outils `ip`, `tc`, `sysctl`, `ping`. Le dossier de preuves n’est ni créé ni vidé par la commande. Chaque mode et chaque nouvel essai utilisent leur propre dossier.

Formes des commandes, avec chemins à fournir par la future préparation figée :

```sh
python3 -B scripts/lab-cake-go-campaign.py run \
  --worker /chemin/essai/bin/coopace-cake-worker \
  --binaries /chemin/essai/bin \
  --artifacts /chemin/essai/run

python3 -B scripts/lab-cake-go-campaign.py check-crash \
  --worker /chemin/autre-essai/bin/coopace-cake-worker \
  --binaries /chemin/autre-essai/bin \
  --artifacts /chemin/autre-essai/check-crash
```

Les privilèges de laboratoire s’appliquent seulement aux modes d’exécution. Aucune interface physique ni accès Internet n’est utilisé. `run` effectue les six phases et les trois transferts attendus. `check-crash` vérifie la récupération au premier `ready` chargé après la phase idle ; il ne qualifie pas les mesures.

## Sorties et codes

La sortie standard contient un rapport JSON uniquement après retour conforme du superviseur : `kind: lab_cake_go_campaign`, `state: complete`, et `technical_valid: true` en mode normal ou `null` pour un contrôle de panne réussi. Une charge insuffisante ou des connexions dégradées restent compatibles avec le code 0 si les preuves et mesures sont techniquement exploitables.

Une erreur d’arguments donne le code 2. Un refus de contexte, une erreur opérationnelle ou des mesures inexploitables donnent le code 1 et un diagnostic sur stderr. Une interruption conserve le code du garde, par exemple 143 pour SIGTERM. Les rapports et preuves partielles déjà écrits restent dans le dossier d’essai ; la commande n’affiche pas un rapport de succès sur stdout après une erreur.

Le code 0 ne remplace ni la relecture indépendante ni la validation native, et ne prouve aucun bénéfice pour le foyer.

## Vérification et suite

Les huit tests de l’entrée couvrent le plan par défaut, l’aide, les arguments, le fonctionnement sans outils réseau, les chemins, le refus d’écrasement, la sélection des modes, le raccordement au modèle, les codes d’erreur/interruption et l’inclusion de l’entrée dans les empreintes. Les appels d’exécution de l’entrée sont simulés ; les tests existants du rapport global utilisent de vrais processus avec noyau réseau simulé.

Validation locale du 3 novembre 2026 : 47 tests ciblés passent en 93,895 s, dont les huit nouveaux tests de l’entrée, neuf du rapport global, neuf des calculs, quatorze du dialogue de campagne, six du protocole à flux unique et un contrôle de régression de l’entrée IPv4 historique. La suite complète n’a pas été relancée pour cet ajout. Le plan a également été exécuté directement, sans privilèges et sans action réseau.

La prochaine sous-étape est la préparation figée, suivie de la relecture indépendante avant les essais natifs dans des dossiers neufs.
