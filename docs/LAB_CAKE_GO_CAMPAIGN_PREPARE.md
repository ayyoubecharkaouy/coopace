# Préparation figée de la campagne Go

## État et portée

`scripts/prepare-cake-go-campaign.py` prépare un dossier distinct pour le [contrat de campagne](LAB_CAKE_GO_CAMPAIGN.md) et sa [commande](LAB_CAKE_GO_CAMPAIGN_CLI.md). Il réutilise la compilation et les protections du préparateur Go/trafic, avec un profil `lab_cake_go_campaign_preparation`.

**La préparation inclut maintenant le [lanceur natif](LAB_CAKE_GO_CAMPAIGN_RUN.md) et son wrapper de relecture.** Elle crée `run.sh` et `review-native.py`, sans exécuter les contrôles ni créer leurs résultats ou certificat. Les profils historiques Go/trafic et IPv4 gardent leur comportement.

## Préparation sans privilèges

Depuis un arbre Git propre, avec le compte habituel :

```sh
python3 -I -B scripts/prepare-cake-go-campaign.py
```

Le dossier par défaut est `.local/experiments/go-campaign-native-validation-REVISION/`. L’option `--artifacts CHEMIN_NEUF` permet un autre emplacement dont le parent existe. Un dossier existant est refusé ; une préparation échouée reste conservée et demande un autre dossier pour un nouvel essai.

Linux amd64 et Python avec `os.setns` sont requis. Aucune création de namespace, modification de file ou émission de trafic n’a lieu. Les commandes exécutées servent à Git, à la compilation, aux aides/plans, aux versions locales et aux empreintes ; le script généré appellera sudo uniquement lors du lancement des deux contrôles, pas pendant la préparation.

## Entrées figées

| Élément | Contrôle |
| --- | --- |
| Révision | Arbre propre avant/après, commit capturé et revérifié avant publication du manifeste |
| Quatre binaires | Worker CAKE, agent, cible TCP, transfert ; SDK de `.go-version`, `-trimpath`, `-buildvcs=true` |
| Provenance Go | Commit attendu, `vcs.modified=false`, Linux amd64 et version exacte du SDK |
| Outils | Chemins canoniques et SHA-256 de worker/agent/cible/transfert/Python/ip/tc/sysctl/ping |
| Producteurs | `tc -V` conforme au profil iproute2-6.1.0 ; `ping -V` annonçant iputils, stdout/stderr conservés |
| Sources | Fichiers suivis Git, scripts du superviseur, préparation commune et entrée du préparateur |
| Contexte | Noyau, version de Python, exécutable Go, plan, protocole, aides et métadonnées de compilation |

Les sources du superviseur et les outils sont revérifiés avant publication. `inputs.sha256` protège les fichiers figés, les sources et les exécutables à leurs chemins d’origine. `prepared.json` conserve l’inventaire et est protégé par `prepared.sha256`. Les fichiers sont créés exclusivement et synchronisés. Les espaces dans les chemins sont pris en charge.

Le fichier `protocol.md` copie cette procédure ; le contrat de campagne et les autres documents suivis restent également couverts par les entrées Git et leurs empreintes.

## État du dossier

Le manifeste garde `state: not_run` et `native_execution: not_run`. Il déclare les deux étapes `native_steps: [run, check-crash]` et `native_launcher_available: true`. Ces deux noms réservent des destinations séparées pour les résultats futurs ; la préparation ne les remplit pas et ne les crée pas.

Ce dossier ne constitue pas une validation native. Le lanceur et la relecture sont livrés ; un nouveau dossier est préparé depuis leur commit propre. Les dossiers déjà produits restent inchangés : leurs manifestes ne doivent pas être réécrits pour y ajouter un nouveau lanceur.

## Vérification et suite

Les tests simulent la compilation et les sorties d’outils, mais écrivent de vrais fichiers et revérifient les empreintes avec `sha256sum`. Ils couvrent le manifeste de campagne, les lanceurs et wrappers générés, l’absence de résultats natifs pendant la préparation, la provenance, ping, les changements de révision/outils, le refus d’écrasement et la compatibilité des profils historiques, dont la syntaxe des lanceurs et wrappers générés.

Validation locale du 3 novembre 2026 : 25 tests ciblés passent en 5,398 s, dont cinq nouveaux tests de préparation, sept tests des préparateurs historiques, huit tests de l’entrée de campagne et cinq tests du verdict global. La compilation est simulée dans ces tests ; la suite complète n’a pas été relancée pour cet ajout. Aucun essai réseau natif n’est produit.

Prochaine étape : [exécution du nouveau dossier](LAB_CAKE_GO_CAMPAIGN_RUN.md), puis revue des preuves et compte rendu natif.

La [relecture indépendante des phases](LAB_CAKE_GO_CAMPAIGN_PHASE_REVIEW.md) est maintenant livrée comme première sous-étape. Elle ne publie aucun certificat. Le [raccordement Go/IPv4 et au dossier figé](LAB_CAKE_GO_CAMPAIGN_GLOBAL_REVIEW.md) est maintenant livré ; le [lanceur natif](LAB_CAKE_GO_CAMPAIGN_RUN.md) est maintenant livré.
