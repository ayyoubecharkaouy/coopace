# Contexte et protocole interne du contrôle CAKE Go

## État et limites

`apps/gateway/internal/labcontrol` implémente le décodage du contexte, les instructions et leur enchaînement. `platforms/linux/namespace*.go` ajoute la vérification en lecture seule des descripteurs d'espace réseau sous Linux amd64. Le [transport hérité et le pilote privé](LAB_CAKE_TRANSPORT.md) complètent maintenant cette bibliothèque, avec des essais de processus et outils simulés. Le [backend natif borné](LAB_CAKE_BACKEND.md) est maintenant implémenté et assemblé en privé, avec essais par outils simulés. L’[entrée interne et le journal durable](LAB_CAKE_ENTRY.md) sont maintenant livrés ; le raccordement au superviseur et les contrôles natifs Go restent à réaliser. La passerelle conserve `inspect` et [`plan`](GATEWAY_PLANNING.md).

Cette sous-étape prépare le [contrat d'exécuteur](LAB_CAKE_EXECUTOR.md). Elle ne constitue ni sa réalisation complète ni une validation native du nettoyage d'un processus Go de contrôle CAKE.

## Trames et contexte

Les messages internes sont des objets JSON stricts précédés d'une longueur sur **quatre octets non signés, ordre réseau big-endian**. La limite porte sur le JSON, préfixe exclu : 4 096 octets pour l'initialisation et 1 024 pour une instruction. Une longueur nulle ou excessive est rejetée avant allocation du corps. Les trames tronquées, JSON ambigus et objets concaténés sont refusés ; la trame suivante reste disponible pour une autre lecture.

`ReadRequest` exige les six champs du contrat : `schema_version: 1`, `kind: lab_cake_worker_request`, `session_id`, `purpose: cake_down_control`, `reference: cake-ipv4-lab-4mbit-v1` et `namespace_identity` avec `device`/`inode`. Tous sont requis, non nuls et strictement typés. Les identités sont décodées en uint64 sans arrondi ; elles ne prouvent pas leur origine.

Le jeton comporte huit caractères ASCII parmi `a-z`, `0-9`, `_`, comme les réservations actuelles du superviseur. `NewSession` exige séparément le jeton attendu provenant du lancement de confiance ; il ne le déduit pas automatiquement du message. La requête décodée est opaque et sa valeur zéro est invalide. Les scénarios, rapports de simulation et booléens de permission ne peuvent pas remplacer ce contexte.

`ReadCommand` attend un objet v1 `lab_cake_worker_control` avec le même `session_id` et `action` égal à `apply` ou `finish`. Les commandes décodées sont opaques ; leur valeur zéro est invalide. Ces formats sont propres au laboratoire, indépendants des messages du groupe et du JSON de planification.

## Descripteurs et identité observée

`VerifyLabNamespace` reçoit l'identité attendue, le descripteur de cible conservé et celui de l'espace d'origine du superviseur. Il ouvre `/proc/thread-self/ns/net` en lecture seule et ferme cette référence locale après vérification. Il emprunte les deux descripteurs fournis sans les fermer ; leur propriétaire doit les maintenir valides, sans remplacement concurrent.

Le type des descripteurs est contrôlé via [`NS_GET_NSTYPE`](https://man7.org/linux/man-pages/man2/NS_GET_NSTYPE.2const.html), qui distingue les types d'espaces Linux. Les fichiers ordinaires et espaces PID sont refusés. Les identités doivent satisfaire : attendue = cible conservée = espace courant, avec un espace d'origine différent. Identité indisponible, inode zéro, descripteur absent/fermé ou échec de lecture provoquent un refus.

Ce backend est limité à **Linux amd64** ; les autres plateformes/architectures refusent cette opération. Le décodage reste compilable sur Windows. Aucun `setns`, création d'espace ou réglage réseau n'est effectué. Le futur processus doit être lancé dans son espace avant le démarrage de Go, sans changement d'espace par thread pendant le contrôle.

Cette vérification ne prouve pas une création récente, la propriété des ressources, l'origine du descripteur du superviseur ou l'accord de l'opérateur. Ces attestations et la transmission des canaux restent sous la responsabilité du futur lancement supervisé. Aucun simple nombre JSON ne remplace un descripteur observé.

## Enchaînement et délais

Une `Session` est utilisée séquentiellement par un seul processus :

| Étape | Vérification et résultat |
| --- | --- |
| Initialisation | Requête et jeton attendu cohérents, départ local valide ; état `need_binding`. |
| `BindNamespace` | Vérification des descripteurs ; état `bound`. |
| `Ready` | Descripteurs revérifiés et relevé initial vide/noqueue validé ; état `waiting_apply`. |
| Instruction `apply` | Même session, ordre correct, descripteurs revérifiés ; état `applying`. Aucun ajout exécuté par cette méthode. |
| `Applied` | Descripteurs revérifiés et relevé CAKE fourni validé ; état `waiting_finish`. |
| Instruction `finish` | Même session, ordre correct, descripteurs revérifiés ; état `finished`. |

Le [backend natif](LAB_CAKE_BACKEND.md) implémente les contrôles des interfaces DOWN et la collecte après ajout ; le pilote émet les événements. Leur validation native sur un espace neuf reste à réaliser. `Applied` valide les octets fournis ; il n'atteste pas à lui seul leur provenance du noyau ni une mutation réelle.

Un échec est permanent sur cet objet : doublon, session différente, instruction hors ordre, relevé incorrect ou EOF traité par `Receive` empêchent toute reprise. Une instruction après `finished` ne peut pas relancer le contrôle. L'unicité entre lancements appartient au superviseur ; la bibliothèque ne maintient pas de registre global de rejeu.

Le départ doit être capturé avec `time.Now` avant la lecture d'initialisation. La durée totale est de 30s ; chaque frontière dispose de 5s au maximum, sans dépasser l'échéance totale. Les comparaisons utilisent la composante monotone lorsqu'elle est conservée. L'expiration à la frontière exacte est refusée et les vérifications seules ne prolongent pas les délais.

**Ces contrôles d'horloge ont lieu aux appels de la bibliothèque.** Le lecteur de trames n'interrompt pas une lecture bloquée. Le [transport Linux](LAB_CAKE_TRANSPORT.md) fournit maintenant les échéances et annulations des canaux hérités. Les commandes natives bornées sont maintenant implémentées dans le [backend](LAB_CAKE_BACKEND.md) ; les signaux et l’arrêt sous le superviseur restent à raccorder. Ce module ne garantit pas de durée de vie autonome ni de nettoyage indépendant.

## Tests et preuves actuelles

```sh
sh scripts/go.sh test -count=1 -v ./apps/gateway/internal/labcontrol ./platforms/linux
```

Les tests couvrent champs requis, limites des trames, uint64, refus des formats de simulation, jeton attendu, valeurs zéro, instructions prématurées/rejouées, EOF, relevé incorrect, identité changée et échéances. Les transitions valides utilisent une horloge et un vérificateur de namespace simulés ; les règles d'identité sont vérifiées séparément.

Un test Linux en lecture seule vérifie le type réseau sur des descripteurs réels, refuse le type PID et confirme le refus de l'espace d'origine comme cible jetable. Les fichiers ordinaires et descripteurs fermés sont également refusés. Ce test est explicitement ignoré si la lecture native nécessaire est indisponible ; il ne crée aucun espace et ne remplace pas un essai positif dans une cible neuve.

Le [transport et ses tests de processus](LAB_CAKE_TRANSPORT.md) démontrent maintenant l’héritage lors d’un lancement ordinaire, le groupe du processus de test, les événements et l’annulation des canaux bloqués. Restent à démontrer : héritage à travers l’entrée dans un espace neuf, raccordement de l’entrée et des preuves au superviseur et nettoyage du contrôle après panne. Les tests Go généraux, l'analyse statique et les compilations Linux/Windows sont à maintenir lors du raccordement.
