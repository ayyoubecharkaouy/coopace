# Backend CAKE Go du contrôle DOWN

## État et portée

Le backend natif est implémenté dans `platforms/linux`, avec assemblage privé dans `apps/gateway/internal/labcontrol/native_linux.go`. Il fournit au [pilote interne](LAB_CAKE_TRANSPORT.md) les opérations de préparation, ajout/relecture et vérification finale. **Les essais positifs utilisent des exécutables ELF simulant `ip` et `tc`, des relevés synthétiques et les fixtures CAKE. Aucun vrai appel `ip`/`tc` ni changement réseau n’est effectué par ces essais.**

Le chemin par défaut utilise les vérifications natives des espaces réseau ; il n’accepte aucun vérificateur fourni par l’appelant. Un test confirme le refus de l’espace d’origine avant tout outil. Le vérificateur permissif des essais positifs est privé au paquet et n’existe dans aucune option CLI, JSON ou variable d’environnement du produit.

La première cible est Linux amd64. La passerelle publique conserve `inspect` et `plan`. L’[entrée interne et le journal durable](LAB_CAKE_ENTRY.md) sont maintenant livrés ; le raccordement au superviseur reste à développer selon le [contrat d’exécuteur](LAB_CAKE_EXECUTOR.md). Cette livraison n’est pas une validation native de l’application CAKE ni du nettoyage du nouveau contrôle.

## Rangement et API

| Fichier | Responsabilité |
| --- | --- |
| `platforms/linux/cake_control.go` | Types internes de lancement d’outil, identité du lien et traces Go. |
| `platforms/linux/cake_link.go` | Validation pure des relevés JSON de lien/adresses. |
| `platforms/linux/cake_command_linux.go` | Vérification des exécutables et appels bornés. |
| `platforms/linux/cake_control_linux.go` | Cycle unique du backend et collecte des traces. |
| `apps/gateway/internal/labcontrol/native_linux.go` | Assemblage privé du backend avec la session et le transport. |

`NewLabCakeControl` valide les paramètres sans lancer d’outil. Les descripteurs cible/origine sont empruntés au transport, qui les ferme à la fin. L’appelant doit toujours établir l’accord local et la propriété des ressources neuves ; le backend ne les déduit pas d’identifiants déclarés.

| Méthode | Effet |
| --- | --- |
| `Prepare` | Vérification native de la liaison, bannière `tc`, lien DOWN et file initiale vide/noqueue ; aucun ajout. |
| `Apply` | Revérifications du lien et de l’état initial, unique ajout du profil fixe, puis relecture et validation CAKE. L’application l’appelle seulement après l’instruction `apply` de la session. |
| `Final` | Revérification du lien et du relevé CAKE avant la fin ; aucune suppression. |
| `Evidence` | Copie indépendante des observations et appels, y compris les échecs et sorties partielles. |

Le cycle est `new` → `prepared` → `applying` → `applied` → `finished`. Une erreur ou un appel hors ordre donne un échec permanent. Aucun ajout n’est retenté, même si la première opération échoue avant sa relecture. `AddAttempted` reste conservateur dès le départ de la tentative ; l’effet noyau d’un ajout échoué reste inconnu et doit être nettoyé par le superviseur.

## Lien admis

Les requêtes sont fixes : `ip -j -d link show` et `ip -j address show dev wan`. Le relevé doit contenir exactement `lo` et `wan`, avec des indices positifs distincts et aucun drapeau `UP`. `lo` doit porter `LOOPBACK`, contrairement à `wan`.

`wan` doit être un veth Ethernet, état opérationnel DOWN, avec MTU et indice de pair valides et MAC unicast non nulle. Le relevé d’adresses doit confirmer son indice et une liste `addr_info` explicitement vide. Indices de `lo`/`wan`, indice du pair, MTU et MAC sont conservés et comparés aux lectures suivantes. Les JSON sont limités à 64 Kio et soumis au contrôle de syntaxe strict des relevés natifs.

Ces observations ne prouvent pas la propriété du pair ni une création récente. Les routes, le forwarding, l’espace serveur et le journal de création restent sous la responsabilité du superviseur. Le backend ne crée ni lien ni adresse et n’active aucun forwarding. La compatibilité des nouveaux relevés `ip` avec l’hôte de laboratoire reste à confirmer lors du futur contrôle natif.

