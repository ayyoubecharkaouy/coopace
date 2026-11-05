# Relecture globale du dossier de campagne Go

## État et portée

`scripts/lab_cake_go_campaign_native_review.py` raccorde la [relecture des phases](LAB_CAKE_GO_CAMPAIGN_PHASE_REVIEW.md) aux preuves Go, à la topologie et au passage IPv4, puis aux entrées du [dossier figé](LAB_CAKE_GO_CAMPAIGN_PREPARE.md). L’entrée `lab-cake-go-campaign-review.py` expose cette relecture sans privilèges.

La relecture est implémentée et testée. **Le lanceur natif reste à développer.** La préparation garde `native_launcher_available: false`. Les anciens dossiers restent inchangés ; le futur lanceur demandera une nouvelle préparation depuis son propre commit.

Cette version n’écrit aucun certificat ni fichier de preuve. Elle retourne `state: campaign_evidence_reviewed` et `native_certificate: false` après acceptation des deux contrôles. Aucun essai réseau natif de cette campagne n’est validé à ce stade.

## Interfaces

| Entrée | Contrôle effectué |
| --- | --- |
| `validate_control(folder, report, tools, sources, build)` | Recalcule Go, activation, IPv4, phases et décisions d’un contrôle complet |
| `review(case)` | Vérifie la préparation, les binaires et les deux contrôles, puis les absences observées et la stabilité des pièces |

Pour consulter l’aide :

```sh
python3 -I -B scripts/lab-cake-go-campaign-review.py --help
```

Pour relire un dossier contenant les deux résultats :

```sh
python3 -I -B scripts/lab-cake-go-campaign-review.py --artifacts CHEMIN_DU_DOSSIER
```

Un dossier de préparation seule ne contient pas les résultats nécessaires : sa relecture est refusée et ne crée aucun certificat. L’entrée renvoie 0 pour une revue acceptée, 1 après refus et 2 pour une erreur d’arguments. Elle affiche le compte rendu sur stdout après acceptation et les diagnostics sur stderr après refus.

## Preuves recalculées

Le validateur commun des contrôles Go/trafic accepte un raccordement explicite pour le format de campagne. Son comportement par défaut et les formats historiques restent distincts ; les anciens relecteurs refusent le type de rapport de campagne.

La relecture de chaque contrôle exige :

1. Le type exact du rapport, une fin opérationnelle complète, le nettoyage attesté, le périmètre IPv4 synthétique et les noms/identités attendus.
2. Un environnement conforme aux outils et sources figés ; la phase Go normale, ses deux événements, ses 36 lignes durables et ses 14 appels sont reparsés depuis les captures. L’ajout unique et les relevés sur lien DOWN sont conservés.
3. Les intentions et résultats bruts d’activation, les quinze changements autorisés, les identités des interfaces, les adresses, routes et relevés CAKE. Les compteurs restent monotones et les différences DOWN/activation/IPv4/campagne restent distinctes.
4. Les six commandes de passage IPv4, leur ordre, leurs codes et captures : une requête sans réponse avec forwarding désactivé, puis trois requêtes/réponses avec forwarding activé.
5. Le lancement exact du pilote de campagne avec session, noms, chemins et manifeste des quatre outils attendus. La relecture indépendante des phases vérifie les identités, résultats, lectures brutes et frontières monotones.
6. Les deux groupes récupérés, les codes réels du worker et du pilote, les trois descendants récupérés en mode panne et la concordance des transitions de fin.

Les échantillons racine, ceux du groupe et ceux du journal sont rapprochés. Le journal est borné à 16 Mio pour la campagne, la collecte à 720 échantillons/4 Mio. La lecture des rapports peut atteindre 32 Mio, car les mêmes preuves apparaissent aussi dans les sous-rapports. Les limites historiques restent inchangées pour les anciens formats.

L’objet d’évaluation est recalculé puis comparé au rapport. Pour accepter le contrôle normal dans cette revue positive, les mesures doivent être exploitables, les trois charges qualifiées et les 60 connexions réussies. Une collecte techniquement complète mais non qualifiée reste un résultat conservé, sans acceptation positive de ce dossier. Le contrôle de panne conserve `technical_valid: null` et ses décisions de mesure non évaluées. Aucune comparaison ou amélioration propre à Coopace n’est déduite.

## Dossier figé et absences

La revue vérifie le sceau de `prepared.json`, le profil de campagne, le commit et les manifestes. Les fichiers suivis sont rapprochés des objets Git de la révision figée. Les neuf outils sont réempreintés et les quatre rôles Go doivent désigner les binaires canoniques du dossier. Le SDK relit chaque provenance avec `go version -m`, en accord avec la copie conservée et le commit Linux amd64 propre.

Les résultats attendus sont `run/` et `check-crash/`, leurs copies stdout, logs et codes de sortie, ainsi que `runtime.json`. Chaque mode doit avoir code 0, un rapport identique à stdout et le même environnement que la préparation. Les six noms de namespaces doivent être distincts entre les deux modes.

Les logs doivent attester le nettoyage. Les réservations, namespaces et PID consignés doivent être absents au moment de la relecture. Une réutilisation actuelle de PID peut provoquer un refus conservateur ; aucun processus n’est signalé. Les empreintes d’entrée et des pièces sont revérifiées en fin de revue.

Les seules commandes de la revue sont la lecture d’objets Git et `go version -m` via le SDK figé. Elle n’exécute ni ip, tc, ping, sudo, outil de trafic ni nettoyage.

## Vérification et suite

Les tests couvrent les décisions synthétiques, les altérations de préparation/outils/pièces, le raccordement des deux modes et l’absence de publication de certificat. Un contrôle de panne issu de vrais groupes de processus, avec réseau simulé, est relu de bout en bout Go/IPv4/phases. Les tests du dossier complet simulent les résultats Git/Go et le validateur de contrôle pour vérifier l’orchestration ; ils ne constituent pas une campagne réseau native. Les tests des relecteurs historiques restent vérifiés.

Validation locale du 5 novembre 2026 : 31 tests ciblés passent en 116,990 s, dont douze nouveaux tests de relecture globale et du dossier, six tests du relecteur Go/trafic historique, sept du passage IPv4 et six de la relecture des phases. Les provenances de compilation des tests de dossier sont simulées ; aucune validation native n’est publiée. La suite complète n’a pas été relancée pour cet ajout.

Prochaine sous-étape : raccorder le lanceur aux deux modes et à cette relecture, puis préparer un nouveau dossier avant les essais natifs.
