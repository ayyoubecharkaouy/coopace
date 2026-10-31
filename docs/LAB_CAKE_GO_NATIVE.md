# Protocole des deux contrôles natifs CAKE Go

## État et portée

Le [raccordement au superviseur](LAB_CAKE_GO_GUARD.md) passe ses tests avec réseau et programme du contrôle simulés. Cette procédure prépare sa première vérification avec le véritable binaire Go, l’entrée `setns`, les descripteurs hérités et les outils `ip`/`tc` du laboratoire. **Les résultats natifs restent en attente jusqu’à exécution et relecture des preuves.**

Deux contrôles distincts sont prévus : `check`, puis `check-crash`. Chacun possède trois espaces réseau neufs et un veth `wan`/`eth0` laissé DOWN. Le profil reste `cake-ipv4-lab-4mbit-v1`, sans adresse, route ni transfert. Seul le processus Go ajoute CAKE après l’instruction `apply` du superviseur.

## Préparation figée

Depuis un arbre Git propre, compiler `./apps/gateway/cmd/coopace-cake-worker` avec le SDK local, sans modification des sources. Conserver le binaire et la sortie `go version -m` dans un dossier neuf `.local/experiments/go-native-validation-REVISION/`. Exiger `vcs.revision` égal au commit préparé, `vcs.modified=false`, Linux amd64 et le SDK déclaré dans `.go-version`.

Le dossier contient avant tout lancement :

- `prepared.json` : commit, date UTC, noyau, Python, outils canoniques et empreintes ; état historique `not_run`.
- `inputs.sha256` : sources suivies, scripts du contrôle, protocoles, outils, binaire et fichiers locaux préparés.
- `build-info.txt`, `worker-help.txt` et `plan.txt` : provenance et prévisualisations sans privilèges.
- `run.sh` : deux invocations bornées, capture des sorties et codes, refus d’écrasement.
- `review-native.py` : relecture locale, sans commande réseau ni suppression de ressources.

Vérifier Python avec `os.setns`, Linux amd64 et le producteur `iproute2-6.1.0`. L’exécution exige les privilèges de laboratoire `CAP_NET_ADMIN` et `CAP_SYS_ADMIN` décrits dans [LAB_GUARD.md](LAB_GUARD.md). La présence des outils et leur version ne suffisent pas à valider CAKE dans le nouveau contrôle.

## Exécution locale

Lancer `sh CHEMIN_ABSOLU_DU_DOSSIER/run.sh` avec le compte habituel. Seules les deux invocations du superviseur utilisent `sudo` avec le chemin Python figé. Le lanceur vérifie les empreintes avant les contrôles, réserve son lancement et refuse un dossier contenant déjà des résultats. Une erreur arrête la séquence et conserve les pièces disponibles ; préparer un autre dossier après analyse au lieu de relancer sur les mêmes sorties.

Chaque invocation utilise `scripts/lab-cake-go.py MODE --worker BINAIRE_FIGÉ --artifacts DOSSIER_NEUF`. Les fichiers stdout, stderr et code du superviseur restent séparés des preuves internes `check/` et `check-crash/`. L’arrêt forcé intervient après `applied` et sa relecture indépendante, lorsque les appels d’outils du processus Go sont déjà terminés.

Après deux codes `0`, le lanceur exécute la relecture avec le compte habituel. Il conserve son code et sa sortie. Un code nul du superviseur seul ne remplace pas cette revue.

## Acceptation

| Élément | Fin normale | Arrêt forcé |
| --- | --- | --- |
| Code du superviseur | `0` | `0` |
| Code OS du processus Go | `0` | `-9` |
| Appels d’outils durables | 14 | 11 |
| Enregistrements du journal | 36, jusqu’à `worker_exit` | 27, jusqu’à `applied` |
| Ajouts CAKE | Un seul, après `apply_received` | Un seul, après `apply_received` |
| Événements du canal 4 | `ready`, puis `applied` | `ready`, puis `applied` |
| Relectures indépendantes | Après ajout et après arrêt | Après ajout et après arrêt |
| État publié | `complete`, nettoyage confirmé | `complete`, nettoyage confirmé |

La revue recalcule les contrats des trames et du journal avec les validateurs livrés : contexte lié à la session, espaces cible/origine distincts, provenance du vrai Go, chemins/empreintes/arguments exacts, sorties bornées, codes et statistiques conformes. Le relevé `applied` doit correspondre aux octets du journal. Les deux relevés CAKE Go du mode normal, ou celui du mode panne, sont rapprochés des deux relevés du superviseur ; les compteurs et jauges de trafic restent nuls sur le lien DOWN.

Les empreintes d’entrée et les sources du commit sont revérifiées. La sortie JSON du superviseur doit correspondre à son `report.json`. Les journaux stderr doivent confirmer la réservation et le nettoyage. Les noms des six espaces et les deux réservations doivent être distincts et absents après les contrôles ; les PID consignés doivent être absents sous `/proc` au moment de la revue. Une présence inattendue refuse la validation, sans signaler ni supprimer quoi que ce soit.

Le nombre de descendants récupérés est conservé tel qu’observé. Il n’est pas forcé à un : la panne intervient après récupération des outils. Ces deux contrôles ne démontrent pas la récupération d’un véritable outil Go tué pendant son exécution, ni la survie à la destruction du superviseur ou à une panne de l’hôte.

## Résultat et suite

`validation.json` est créé uniquement après relecture réussie des deux contrôles. Il conserve le commit, les synthèses recalculées, les observations d’absence et les empreintes des pièces. `prepared.json` garde son état initial. Les preuves restent locales et exclues de Git ; un bilan documentaire natif sera ajouté après examen des résultats.

Un succès valide ce cycle de vie DOWN. Le chemin actif avec le nouveau contrôle Go, le bénéfice propre à Coopace, la couverture du foyer et la restauration d’une passerelle réelle restent des activités distinctes.
