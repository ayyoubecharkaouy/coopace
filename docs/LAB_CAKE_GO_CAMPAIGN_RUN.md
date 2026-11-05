# Lanceur des essais de campagne Go

## État et portée

Le [préparateur de campagne](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) génère maintenant `run.sh` et `review-native.py` dans chaque nouveau dossier figé. Le manifeste porte `native_launcher_available: true`. Les deux fichiers générés sont inclus dans les empreintes des entrées.

Le lanceur est implémenté et testé avec un faux sudo. Aucun essai réseau natif de cette campagne n’est validé à ce stade. Les anciens dossiers préparés sans lanceur restent inchangés ; un nouveau dossier doit être préparé depuis le commit courant propre.

## Préparation et exécution

Avec le compte habituel, depuis la racine du dépôt :

```sh
python3 -I -B scripts/prepare-cake-go-campaign.py
```

Le préparateur affiche le chemin du nouveau dossier. Pour l’essai natif, lancer son script avec le compte habituel :

```sh
sh CHEMIN_ABSOLU_DU_DOSSIER/run.sh
```

Le script appelle sudo seulement pour les deux contrôles. La préparation et la relecture s’exécutent sans privilèges. Prévoir deux à trois minutes : trois paires repos/charge avec trois transferts de 8 Mio, puis une première phase idle et une panne au ready chargé dans un autre laboratoire neuf.

## Déroulement et protections

1. Refuser un lancement en root, réserver `run.lock`, puis refuser les résultats existants, y compris les liens symboliques.
2. Vérifier `inputs.sha256`, le sceau de `prepared.json`, leur concordance, le drapeau de disponibilité du lanceur et le commit. Conserver les versions de noyau/Python dans `runtime.json`.
3. Créer seulement le dossier `run/`, appeler la commande de campagne avec les binaires figés et conserver stdout, stderr et code de sortie.
4. Après code 0 et nouvelle vérification des entrées, créer `check-crash/` et exécuter le second contrôle avec ses propres ressources.
5. Après deux codes 0 et nouvelle vérification des entrées, appeler `review-native.py` sans sudo. Ce wrapper charge la [relecture globale](LAB_CAKE_GO_CAMPAIGN_GLOBAL_REVIEW.md) du commit figé.
6. Conserver le code de revue et revérifier les entrées avant la sortie finale.

Les chemins avec espaces sont cités. Les redirections utilisent le mode sans écrasement. Le verrou du lancement est retiré à la sortie ; un verrou déjà présent appartient à un autre lancement et n’est pas retiré. Les résultats partiels restent conservés après une erreur. Un nouvel essai exige un nouveau dossier.

Les contrôles restent limités aux namespaces, liens et groupes jetables possédés. Leurs délais et nettoyage sont ceux du [contrat v1](LAB_CAKE_GO_CAMPAIGN.md). Le lanceur n’ajoute aucun réglage ni seuil.

## Résultats et codes

| Fichiers | Contenu |
| --- | --- |
| `runtime.json` | Environnement au début du lancement |
| `run/`, `check-crash/` | Rapports et captures détaillés de chaque contrôle |
| `run.stdout.json`, `check-crash.stdout.json` | Rapports publiés sur stdout |
| `run.log`, `check-crash.log` | Diagnostics et traces de nettoyage |
| `run.exit`, `check-crash.exit` | Codes réels des contrôles |
| `review.stdout.json`, `review.log`, `review.exit` | Compte rendu, diagnostic et code de la relecture |

Un échec de contrôle interrompt la suite et conserve son code. Un refus d’entrées ou de réutilisation donne le code 2. Après les deux contrôles, un refus du relecteur est conservé dans `review.exit` et propagé à la sortie. Une modification des entrées après la revue interdit un succès du lanceur.

Trois codes 0 signifient que la collecte et la revue ont été acceptées. Le relecteur garde `native_certificate: false` et ne publie pas `validation.json` ; les preuves seront examinées pour consigner la première validation native. Aucun gain du pilotage Coopace ni bénéfice du foyer n’est déduit automatiquement.

## Vérification et suite

Les tests du lanceur utilisent un faux sudo qui vérifie l’entrée appelée, les modes, les options et les dossiers. Un faux relecteur vérifie l’ordre. Les cas couvrent la réussite, le refus de relance, les résultats/liens/verrous existants, le commit et les empreintes modifiés, un manifeste divergent, un dossier non prêt, les erreurs des deux contrôles, le refus de revue et les changements entre les étapes. Ils ne lancent aucun contrôle réseau natif.

Validation locale du 5 novembre 2026 : 32 tests ciblés passent en 6,207 s, dont sept nouveaux tests du lanceur, cinq tests de préparation de campagne, sept des préparateurs historiques, huit de la commande de campagne et cinq du raccordement au dossier figé. Les contrôles sudo, la compilation et les rapports réseau sont simulés dans ces tests. La suite complète n’a pas été relancée pour cet ajout.

Prochaine étape : exécuter le nouveau dossier sur l’hôte Linux, relire les preuves et consigner les résultats, y compris tout refus, sans réécrire les essais précédents.
