# Comparaison supervisée TBF/CAKE — mise en œuvre v1

## État et portée

`scripts/lab-compare.py`, `lab_comparison_run.py` et `lab_comparison.py` implémentent les six campagnes et l'agrégation des neuf comparaisons du [protocole v1](CAKE_COMPARISON.md). **La première comparaison native est validée** : six campagnes, 360 connexions réussies, 18 réceptions complètes et décision `static_cake_improvement_v1` confirmée par relecture et calculs indépendants. Voir le [compte rendu](VALIDATION_CAKE_COMPARISON_2026-10-30.md). Les campagnes [TBF](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) et [CAKE](VALIDATION_LAB_CAKE_CAMPAIGN_2026-10-30.md) sont déjà validées séparément, sans constituer les bras de cette nouvelle expérience.

L'expérience compare deux configurations statiques existantes. Elle ne pilote pas les paramètres avec Coopace, n'utilise pas le ML et ne mesure pas le réseau du foyer. Les paramètres, ordres et seuils comparatifs v1 restent inchangés.

## Orchestration et nettoyage

Les blocs suivent TBF/CAKE, CAKE/TBF, TBF/CAKE. Les six campagnes utilisent chacune trois espaces neufs et les phases idle/loaded, loaded/idle, idle/loaded. Le volume attendu est 36 phases, 360 tentatives TCP et 18 transferts de 8 Mio, soit 144 Mio utiles ; les contrôles de panne préalables restent séparés.

Le lanceur appelle directement les moteurs supervisés existants. Chaque campagne garde son pilote de 150s, son superviseur de 180s et son budget de nettoyage de 10s. Il n'y a pas de destruction du superviseur pour imposer une échéance globale. Les outils Go héritent du fichier stderr propre à leur campagne. Le lanceur attend au moins 2s après le retour confirmant le nettoyage avant la campagne suivante ; cette pause inclut le temps de validation hors ligne déjà écoulé.

Les identités des espaces et réservations doivent rester distinctes. Avant et après chaque campagne, le lanceur vérifie l'environnement, les chemins et empreintes des outils, des trois binaires et des sources Python exécutées. Le noyau et la version Python doivent aussi rester identiques. Les protocoles, la provenance Go et les sources sont figés séparément dans le dossier d'expérience avant lancement.

Une erreur opérationnelle, une collecte non exploitable, une modification d'entrée ou une interruption arrête les campagnes suivantes. Le superviseur courant reste responsable de ses ressources. Entre campagnes, les signaux sont mémorisés par le lanceur, qui ne crée pas la topologie suivante. Les preuves déjà produites sont conservées. Une collecte valide mais une référence non qualifiée ou un garde-fou défavorable ne provoquent aucune reprise ni arrêt sélectif.

## Fichiers et relecture

`run --artifacts DOSSIER` exige un dossier existant et vide. Toutes les créations sont exclusives, sans écrasement des fichiers. Les six sous-dossiers sont `01-block-1-tbf`, `02-block-1-cake`, `03-block-2-cake`, `04-block-2-tbf`, `05-block-3-tbf`, `06-block-3-cake`.

| Pièce | Contenu |
| --- | --- |
| `environment.json` | Environnement et empreintes vérifiés pendant les six campagnes. |
| `progress.jsonl` | Ordre, débuts/fins de campagnes et décision finale ; écrit et vidé après chaque événement. |
| `session.json` | État final complet ou échoué, campagnes déjà tentées, chronologie monotone, empreintes des rapports et erreur éventuelle. |
| Chaque sous-dossier | `campaign.json`, `campaign.log`, `campaign.exit`, journal supervisé et six rapports TCP de phases ; preuves partielles conservées si échec. |
| `comparison.json` | Neuf comparaisons par bloc/paire, trois décisions de blocs, garde-fous détaillés et décision globale. Créé seulement pour six campagnes exploitables. |

L'agrégateur revalide configurations et statistiques brutes/normalisées, contrôles de passage, chronologie, vidage, différences de compteurs, réception complète, recouvrement et stabilisation. Il rapproche les rapports de phases et les journaux, puis reproduit les 18 comparaisons de la vraie CLI `coopace latency compare`. Les décisions TBF et CAKE sont recalculées. Un drapeau de réussite dans le rapport n'est pas suffisant.

`analyze --artifacts DOSSIER` relit ces mêmes preuves sans opération réseau ni privilège. Il vérifie les empreintes de session, l'ordre, les pauses, les binaires de collecte, les six campagnes et reproduit le bilan. Il affiche le JSON sans réécrire les fichiers. Il refuse une session incomplète, une pièce modifiée ou un bilan non reproductible.

## Décisions et disponibilité

Pour les neuf comparaisons, les calculs utilisent des décimaux aux frontières des seuils. Les différences de p50 restent signées, les valeurs indisponibles restent `null` et aucune moyenne de percentiles n'est utilisée. Chaque bloc exige au moins deux paires satisfaisant les trois conditions de latence v1 ; une paire indisponible reste dans le dénominateur.

L'ordre des décisions est celui du protocole : référence TBF non qualifiée (`reference_unqualified`), charge non qualifiée (`load_scenario_unqualified`), garde-fou non satisfait (`guard_failed`), amélioration non démontrée (`improvement_not_demonstrated`), ou amélioration CAKE selon v1 (`static_cake_improvement_v1`). Les garde-fous détaillent séparément les régressions et valeurs indisponibles. Le débit utile, les échecs des 18 phases appariées et les neuf p50 idle sont contrôlés avant toute conclusion de latence.

Une collecte complète et exploitable sort avec `0`, quelle que soit la décision scientifique. Une erreur technique sort avec un code non nul et un état de session `failed`, `technical_valid: false`, `decision: non_exploitable` lorsque la session a été créée. Les interruptions gérées conservent leur code 129/130/143. Une erreur avant préparation ne crée pas de ressources réseau.

## Vérification et essai natif

Sans privilèges :

```sh
python3 -I -B scripts/lab-compare.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_comparison*.py' -v
python3 -I -B scripts/lab-compare.py analyze --artifacts DOSSIER_DE_COLLECTE
```

Les tests couvrent seuils inclusifs, trois blocs, différences négatives, percentiles indisponibles, priorités des décisions, preuves incohérentes, topologies réutilisées, environnement modifié, erreurs, interruptions et conservation des fichiers. Les opérations réseau et les comparaisons Go sont simulées dans les tests Python ; les anciennes données natives ont aussi été relues avec la vraie CLI pour vérifier la compatibilité de l'agrégateur, sans en déduire une nouvelle comparaison.

L'essai natif exige Linux, Python 3, `ip`, `tc`, `sysctl`, `ping`, les trois binaires Go figés et les capacités `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, `CAP_NET_RAW` via UID 0. Prévoir environ sept à dix minutes. Le lanceur d'expérience est lancé avec le compte habituel, vérifie les empreintes et appelle `sudo` pour les contrôles réseau ; la relecture `analyze` reste sans privilège. Conserver aussi les résultats défavorables, incomplets et stderr. Vérifier ensuite les ressources consignées et publier une validation datée avant toute conclusion native. Les limites du nettoyage restent celles du [superviseur](LAB_GUARD.md).
