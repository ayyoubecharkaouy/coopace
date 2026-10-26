# Identité et contrats du groupe — étapes 3.3 et 3.4

## Périmètre livré

L'étape 3.3 a fourni l'identité persistante Linux, le modèle de consentement et les premiers contrats hors réseau. L'étape 3.4 ajoute les certificats, l'approbation et le consentement persistés, le transport TLS et un premier échange borné. Les contrats réseau sont maintenant en version 2. La [procédure d'échange](GROUP_EXCHANGE.md) décrit les commandes et la validation ; le présent document précise les identités et les messages.

## Identité locale

L'agent génère une clé [Ed25519](https://pkg.go.dev/crypto/ed25519) avec le générateur aléatoire de la bibliothèque standard. Son identifiant public est :

```text
ed25519:<SHA-256 des 32 octets bruts de la clé publique, en hexadécimal minuscule>
```

Le nom du PC, son adresse IP et sa MAC ne participent pas à cet identifiant. L'empreinte identifie une clé ; elle ne constitue ni une preuve de possession à distance, ni une approbation du pair, ni un consentement de l'utilisateur. La même clé garde la même empreinte dans plusieurs groupes.

Sous Linux, depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/agent/cmd/coopace identity init --state-dir .local/state
sh scripts/go.sh run ./apps/agent/cmd/coopace identity show --state-dir .local/state
```

Le dossier est explicite. `init` crée une identité ou recharge celle qui existe ; `show` ne crée rien. La sortie contient uniquement l'identifiant et la clé publique en base64, avec l'état « hors groupe ». `status` continue de décrire l'exécution locale, sans adhésion implicite.

La clé privée est enregistrée dans `identity.key`, au format PKCS#8/PEM via la [bibliothèque x509](https://pkg.go.dev/crypto/x509#MarshalPKCS8PrivateKey). Le fichier n'est pas chiffré : sa protection locale repose sur les permissions Linux, avec création du dossier en `0700` et du fichier en `0600`. Le chargement refuse les accès groupe/autres, les liens symboliques à la place du dossier final ou du fichier, les formats invalides et les fichiers dépassant 16 Kio.

La création du fichier est exclusive et son contenu est synchronisé avant relecture. Une clé existante corrompue n'est jamais remplacée automatiquement. Des initialisations concurrentes peuvent échouer pendant la première écriture ; elles ne doivent pas provoquer de rotation silencieuse. Chaque appareil utilise sa propre clé et son propre état. Copier la clé privée duplique l'identité ; la perdre impose une nouvelle identité et une nouvelle approbation des pairs.

`.local/` et les fichiers `*.key` sont exclus de Git. Le prototype ne gère pas encore le chiffrement au repos, la sauvegarde, la rotation ni un coffre de clés du système.

## Consentement et admission

`core.GroupConsent` distingue :

| Champ | Portée |
| --- | --- |
| `GroupID`, `DeviceID` | Groupe et appareil concernés. L'identifiant de groupe n'est pas un secret d'authentification. |
| `Join` | Consentement local à participer au groupe. |
| `ShareObservations` | Consentement séparé au partage des observations. |
| `AllowRelay` | Consentement distinct au rôle de relais, qui reste non implémenté. |

Les permissions sont fausses par défaut. Partage et relais exigent le consentement à rejoindre ; rejoindre seul n'autorise pas les autres usages. `AllowsObservationSharing` vérifie aussi le groupe et l'identifiant de l'appareil. Ce modèle est persisté dans le fichier privé `group.json` à l'étape 3.4. `group configure` exige `--join`, conserve le partage désactivé par défaut et approuve un seul pair par groupe local. `group revoke` retire adhésion et partage ; voir [GROUP_EXCHANGE.md](GROUP_EXCHANGE.md).

Le consentement local ne prouve pas que l'autre appareil accepte l'adhésion. L'échange vérifie aussi l'identité distante par TLS et le certificat explicitement approuvé localement.

## Contrats de messages v2

Le code de référence se trouve dans `packages/protocol`. Les messages sont indépendants des modèles métier et des fichiers JSON locaux de latence.

| Champ d'enveloppe | Règle |
| --- | --- |
| `version` | `2` uniquement ; la v1 historique est refusée. |
| `kind` | `hello`, `traffic_observation` ou `complete`. Aucun ordre d'exécution réseau privilégiée n'est défini. |
| `group_id` | Identifiant explicite, sans espace ni caractère de contrôle, au plus 128 octets. |
| `sender_id` | Empreinte `ed25519:` et 64 chiffres hexadécimaux minuscules. |
| `sequence` | Entier de 1 à `2^53-1`, pour préserver l'interopérabilité des nombres JSON. |
| `hello`, `observation` | Un seul corps pour hello/observation ; aucun pour complete. |

`hello` annonce un nom (128 octets maximum), le système, les rôles et les capacités déclarées, ainsi que `share_observations`, le choix du seul expéditeur pour cet échange. Ce champ ne donne aucune permission au destinataire. Les rôles/capacités inconnus ou dupliqués sont refusés. La conversion vers `core.Device` se fait dans `apps/agent/internal/group`, où les règles métier sont aussi appliquées : par exemple, la capacité de gestion du trafic de passerelle exige le rôle correspondant. Ces annonces restent des déclarations, pas une preuve de capacité matérielle.

`traffic_observation` contient :

- `observed_at` : horodatage non nul ; sa présence ne garantit pas une horloge synchronisée ;
- `source: "linux_proc_net_dev"` et `scope: "process_network_namespace"` pour cette première version ;
- `window_ms` : durée positive, au plus 60 000 millisecondes ;
- au plus 128 interfaces distinctes, avec leur nom, leur état et leurs différences d'octets.

Les différences d'octets sont des chaînes décimales canoniques de `uint64`, pour conserver les grandes valeurs dans les clients JSON. Pour une interface `measured`, les deux valeurs sont requises, y compris `"0"`. Pour `appeared`, `disappeared` ou `counters_reset`, elles sont `null`. Les listes de capacités ou d'interfaces absentes/nulles sont interprétées comme vides, sans permission ou mesure implicite.

Les objets utilisent les noms de champs ASCII minuscules définis par les contrats, avec `_` comme séparateur. Le décodeur refuse les champs inconnus, doublons, variantes de casse ou alias Unicode, UTF-8 brut invalide, données supplémentaires et profondeurs dépassant 16 niveaux. Chaque message est limité à 64 Kio. Ces vérifications évitent notamment certaines permissivités d'[encoding/json](https://pkg.go.dev/encoding/json) ; elles ne réalisent pas une authentification.

## Session et authentification

`protocol.NewSession` reçoit un groupe choisi localement et l'identifiant d'un pair **déjà authentifié et approuvé par le transport**. Ces valeurs attendues ne doivent jamais être reprises du premier message reçu.

Le validateur impose `hello` en séquence 1, exactement une observation si le partage a été annoncé (aucune sinon), puis `complete`. Les séquences sont strictement consécutives, avec groupe et expéditeur identiques au contexte de session. Une fin prématurée, une deuxième observation et tout message après la fin sont refusés. Une trame refusée n'avance pas le compteur. Une instance appartient à une seule connexion et son utilisation doit être sérialisée. Cela vérifie l'ordre et la liaison au contexte ; cela ne prouve pas la possession d'une clé ni la fraîcheur d'une mesure entre sessions.

L'étape 3.4 utilise **TLS 1.3 avec authentification mutuelle**, via [crypto/tls](https://pkg.go.dev/crypto/tls#Config), sur des adresses numériques explicitement choisies :

1. Les certificats publics et empreintes sont approuvés avant la connexion ; aucune confiance automatique liée au Wi-Fi ou au nom du PC.
2. Les certificats sont vérifiés dans les deux sens avec les mécanismes TLS standards. Le serveur exige un certificat client vérifié. Les seules ancres de confiance sont les certificats approuvés.
3. Le certificat exact et l'empreinte de sa clé authentifiée sont comparés à l'approbation locale avant de construire la session. Le nom TLS est lié à l'empreinte et l'ALPN est `coopace-group/2`.
4. Le consentement, le groupe et le droit de partage sont vérifiés avant la collecte et l'envoi. Une modification du profil interrompt la connexion lors de sa détection ; les données déjà transmises ne peuvent pas être rappelées.
5. Le cadrage utilise une longueur de quatre octets en ordre réseau, contrôlée avant allocation, puis un JSON limité à 64 Kio. L'ensemble de l'attente et de l'échange est limité à 30 secondes.
6. Les messages invalides ferment la connexion. Une réussite comprend les messages de fin dans les deux sens, puis la fermeture de la connexion sous-jacente ; aucun service de groupe permanent n'est lancé.

Les messages ne sont pas signés avec un mécanisme JSON spécifique à Coopace : l'authentification et le chiffrement relèvent de TLS. Les clés Ed25519 servent à l'identité/signature. Un processus en écoute n'est pas un chef des décisions coopératives. Le renouvellement des certificats, la découverte et les groupes à plusieurs pairs restent à développer.

## Plateformes et validation

Le stockage persistant de clé est activé sous Linux seulement. Sous Windows, les [bits de mode Go ne définissent pas les ACL](https://pkg.go.dev/os#Chmod) ; la commande refuse donc ce stockage avant toute création de clé. Un adaptateur natif de stockage protégé doit être développé et testé avant d'activer cette fonction. Cela limite le prototype actuel, pas les plateformes visées par le produit final. Les contraintes du stockage et des clés Android restent aussi à étudier.

Les tests couvrent la stabilité d'identité, le lien clé publique/identifiant, les permissions, clés corrompues et liens symboliques, le consentement, les messages ambigus/invalides et l'ordre des sessions. Le décodeur a aussi été soumis à des essais aléatoires sans plantage observé. La compilation et l'analyse statique passent pour Linux et Windows amd64 ; cela ne valide pas le stockage Windows. Les négociations TLS réelles en mémoire, les quatre choix de partage et la révocation passent les tests. Le test TCP en boucle locale reste à confirmer depuis le terminal utilisateur ; voir la [portée des vérifications](GROUP_EXCHANGE.md#périmètre-et-validation).

La [procédure du premier échange authentifié](GROUP_EXCHANGE.md) permet de reproduire l'essai avec deux états distincts sur un PC Linux.
