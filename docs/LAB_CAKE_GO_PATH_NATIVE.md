# Essais natifs du passage IPv4 après Go — préparation et relecture

## État et portée

Le [raccordement du passage IPv4](LAB_CAKE_GO_PATH_CONTROL.md) est testé avec réseau simulé et vrais processus. La préparation figée et la relecture indépendante de ses preuves sont livrées. **Les deux contrôles corrigés sont [validés en natif](VALIDATION_CAKE_GO_PATH_2026-11-01.md).** La [preuve combinée historique](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md) reste distincte.

Le contrôle doit confirmer successivement Go DOWN, activation des mêmes ressources, blocage IPv4 sans forwarding, passage après réactivation, puis transfert TCP ou panne du pilote de trafic. Chaque mode utilise son propre laboratoire neuf.

Le [premier essai au commit afa0b22](REVIEW_CAKE_GO_PATH_FAILURE_2026-11-01.md) a été refusé : la sonde négative a émis trois requêtes avec `-w`. La correction supprime `-w` des deux sondes, conserve une puis trois requêtes exigées et garde les bornes externes de 4/6 s. Le nouveau dossier doit être préparé depuis les sources corrigées ; l’ancien essai reste conservé.

## Préparation sans privilèges

Depuis un arbre Git propre, avec le compte habituel :

```sh
python3 -I -B scripts/prepare-cake-go-path.py
```

Le préparateur réutilise la compilation et les protections du [préparateur combiné](LAB_CAKE_GO_ACTIVE_NATIVE.md), avec un profil distinct. Il crée `.local/experiments/go-path-native-validation-REVISION/`, sans réutiliser un dossier existant. `--artifacts` permet un autre dossier neuf dont le parent existe.

Quatre binaires sont compilés avec le SDK de `.go-version`, Linux amd64, `-trimpath` et `-buildvcs=true` : worker CAKE, agent, cible TCP et outil de transfert. Leur provenance doit indiquer le commit préparé et `vcs.modified=false`.

Les chemins canoniques et empreintes des outils sont figés, y compris ping. `ping -V` est exécuté sans réseau et doit annoncer iputils ; ses deux sorties sont conservées dans `ping-version.json` et le manifeste. Le producteur CAKE reste iproute2-6.1.0. Aides, plan, sources suivies, SDK, scripts, protocole et binaires sont figés dans `inputs.sha256` et `prepared.json`, lui-même protégé par `prepared.sha256`.

`prepared.json` conserve son état historique `not_run` avec `kind: lab_cake_go_path_preparation`. La préparation ne crée aucun namespace et ne modifie aucune file.

## Exécution utilisateur

Lancer avec le compte habituel `sh CHEMIN_ABSOLU_DU_DOSSIER/run.sh`. Le script appelle sudo uniquement pour `check` puis `check-crash` de `lab-cake-go-path.py` avec les quatre binaires figés. Il vérifie empreintes et commit avant chaque contrôle, réserve le lancement et refuse tout résultat préexistant. Un échec interrompt la suite et conserve les résultats.

Prévoir une à deux minutes : deux paires de sondes négative/positive, un transfert complet de 8 Mio dans le mode normal, puis panne du pilote de trafic dans le second mode. La création et l’entrée dans les espaces réseau exigent les privilèges de laboratoire déjà documentés. Les contrôles restent dans trois espaces jetables par mode, sans interface physique, NAT, route par défaut ou accès Internet.

Après deux codes `0`, la relecture est lancée sans privilèges. Le lanceur conserve stdout, stderr et code de chaque contrôle et de la revue. Un essai interrompu ou refusé demande un nouveau dossier après analyse ; ses preuves ne sont jamais écrasées.

## Acceptation et relecture

| Élément | Exigence dans les deux contrôles |
| --- | --- |
| Sources et outils | Empreintes figées, commit et quatre provenances Go conformes ; même version de ping que la préparation |
| Phase Go | Code 0, 14 appels, 36 lignes durables, ajout unique de CAKE sur lien DOWN |
| Passage négatif | Forwarding relu exactement à 0, une requête émise, zéro réponse, code ping 1 |
| Passage positif | Forwarding relu exactement à 1, trois requêtes et trois réponses, code ping 0 |
| Ordre | Six commandes fixes après activation et avant toute intention de lancement TCP |
| Continuité | Même lien et même CAKE, lectures intermédiaires conformes, compteurs monotones et différences distinctes |
| Nettoyage | Deux groupes récupérés, six commandes de passage arrêtées, espaces/réservations et PID consignés absents lors de la revue |

