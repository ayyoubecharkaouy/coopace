# Deux contrôles natifs Go puis trafic — préparation et relecture

## État et portée

Le [contrôle combiné](LAB_CAKE_GO_COLLECT.md) passe ses tests avec réseau simulé et vrais processus. Les outils de préparation et de relecture native sont livrés. **Les deux essais natifs combinés sont [validés au 1er novembre 2026](VALIDATION_CAKE_GO_ACTIVE_2026-11-01.md).** Les preuves historiques [Go DOWN](VALIDATION_CAKE_GO_DOWN_2026-11-01.md) et CAKE actif Python restent des validations séparées.

Ce protocole vise un seul transfert complet de 8 Mio dans le contrôle normal, puis une panne du pilote de trafic pendant l’attente de l’accusé dans un second laboratoire neuf. Dans les deux modes, le processus Go termine normalement son cycle DOWN avant activation. La panne ne tue pas le processus Go pendant un appel d’outil.

## Préparation sans privilèges

Depuis un arbre Git propre, lancer avec le compte habituel :

```sh
python3 -I -B scripts/prepare-cake-go-active.py
```

Le préparateur crée un dossier privé neuf `.local/experiments/go-active-native-validation-REVISION/`. Un autre chemin neuf peut être fourni avec `--artifacts`, dont le parent doit exister. Un dossier existant n’est jamais réutilisé.

Il compile quatre programmes avec le SDK déclaré dans `.go-version`, `-trimpath` et `-buildvcs=true` :

| Binaire | Source |
| --- | --- |
| `coopace-cake-worker` | `./apps/gateway/cmd/coopace-cake-worker` |
| `coopace` | `./apps/agent/cmd/coopace` |
| `coopace-lab-tcp` | `./scripts/lab-tcp` |
| `coopace-lab-load` | `./scripts/lab-load` |

La provenance de chaque binaire doit indiquer le commit préparé, `vcs.modified=false`, Linux amd64 et le SDK prévu. Les aides sont exécutées sans accès réseau. Python avec `os.setns` et le producteur CAKE identifié `iproute2-6.1.0` sont vérifiés en lecture seule ; aucun namespace ni qdisc n’est créé pendant cette préparation.

Le dossier conserve les binaires, leurs quatre sorties `go version -m`, leurs aides, `plan.txt`, une copie de ce protocole et du préparateur. `prepared.json` reste dans son état historique `not_run`, protégé contre une modification accidentelle par `prepared.sha256`. `inputs.sha256` et le manifeste JSON figent les fichiers suivis, outils canoniques, SDK, binaires et fichiers locaux du lanceur. Le commit de contexte ne remplace pas ces empreintes.

## Exécution dans le terminal utilisateur

Lancer `sh CHEMIN_ABSOLU_DU_DOSSIER/run.sh` avec le compte habituel. Le script vérifie les empreintes et le commit avant chaque invocation, réserve son lancement et refuse tout résultat préexistant. Seuls les deux contrôles utilisent `sudo`, avec le Python et les binaires figés.

Les contrôles exigent les privilèges de laboratoire documentés dans [LAB_GUARD.md](LAB_GUARD.md), notamment la création des namespaces et l’entrée réseau. Ils ne touchent ni interface physique, route par défaut, NAT ou accès Internet du foyer.

Le lanceur conserve stdout, stderr et code de sortie pour `check`, puis `check-crash`. Un échec arrête la suite et conserve les preuves : préparer un autre dossier après analyse, sans écraser le premier essai. Un lancement interrompu ne doit pas être repris sur les mêmes fichiers.

Après deux codes `0`, le script lance la relecture locale avec le compte habituel. La durée attendue est de l’ordre d’une minute, sans garantie liée au matériel. Les bornes indépendantes du superviseur et de son nettoyage restent celles du contrat.

## Critères d’acceptation

| Élément | `check` | `check-crash` |
| --- | --- | --- |
| Code superviseur | 0 | 0 |
| Phase Go normale | 0, 14 appels, 36 lignes durables | 0, 14 appels, 36 lignes durables |
| Code OS du pilote de trafic | 0 | -9 |
| Outils orphelins récupérés | 0 | 3 |
| Transfert et sondes | 8 388 608 octets reçus, dix réussites et recouvrement confirmé | `flow: null`, aucun accusé envoyé |
| File et topologie | Même `wan` et même CAKE, compteurs monotones, différence de trafic positive et vidage normal | Même `wan` et même CAKE, relecture après arrêt |
| Nettoyage | Deux groupes récupérés, espaces et réservation retirés | Deux groupes récupérés, espaces et réservation retirés |

Les deux sessions doivent avoir des jetons et six noms d’espaces distincts. La réutilisation d’un inode par le noyau entre deux expériences n’est pas interdite ; la continuité se vérifie pendant chaque session.

## Relecture indépendante

`review-native.py` du dossier appelle `scripts/lab-cake-go-active-review.py`. La revue ne lance aucune commande `ip`, `tc` ou de nettoyage. Elle relit les preuves et les sources figées, ainsi que la provenance des binaires par `go version -m` et les objets Git du commit.

Elle recalcule les trames et le journal Go, les configurations/statistiques CAKE et les différences. Les quinze changements d’activation et les sorties brutes sont rapprochés des topologies normalisées. Les identités de `wan`, les adresses/routes, le forwarding, les trois rôles/PID et l’ordre des transitions doivent concorder. Les exports du flux sont revalidés, y compris réception, plafonds, durée de stabilisation, tentatives et percentiles au rang le plus proche. Les échecs ne deviennent pas des durées nulles ni une preuve de perte de paquets.

La revue vérifie les captures, la cadence et le double relevé vide. Le délai de trois secondes du vidage est imposé par l’exécuteur figé ; son instant interne d’observation de sortie n’est pas conservé comme événement distinct et n’est donc pas recalculé intégralement hors ligne.

Les noms/réservations et PID consignés doivent être absents au moment de la revue. Une présence refuse la validation sans signal ni suppression automatique ; un PID réutilisé peut donc imposer une analyse séparée. Les fichiers sont empreintés avant/après relecture pour détecter une modification pendant celle-ci.

`validation.json` n’est créé qu’après acceptation des deux contrôles. Il conserve `native_cake_go_active_validated`, commit, synthèses recalculées et empreintes des pièces. Une relecture identique conserve une validation existante ; une divergence est refusée. Le préparateur reste inchangé en `not_run`.

Pour relire ultérieurement, restituer les sources et documents suivis du commit préparé à leurs chemins d’origine : le manifeste inclut aussi les documents, et une modification ultérieure doit être refusée. Conserver les pièces locales et les manifestes inchangés, puis lancer :

```sh
python3 -I -B scripts/lab-cake-go-active-review.py --artifacts CHEMIN_DU_DOSSIER
```

Les tests des relecteurs utilisent des preuves synthétiques et ne publient aucun certificat natif. Ce protocole ne mesure pas un gain propre à Coopace, ne valide ni IPv6/DNS, la couverture du foyer, la restauration réelle, ni la mort de Go pendant un outil actif.

Validation locale du 1er novembre 2026 : les 177 tests Python passent en 419,522 s, dont six tests de relecture et trois tests du préparateur/lanceur. La suite Go `sh scripts/go.sh test ./...` passe également. Ces résultats vérifient les outils et les simulations ; ils ne remplacent pas les deux contrôles natifs décrits ici.
