# Protocole de communication

État : contrats v1, encodage/décodage stricts et validation de session implémentés à l'étape 3.3. Transport TLS et échanges réseau non implémentés.

Ce module définit les premières annonces d'appareil (`hello`) et observations de compteurs (`traffic_observation`). Il ne définit aucun ordre d'exécution ou de modification du réseau.

Le format est JSON v1, avec des messages limités à 64 Kio. Les champs inconnus, doublons, variantes de casse et structures invalides sont rejetés. Les compteurs sont des chaînes décimales de `uint64` et les valeurs indisponibles restent nulles. Les contrats restent indépendants du langage pour préparer l'interopérabilité Kotlin.

`Session` vérifie le groupe, l'expéditeur attendu et les séquences consécutives, avec un unique `hello` initial. Il exige que l'appelant fournisse une identité de pair déjà authentifiée et approuvée ; il ne réalise aucune cryptographie, admission ou connexion par lui-même.

Les conversions vers le noyau métier restent à la frontière applicative. Les détails des contrats, de l'identité et du futur TLS mutuel sont dans [IDENTITY_AND_GROUP.md](../../docs/IDENTITY_AND_GROUP.md).
