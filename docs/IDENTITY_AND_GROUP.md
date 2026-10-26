# Identité et contrats du groupe — étape 3.3

## Périmètre livré

Cette étape fournit une identité locale persistante sous Linux, un modèle de consentement, deux contrats JSON de groupe et un validateur de session hors réseau. Elle définit le transport authentifié à intégrer à l'étape 3.4. Aucune commande ne crée, découvre ou rejoint encore un groupe, et aucune session TLS n'est ouverte à cette étape.

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

Les permissions sont fausses par défaut. Partage et relais exigent le consentement à rejoindre ; rejoindre seul n'autorise pas les autres usages. `AllowsObservationSharing` vérifie aussi le groupe et l'identifiant de l'appareil. Ce modèle n'est pas encore persisté ni exposé par une commande d'adhésion : cette activation sera intégrée à l'étape 3.4.

Le consentement local ne prouve pas que l'autre appareil accepte l'adhésion. La future admission devra également vérifier l'identité distante et la politique locale d'approbation des pairs.

## Contrats de messages v1

Le code de référence se trouve dans `packages/protocol`. Les messages sont indépendants des modèles métier et des fichiers JSON locaux de latence.

| Champ d'enveloppe | Règle |
| --- | --- |
| `version` | `1` uniquement. |
| `kind` | `hello` ou `traffic_observation`. Aucun ordre d'exécution réseau privilégiée n'est défini. |
| `group_id` | Identifiant explicite, sans espace ni caractère de contrôle, au plus 128 octets. |
| `sender_id` | Empreinte `ed25519:` et 64 chiffres hexadécimaux minuscules. |
| `sequence` | Entier de 1 à `2^53-1`, pour préserver l'interopérabilité des nombres JSON. |
| `hello`, `observation` | Un seul corps, correspondant exactement au type du message. |

`hello` annonce un nom (128 octets maximum), le système, les rôles et les capacités déclarées. Les rôles/capacités inconnus ou dupliqués sont refusés. La conversion vers `core.Device` se fait dans `apps/agent/internal/group`, où les règles métier sont aussi appliquées : par exemple, la capacité de gestion du trafic de passerelle exige le rôle correspondant. Ces annonces restent des déclarations, pas une preuve de capacité matérielle.

`traffic_observation` contient :

- `observed_at` : horodatage non nul ; sa présence ne garantit pas une horloge synchronisée ;
- `source: "linux_proc_net_dev"` et `scope: "process_network_namespace"` pour cette première version ;
- `window_ms` : durée positive, au plus 60 000 millisecondes ;
- au plus 128 interfaces distinctes, avec leur nom, leur état et leurs différences d'octets.

Les différences d'octets sont des chaînes décimales canoniques de `uint64`, pour conserver les grandes valeurs dans les clients JSON. Pour une interface `measured`, les deux valeurs sont requises, y compris `"0"`. Pour `appeared`, `disappeared` ou `counters_reset`, elles sont `null`. Les listes de capacités ou d'interfaces absentes/nulles sont interprétées comme vides, sans permission ou mesure implicite.

Les objets utilisent les noms de champs ASCII minuscules définis par les contrats, avec `_` comme séparateur. Le décodeur refuse les champs inconnus, doublons, variantes de casse ou alias Unicode, UTF-8 brut invalide, données supplémentaires et profondeurs dépassant 16 niveaux. Chaque message est limité à 64 Kio. Ces vérifications évitent notamment certaines permissivités d'[encoding/json](https://pkg.go.dev/encoding/json) ; elles ne réalisent pas une authentification.

## Session et authentification prévue

`protocol.NewSession` reçoit un groupe choisi localement et l'identifiant d'un pair **déjà authentifié et approuvé par le transport**. Ces valeurs attendues ne doivent jamais être reprises du premier message reçu.

Le validateur impose `hello` en séquence 1, puis des observations en séquences strictement consécutives, avec groupe et expéditeur identiques au contexte de session. Une trame refusée n'avance pas le compteur. Une instance appartient à une seule connexion et son utilisation doit être sérialisée. Cela vérifie l'ordre et la liaison au contexte ; cela ne prouve pas la possession d'une clé ni la fraîcheur d'une mesure entre sessions.

Le choix pour l'étape 3.4 est **TLS 1.3 avec authentification mutuelle**, via [crypto/tls](https://pkg.go.dev/crypto/tls#Config), sur des adresses explicitement configurées pour le premier essai. La mise en œuvre devra :

1. Faire approuver les empreintes publiques par un moyen distinct de la connexion inconnue, puis enregistrer les pairs autorisés pour le groupe ; aucune confiance automatique liée au Wi-Fi ou au nom du PC.
2. Vérifier les certificats dans les deux sens avec les mécanismes TLS standards et exiger un certificat client vérifié ; une désactivation générale de la vérification n'est pas une authentification.
3. Calculer l'identifiant depuis la clé publique authentifiée et le comparer à l'approbation locale avant de construire le validateur de session.
4. Vérifier consentement, appartenance et droit de partage avant tout envoi de mesure ; le protocole ne peut pas s'accorder ces permissions lui-même.
5. Encadrer chaque JSON par une longueur de 4 octets en ordre réseau, vérifier la limite avant allocation, et imposer des délais de connexion/lecture. Ce transport et ce cadrage ne sont pas encore implémentés.
6. Fermer/refuser une session invalide ou révoquée et garder l'état hors groupe tant que l'admission n'est pas complète.

Les messages ne sont pas signés avec un mécanisme JSON spécifique à Coopace : l'authentification et le chiffrement relèveront de TLS. Les clés Ed25519 servent à l'identité/signature, pas à une nouvelle méthode de chiffrement de contenus. Un premier processus en écoute ne deviendra pas pour autant le chef des décisions coopératives.

## Plateformes et validation

Le stockage persistant de clé est activé sous Linux seulement. Sous Windows, les [bits de mode Go ne définissent pas les ACL](https://pkg.go.dev/os#Chmod) ; la commande refuse donc ce stockage avant toute création de clé. Un adaptateur natif de stockage protégé doit être développé et testé avant d'activer cette fonction. Cela limite le prototype actuel, pas les plateformes visées par le produit final. Les contraintes du stockage et des clés Android restent aussi à étudier.

Les tests couvrent la stabilité d'identité, le lien clé publique/identifiant, les permissions, clés corrompues et liens symboliques, le consentement, les messages ambigus/invalides et l'ordre des sessions. Le décodeur a aussi été soumis à des essais aléatoires sans plantage observé. La compilation et l'analyse statique passent pour Linux et Windows amd64 ; cela ne valide ni un stockage Windows ni un échange TLS réel.

La suite est le [premier échange authentifié entre deux instances](ROADMAP.md#34--premier-échange-entre-deux-instances), après intégration du stockage d'admission et du transport.