## Exécutables et appels bornés

Les chemins et SHA-256 de `ip` et `tc` sont des paramètres Go du lancement de confiance, sans entrée dans le scénario de planification. Les chemins doivent être absolus et canoniques, sans lien symbolique. Chaque appel ouvre un fichier régulier exécutable ELF, limité à 64 Mio, et revérifie son SHA-256 avant de le lancer. Les scripts et interpréteurs shell sont refusés.

Le fichier vérifié reste ouvert et est exécuté via `/proc/self/fd/3` dans l’enfant ; son chemin n’est pas résolu une seconde fois pour sélectionner l’exécutable. Ce descripteur 3 désigne alors le fichier ELF, jamais le canal de contrôle du processus Go. Aucun descripteur de contrôle ou d’espace réseau n’est transmis aux outils. Le système et ses bibliothèques restent dans la base de confiance du lancement.

L’environnement des outils contient uniquement `LANG=C` et `LC_ALL=C`. Aucun shell, résolution PATH, argument libre, changement d’espace ou création d’un nouveau groupe de processus n’est utilisé. Les outils restent dans le groupe du processus Go pour permettre la récupération future par le superviseur.

Chaque appel reçoit la borne la plus proche entre le contexte de la phase et deux secondes, vérification d’empreinte comprise. stdout et stderr sont limités séparément à 64 Kio ; stdout de `tc -V` est limité à 512 octets. Un dépassement annule l’appel et conserve le préfixe borné avec un indicateur de troncature. `Wait` récupère le processus ; le drainage des canaux utilise `WaitDelay` à 100 ms. Les outils fixes sont supposés ne pas engendrer de descendants indépendants ; la récupération après mort du processus Go relève toujours du superviseur.

La bannière doit correspondre au producteur `iproute2-6.1.0`. La file est relue par `tc -j -s -r qdisc show dev wan`. L’unique modification possible est le `qdisc add` obtenu à nouveau depuis le catalogue `cake-ipv4-lab-4mbit-v1` ; aucun remplacement, suppression, débit libre ou repli n’est ajouté.

## Traces et limites actuelles

Chaque appel conserve chemin et empreinte attendue, arguments, départ UTC, durée monotone, PID si démarré, code si récupéré, stdout/stderr, troncatures et erreur. Une empreinte refusée peut donc laisser une trace sans PID ni code ; elle ne signifie pas qu’un outil a été exécuté. La bannière et l’identité du lien sont également conservées. Un cycle normal contient quatorze appels aux outils.

Ces objets sont des traces Go en mémoire, pas un nouveau format JSON public. Ils ne sont pas automatiquement inclus dans les événements `ready`/`applied`. Leur [conservation durable](LAB_CAKE_ENTRY.md) est maintenant raccordée au backend par `LabToolObserver`, avant dispatch et après récupération. Leur intégration au bilan du superviseur reste à réaliser. Ils n’attestent ni nettoyage ni restauration d’une passerelle existante.

## Vérification et suite

```sh
sh scripts/go.sh test -count=1 -v ./platforms/linux ./apps/gateway/internal/labcontrol
sh scripts/go.sh test -race -count=1 ./platforms/linux ./apps/gateway/internal/labcontrol
```

Les tests vérifient le cycle complet, l’absence d’ajout pendant `Prepare`, les arguments fixes, la relecture finale, la copie des traces, les refus de version/empreinte/lien/adresses/file préexistante, les sorties excessives, la limite exacte de bannière, les échecs partiels d’ajout, l’expiration et la récupération des outils. Les références de namespace positives et les relevés réseau sont simulés ; les processus, exécutions ELF, limites et attentes sont réels.

L’[entrée interne et le journal durable](LAB_CAKE_ENTRY.md) sont maintenant livrés. La suite raccorde le processus au superviseur Python sans modifier les contrôles historiques. Elle doit démontrer l’héritage des descripteurs à travers l’entrée dans un espace neuf, la récupération d’un outil après mort forcée du processus Go et les deux contrôles natifs DOWN. Le chemin actif, la restauration du foyer et le pilotage automatique restent ultérieurs.
