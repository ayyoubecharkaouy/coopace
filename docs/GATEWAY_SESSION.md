# Pilotage d'une session de passerelle

État au 14 novembre 2026 : automate Go, pilote privé, raccordement au moteur de restauration, lanceur figé et relecture implémentés. Les tests Go utilisent de vrais canaux avec une vérification de namespace simulée ; les tests Python simulent le réseau et le pair Go, avec de vrais processus et SIGKILL. Les [deux essais natifs du raccordement sont validés](VALIDATION_GATEWAY_SESSION_2026-11-14.md) : fin normale puis SIGKILL, retour à noqueue et nettoyage dans les deux modes. La [restauration sous le précédent pilote](VALIDATION_QUEUE_RECOVERY_2026-11-12.md) est déjà validée.

Ce raccordement remplace le pilote factice du cycle de restauration par une décision Go. `coopace-session-worker` demande au superviseur d'installer la référence CAKE du laboratoire, vérifie sa capture et demande l'arrêt. Le superviseur conserve les opérations privilégiées et le retour à noqueue. Les commandes publiques de `coopace-gateway` restent en lecture seule pour le réseau.

## Modules et responsabilités

| Emplacement | Responsabilité |
| --- | --- |
| `packages/core/gateway_session.go` | Automate pur, profil fixe, consentement explicite, empreinte initiale et commandes ordonnées à usage unique. |
| `apps/gateway/cmd/coopace-session-worker` | Entrée privée Linux amd64, sans privilèges ; aucune commande réseau exécutée. |
| `apps/gateway/internal/labcontrol/gateway_session*` | Import des captures, vérification des namespaces, transport hérité et journal durable partagé avec le contrôle DOWN. |
| `scripts/lab_gateway_session.py` | Dialogue avec Go et supervision ; réutilisation de `lab_queue_recovery.Engine` pour les opérations réseau. |
| `scripts/lab_gateway_session_review.py` | Relecture du dialogue et du journal, complétée par les contrôles communs de restauration et nettoyage. |
| `scripts/prepare-gateway-session.py` | Compilation des deux binaires depuis un arbre propre, empreintes des entrées et lanceur sans écrasement. |

## Cycle réellement exécuté

1. Le superviseur crée trois namespaces neufs et possédés, puis un veth `wan`/`eth0` actif sans adresse IP, après désactivation d'IPv6 dans ses deux espaces. Il capture et reconnaît le profil noqueue initial.
2. Un bootstrap Python entre dans le namespace retenu **avant** le démarrage du runtime Go. Il retire les groupes supplémentaires et abandonne UID/GID root. Le pilote refuse UID 0, UID effectif différent et capacités effectives non nulles.
3. Le pilote reçoit une initialisation liée à l'identifiant de réservation, au namespace, à l'UID opérateur, au profil fixe, au chemin et au SHA-256 exact de `before.json`. Le consentement local doit être explicitement vrai. Il importe la capture et exige un veth `wan` avec référence noqueue reconnue.
4. Go consigne `ready`. À la commande `begin`, il revérifie son namespace puis synchronise `apply_requested` avant de l'émettre. Le superviseur vérifie le dialogue avant d'appeler le moteur existant : nouvelle capture, comparaison, intention durable et ajout CAKE `10:` à 4 Mbit/s.
5. Le superviseur transmet `applied.json` avec son empreinte. Go vérifie l'import strict, la chronologie, l'identité du lien, les sélections vides et les options/statistiques du profil CAKE, puis consigne et émet `applied`.
6. En fin normale, `stop` produit `release_requested` et Go termine. Dans le contrôle de panne, le superviseur tue le pilote par SIGKILL après réception de `applied`.
7. Le superviseur récupère le groupe **avant** le retrait ciblé de la file. Il relit l'état et la possession, retire uniquement la CAKE reconnue, capture l'état final et exige `selected_state_matches`. Il ferme ensuite les références et supprime ses espaces possédés.

Le journal du pilote finit par une demande de récupération, pas par une affirmation de restauration. Seul le rapport du superviseur peut porter `session_state: restored_and_closed`, après comparaison et nettoyage réussis. Une panne, un journal défaillant ou un ajout incertain déclenche la récupération indépendante ; une configuration étrangère interdit le retrait et le rapport reste en échec.

## Contrat privé et bornes

Les descripteurs sont imposés par le lanceur : contrôle 3, événements 4, namespace cible 5, origine 6, journal privé append-only 7. Le bootstrap duplique les sources hors de cette plage avant remappage, ferme les autres descripteurs et exécute le binaire ELF épinglé. Le pilote n'entre jamais lui-même dans un namespace ; il vérifie les identités retenues et l'espace courant aux frontières du dialogue.

