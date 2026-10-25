# Application agent

État : commandes locales, compteurs Linux et mesure d'établissement TCP implémentés jusqu'à l'étape 3.2. La connexion TCP en boucle locale est validée sous Linux. Le programme compile pour Windows amd64, avec compteurs d'interfaces indisponibles et exécution native non vérifiée sur cette cible. L'adhésion au groupe et les interventions réseau restent à développer.

L'agent permettra à un appareil volontaire de rejoindre le groupe, d'annoncer ses capacités et de partager les mesures locales autorisées. Les plateformes visées sont Linux, Windows et Android, avec des fonctions dépendant de leurs possibilités réelles.

Ce répertoire définit le rôle applicatif de l'agent. Le premier programme Linux/Windows est développé en Go, avec une commande locale `coopace status`. Les intégrations réseau propres aux systèmes appartiennent à `platforms/`.

## Organisation actuelle

```text
agent/
├── cmd/coopace/main.go   # Point d'entrée et version de l'exécutable
└── internal/
    ├── cli/             # Commandes, affichage et codes de sortie
    ├── status/          # État local et détection de la plateforme de l'exécutable
    ├── observe/         # Deux lectures de compteurs et durée mesurée
    └── latency/         # Connexions TCP, série de mesures et export JSON local
```

La détection commune utilise le système et l'architecture fournis par Go. Elle réutilise les types de plateforme et de rôle du noyau. Elle ne crée pas de fausse identité d'appareil pour satisfaire le modèle `Device` : l'identité persistante sera définie avec l'adhésion au groupe.

## Lancement

Depuis la racine du dépôt :

```sh
sh scripts/go.sh run ./apps/agent/cmd/coopace status
sh scripts/go.sh run ./apps/agent/cmd/coopace observe
sh scripts/go.sh run ./apps/agent/cmd/coopace --help
sh scripts/go.sh run ./apps/agent/cmd/coopace latency --help
```

La version affichée par `status` est `dev`. Le statut décrit l'exécution locale, avec le rôle `agent` et l'état hors groupe. Les commandes se terminent après l'affichage et ne lancent pas de service en arrière-plan. Sous Linux, `observe` affiche des taux d'octets par interface : voir la [provenance et les limites](../../docs/OBSERVATIONS.md).

Le binaire accepte `status`, `observe`, `latency`, `help`, `--help` et `-h`. Sans argument, il affiche l'aide. Les codes de sortie du binaire sont : `0` pour une réussite, `1` pour une erreur d'exécution, d'affichage ou de collecte indisponible, `2` pour des arguments invalides. Pour `latency`, `0` signifie au moins une connexion réussie, `1` inclut une série sans réussite et `130` une annulation par Ctrl+C.

La commande `latency` exige une cible IP:port et réalise des connexions actives, sans envoyer de données applicatives. Elle distingue les échecs des durées calculables et peut émettre un JSON local versionné. La méthode, les limites et les conditions de référence sont décrites dans [LATENCY.md](../../docs/LATENCY.md).

La compilation et les instructions détaillées sont dans [DEVELOPMENT.md](../../docs/DEVELOPMENT.md). Le binaire Windows x64 et les essais natifs restant à effectuer sont décrits dans [WINDOWS_VALIDATION.md](../../docs/WINDOWS_VALIDATION.md).

L'intégration Android utilisera Kotlin. Ses points d'entrée et le packaging mobile ou bureau restent à préciser selon les [choix techniques](../../docs/TECH_STACK.md).

La participation au groupe ne rend pas automatiquement l'appareil relais. Cette fonction demandera un consentement distinct et une prise en charge technique validée.
