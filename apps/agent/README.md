# Application agent

État : module prévu, sans implémentation.

L'agent permettra à un appareil volontaire de rejoindre le groupe, d'annoncer ses capacités et de partager les mesures locales autorisées. Les plateformes visées sont Linux, Windows et Android, avec des fonctions dépendant de leurs possibilités réelles.

Ce répertoire définit le rôle applicatif de l'agent. Le premier programme Linux/Windows sera développé en Go, avec une commande locale `coopace status`. Les intégrations propres aux systèmes appartiennent à `platforms/`.

L'intégration Android utilisera Kotlin. Ses points d'entrée et le packaging mobile ou bureau restent à préciser selon les [choix techniques](../../docs/TECH_STACK.md).

La participation au groupe ne rend pas automatiquement l'appareil relais. Cette fonction demandera un consentement distinct et une prise en charge technique validée.