Chaque trame porte une longueur uint32 big-endian puis un JSON UTF-8 canonique de 16 Kio maximum, sans clés dupliquées, inconnues, alias de casse ou champs nuls. Les commandes ont les séquences 1/2/3 et restent liées au SHA-256 initial ; les événements ont les séquences 1 à 4. Répétition ou ordre invalide ferme la session. Chaque direction dispose de 64 Kio ; les écritures expirent en cinq secondes, les lectures Go en 25 secondes, et le processus en 90 secondes. Le superviseur possède son échéance de 120 secondes, puis des fenêtres indépendantes pour récupération et nettoyage.

Les captures importées restent limitées à 8 Mio, depuis des fichiers ordinaires sans lien symbolique final, avec contrôle des octets exacts. Le journal partagé est privé, régulier, à lien unique, limité à 8 Mio et synchronisé avant chaque événement. Les preuves supplémentaires, tronquées ou modifiées sont refusées. La relecture hors ligne compare également le dialogue à ce journal et à celui du superviseur, les deux mutations autorisées et l'absence des ressources enregistrées.

`--allow-lab` exprime l'accord local pour les ressources jetables du lanceur. Un SHA-256 n'authentifie pas une capture ; ces contrôles supposent le lanceur local de confiance. Cet accord ne démontre ni consentement du foyer, ni couverture Internet, ni autorisation sur une interface existante. La référence de 4 Mbit/s est celle de l'essai, sans estimation du débit du foyer.

## Vérifier et lancer

Prévisualisation sans privilèges :

```sh
python3 -I -B scripts/lab-gateway-session.py plan
```

Depuis un arbre Git propre, avec le compte habituel :

```sh
python3 -I -B scripts/prepare-gateway-session.py
```

Exécuter ensuite le `run.sh` absolu affiché. Il contient l'accord local au laboratoire et demande sudo pour les deux contrôles seulement. Chaque mode est suivi d'une relecture sans sudo ; un dossier ayant déjà des résultats est refusé. Le manifeste reste un enregistrement de préparation `not_run` ; les rapports séparés portent les résultats. Toute modification des entrées figées impose un nouveau dossier.

Tests de cette tranche :

```sh
sh scripts/go.sh test ./...
sh scripts/go.sh test -race ./packages/core ./apps/gateway/internal/labcontrol
sh scripts/go.sh vet ./...
(cd scripts/tests && python3 -B -m unittest test_lab_gateway_session test_prepare_gateway_session -v)
```

Ils couvrent le consentement absent/faux, l'identité ou l'empreinte différente, les commandes répétées, l'ordre, la perte de namespace, le journal défaillant, EOF/annulation, les événements supplémentaires et les alias numériques Python. Les contrôles de supervision couvrent fin normale, SIGKILL, panne du pair, erreur de journal, ajout incertain, interruption et refus des états étrangers. Le précédent cycle de restauration et sa relecture restent testés.

Les [deux sessions natives](VALIDATION_GATEWAY_SESSION_2026-11-14.md) valident maintenant la transmission des descripteurs, le démarrage sans privilèges dans le namespace et la restauration après sortie/panne. Le [contrôle fonctionnel pendant un transfert de 4 Mio](GATEWAY_SESSION_ACTIVE.md) est maintenant implémenté et testé avec réseau simulé et vrais processus ; ses deux essais natifs restent à exécuter. Le passage au réseau du foyer exige encore une topologie admissible, la couverture mesurée du trafic et une restauration adaptée à sa configuration. Aucun gain propre au pilotage Coopace, nouveau transfert, ni développement ML n'est déclaré par cette tranche.

Vérification de cette tranche : suite Go complète, `go vet ./...`, tests avec détecteur de courses du noyau et du contrôle, compilation Windows amd64 et 73 tests Python ciblés réussis. Les neuf tests Python du nouveau raccordement ont aussi été relancés après renforcement du protocole. Les deux anciens dossiers natifs de restauration sont encore relus avec leurs 105 empreintes chacun, sans modifier leurs preuves.

Le lancement utilisateur du 14 novembre 2026 du dossier `gateway-session-validation-2676d43` a été refusé avant création du laboratoire : noyau préparé `7.0.0-42-generic`, noyau actif `7.0.0-43-generic`, Python inchangé (`3.12.3`). La relecture retrouve les cinq fichiers de préparation, aucune exécution et toutes les entrées figées identiques. Le diagnostic affiche désormais chaque différence avec ses valeurs préparée/actuelle ; le refus est conservé et le nouveau dossier `gateway-session-validation-c2a196c` a ensuite [réussi ses deux contrôles natifs](VALIDATION_GATEWAY_SESSION_2026-11-14.md). Le refus initial et la réussite du dossier neuf sont conservés séparément.
