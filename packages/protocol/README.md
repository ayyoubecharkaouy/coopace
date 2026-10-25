# Protocole de communication

État : module prévu, sans implémentation.

Ce module accueillera les contrats versionnés et les règles de validation des échanges : identité, adhésion, capacités, mesures, propositions et résultats d'actions.

Le format retenu est JSON, avec versionnement explicite des futurs messages et encodage Go via la bibliothèque standard. Les contrats resteront indépendants du langage pour permettre leur utilisation depuis Kotlin.

Les champs des messages, le transport, la découverte et l'authentification restent à spécifier. Les exemples et schémas devront permettre l'interopérabilité entre les implémentations des différentes plateformes.
