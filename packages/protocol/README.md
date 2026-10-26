# Protocole de communication

État : contrats v2, encodage/décodage stricts, cadrage borné et validation de session implémentés à l'étape 3.4. Le transport TLS est assemblé par l'agent ; ce paquet n'ouvre aucune socket.

Ce module définit les premières annonces d'appareil (`hello`) et observations de compteurs (`traffic_observation`), puis une fin (`complete`). Il ne définit aucun ordre d'exécution ou de modification du réseau.

Le format réseau est JSON v2, avec des messages limités à 64 Kio. Les champs inconnus, doublons, variantes de casse et structures invalides sont rejetés. Les compteurs sont des chaînes décimales de `uint64` et les valeurs indisponibles restent nulles. Les contrats restent indépendants du langage pour préparer l'interopérabilité Kotlin.

`Session` vérifie le groupe, l'expéditeur attendu et les séquences consécutives, avec un unique `hello` initial qui annonce le choix de partage de l'expéditeur. Une seule observation est exigée si annoncée, interdite sinon ; `complete` termine la session et interdit les messages suivants. Il exige que l'appelant fournisse une identité de pair déjà authentifiée et approuvée ; il ne réalise aucune cryptographie, admission ou connexion par lui-même.

Les conversions vers le noyau métier restent à la frontière applicative. `ReadFrame`/`WriteFrame` utilisent un préfixe de longueur de quatre octets en ordre réseau ; la longueur est contrôlée avant allocation et les écritures partielles sont prises en charge. Le transport applique les délais. La v1 historique n'est plus acceptée ; l'export local de latence garde sa version indépendante.

Les [contrats et identités](../../docs/IDENTITY_AND_GROUP.md) et la [procédure TLS](../../docs/GROUP_EXCHANGE.md) décrivent les limites et la validation.
