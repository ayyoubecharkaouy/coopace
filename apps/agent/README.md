# Application agent

État : première commande locale implémentée et validée sous Linux à l'étape 2.3. L'adhésion au groupe et les fonctions réseau restent à développer.

L'agent permettra à un appareil volontaire de rejoindre le groupe, d'annoncer ses capacités et de partager les mesures locales autorisées. Les plateformes visées sont Linux, Windows et Android, avec des fonctions dépendant de leurs possibilités réelles.

Ce répertoire définit le rôle applicatif de l'agent. Le premier programme Linux/Windows est développé en Go, avec une commande locale `coopace status`. Les intégrations réseau propres aux systèmes appartiennent à `platforms/`.

## Organisation actuelle

```text
agent/
├── cmd/coopace/main.go   # Point d'entrée et version de l'exécutable
└── internal/
    ├── cli/             # Commandes, affichage et codes de sortie
    └── status/          # État local et détection de la plateforme de l'exécutable
```

La détection commune utilise le système et l'architecture fournis par Go. Elle réutilise les types de plateforme et de rôle du noyau. Elle ne crée pas de fausse identité d'appareil pour satisfaire le modèle `Device` : l'identité persistante sera définie avec l'adhésion au groupe.

## Lancement

Depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/agent/cmd/coopace status
sh scripts/go.sh run ./apps/agent/cmd/coopace --help
```

La version affichée est `dev`. Le statut décrit l'exécution locale, avec le rôle `agent` et l'état hors groupe. La commande se termine après l'affichage ; elle ne lance pas de service en arrière-plan et ne mesure pas la connexion Internet.

Le binaire accepte `status`, `help`, `--help` et `-h`. Sans argument, il affiche l'aide. Les codes de sortie du binaire sont : `0` pour une réussite, `1` pour une erreur d'exécution ou d'affichage, `2` pour des arguments invalides.

La compilation et les instructions détaillées sont dans [DEVELOPMENT.md](../../docs/DEVELOPMENT.md). Le lancement réel sous Windows reste à vérifier.

L'intégration Android utilisera Kotlin. Ses points d'entrée et le packaging mobile ou bureau restent à préciser selon les [choix techniques](../../docs/TECH_STACK.md).

La participation au groupe ne rend pas automatiquement l'appareil relais. Cette fonction demandera un consentement distinct et une prise en charge technique validée.