Le contrôle normal doit aussi recevoir les 8 388 608 octets, conserver dix connexions TCP réussies avec recouvrement confirmé et vider la file. Le contrôle de panne doit conserver Go `0`, pilote de trafic `-9`, trois outils orphelins récupérés, aucun accusé et `flow: null`.

`lab-cake-go-path-review.py` réutilise explicitement les validations communes Go/topologie/collecte/TCP, puis recalcule les six commandes depuis leurs captures et leurs positions dans le journal. Le relecteur historique sans ce profil continue à refuser le nouveau rapport.

La revue rapproche chaque intention de son résultat, des arguments fermés et du rapport ; elle recalcule comptes et états relus, vérifie PID, code OS, arrêt confirmé, troncature et dates. La durée totale consignée doit rester dans la borne de 2/4/6 s : elle inclut les vérifications après sortie et constitue donc une limite conservatrice, susceptible de refuser un essai sur hôte très chargé. Les identités des liens intermédiaires sont reparsées, même lorsque la topologie finale est conforme.

Les relevés immédiatement avant/après le passage sont reliés aux sorties brutes et aux transitions. Leur différence ne remplace ni celle d’activation ni celle du TCP. Les limites d’observation du délai interne de vidage restent celles de la revue combinée. Les vérifications de possession exécutées par le contrôleur figé ne deviennent pas des observations du réseau domestique.

La revue n’exécute aucune commande `ip`, `tc`, `ping` ou de nettoyage. Elle utilise seulement les fichiers, les objets Git, `go version -m` et l’observation des absences. Un PID réutilisé peut causer un refus ; aucun processus n’est signalé. Une réutilisation de PID entre deux commandes déjà récupérées n’est pas à elle seule un échec.

`validation.json` n’est publié qu’après acceptation des deux modes avec `state: native_cake_go_path_validated`, commit, faits recalculés et empreintes des pièces. Une relecture identique conserve un certificat existant. Les tests synthétiques ne publient aucun certificat natif.

Pour relire ultérieurement :

```sh
python3 -I -B scripts/lab-cake-go-path-review.py --artifacts CHEMIN_DU_DOSSIER
```

Les fichiers suivis doivent correspondre au commit préparé à leurs chemins d’origine, y compris les documents. Une modification ultérieure doit être refusée sans réécrire les manifestes ou les preuves.

Validation de l’outillage avant le premier essai `afa0b22` : les 209 tests Python passent en 493,072 s, dont sept tests de relecture du passage et quatre du profil de préparation/lanceur. Les captures synthétiques et les faux appels sudo de ces tests ne valident aucun essai réseau natif.

Après correction des options ping, les 210 tests Python passent en 484,311 s. La capture native à trois envois reste refusée par le nouveau test de régression ; la simulation représente l’effet de `-w`. La [validation native du passage IPv4](VALIDATION_CAKE_GO_PATH_2026-11-01.md) confirme ensuite les deux contrôles corrigés, préparés dans un dossier neuf.

Le [contrat de campagne répétée Go](LAB_CAKE_GO_CAMPAIGN.md) est défini avant collecte : trois paires repos/charge, dialogue lié à la session et critères séparés. Les [lecteurs et l’automate purs](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md) sont implémentés et couverts par quatorze tests. Le [pilote privé des six phases](LAB_CAKE_GO_CAMPAIGN_TRAFFIC.md) est livré et testé avec outils simulés et vrais processus. Le [collecteur des six phases](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) est implémenté et testé avec réseau simulé : contrôle des PID, journal durable et vidage entre phases. L’[évaluation pure des mesures](LAB_CAKE_GO_CAMPAIGN_ASSESS.md) est implémentée et testée. Le [rapport global](LAB_CAKE_GO_CAMPAIGN_REPORT.md) la raccorde maintenant aux preuves du superviseur après nettoyage. La commande publique, la préparation/relecture et les essais natifs de campagne restent ultérieurs. Le bénéfice propre à Coopace, une campagne comparative de l’intégration Go, IPv6/DNS, la couverture du foyer, la restauration réelle et la mort de Go pendant un outil actif restent hors de cette validation.
