# Coopace

Coopace vise à améliorer la latence sous charge et le partage de la connexion Internet d'un foyer, grâce à une passerelle et à des agents coopératifs facultatifs.

Le produit est organisé dans un dépôt Git unique, dans le dossier `coopace`.

Le [périmètre produit](docs/PRODUCT.md) décrit le résultat visé, l'état réel de chaque composant et les critères nécessaires pour démontrer un bénéfice réseau.

## État du projet

**Étape 4.2 en cours : premier laboratoire Linux validé en ICMP et TCP.** La commande dédiée `coopace-gateway inspect` inventorie les informations visibles et leurs limites, sans intervention réseau. L'agent conserve l'échange TLS de l'étape 3.4, testé en mémoire ; son essai TCP réel reste à confirmer. Les exécutables compilent pour Windows ; le diagnostic, les compteurs et le stockage privé d'identité Windows restent à implémenter, et l'exécution native à valider. Aucun moteur de gestion du trafic ni gain d'optimisation réseau n'est démontré.

Les [choix techniques](docs/TECH_STACK.md) détaillent les raisons, les limites et les décisions différées.

La [revue du démarrage du 26 octobre 2026](docs/REVIEW_2026-10-26.md) consigne le bilan avant l'étape 4.1. Le [diagnostic de passerelle](docs/GATEWAY_DIAGNOSTIC.md) prépare désormais le scénario de laboratoire, les mesures de référence et la restauration.

La [préparation de l’étape 4.2](docs/GATEWAY_BASELINE.md) ajoute `coopace-gateway inspect --json` et un modèle d’expérience. Un premier scénario Linux virtuel est validé ; la plateforme du foyer, la topologie réelle et les mesures de référence restent à confirmer avant de clôturer cette étape.

Un [laboratoire Linux virtuel](docs/VIRTUAL_LAB.md) prépare désormais un scénario client → passerelle → serveur, sans raccorder le réseau du foyer. `sh scripts/lab-network.sh plan` permet de le prévisualiser ; `run-tcp` prépare cinq mesures d'établissement TCP vers une cible temporaire bornée. Le cycle de vie est testé avec des outils simulés. Un [premier essai natif du 29 octobre](docs/VALIDATION_VIRTUAL_LAB_2026-10-29.md) confirme les contrôles ICMP, cinq connexions TCP réussies sans échec et le nettoyage normal, sans charge de saturation.

La [revue du 29 octobre 2026](docs/REVIEW_2026-10-29.md) revérifie le socle et consigne le correctif de nettoyage après interruption apporté avant ces essais natifs.

La préparation des essais sous charge ajoute un [transfert synthétique borné](docs/VIRTUAL_LOAD.md) : `run-load` envoie 8 Mio avec un plafond moyen applicatif de 1 Mio/s et exige la réception complète avant nettoyage. Ses tests simulés passent et un [premier transfert natif](docs/VALIDATION_VIRTUAL_LOAD_2026-10-29.md) a envoyé et reçu les 8 Mio en environ huit secondes, avec nettoyage normal. Les séries de latence simultanées restent à effectuer ; le compte rendu précise les pièces conservées et manquantes.

## Organisation

```text
coopace/
├── apps/
│   ├── gateway/          # Application passerelle et application des politiques
│   ├── agent/            # Application des appareils participants
│   └── dashboard/        # Interface de contrôle
├── packages/
│   ├── core/             # Règles et modèles indépendants du système
│   └── protocol/         # Contrats de communication entre composants
├── platforms/
│   ├── linux/            # Intégrations Linux et, selon compatibilité, OpenWrt
│   ├── windows/          # Intégrations Windows
│   └── android/          # Intégrations Android pour l'agent
├── scripts/              # Installation locale de Go et commandes de développement
├── internal/strictjson/  # Contrôles JSON partagés, privés au module Go
├── ml/                   # Futur module ML : recherche, entraînement et évaluation
└── docs/                 # Architecture, progression et procédures
    └── README.md         # Index de la documentation
```

Chaque composant majeur contient un README qui définit sa responsabilité et son état. Le code Go utilise un seul module à la racine (`go.mod`), avec plusieurs paquets organisés par responsabilité. L'[index de documentation](docs/README.md) guide la lecture des décisions et des procédures.

Le [module ML](ml/README.md) est réservé pour un développement ultérieur. Il reste facultatif et indépendant du fonctionnement de base.

Les applications assemblent les composants ; le noyau métier reste indépendant des systèmes. Les [règles de dépendance](docs/ARCHITECTURE.md#règles-de-dépendance-et-de-rangement) précisent où placer les prochaines fonctionnalités.

## Principes

- Une passerelle ne gère que le trafic qui passe effectivement par elle.
- Un appareil participant installe un agent compatible avec son système et rejoint le groupe avec consentement.
- Un appareil sans agent peut bénéficier de la gestion du trafic par la passerelle.
- Linux n'est pas obligatoire parmi les participants. Une passerelle Windows est une cible à étudier et à valider ; le rapport propose d'abord Linux/OpenWrt avec CAKE/SQM.
- Les optimisations doivent être mesurables, bornées et réversibles, sans déchiffrement des contenus.
- Les relais et le ML seront évalués après la validation du socle.

Voir l'[architecture](docs/ARCHITECTURE.md) et la [progression prévue](docs/ROADMAP.md).

## Développement

Sous Linux x86_64, préparer le SDK local puis lancer l'agent et les tests :

```sh
sh scripts/setup-go.sh
sh scripts/go.sh run ./apps/agent/cmd/coopace status
sh scripts/go.sh run ./apps/agent/cmd/coopace observe
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
sh scripts/go.sh test ./...
```

Les [instructions de développement](docs/DEVELOPMENT.md) détaillent l'installation, la compilation du binaire, l'aide et les vérifications. Les [observations locales](docs/OBSERVATIONS.md) précisent les sources, les unités et les limites. La [procédure Windows](docs/WINDOWS_VALIDATION.md) décrit la compilation et les essais natifs encore à effectuer. L'application Android reste à développer.

La [mesure TCP et le protocole de référence](docs/LATENCY.md) expliquent `coopace latency --target IP:port`, l'export JSON et les comparaisons au repos/sous charge.

`coopace latency compare --idle FICHIER --loaded FICHIER` compare désormais deux rapports TCP locaux, sans lancer de mesure. Il affiche des différences descriptives et conserve les valeurs indisponibles ; les séries réelles au repos/sous charge restent à recueillir.

L'[identité locale et les contrats du groupe](docs/IDENTITY_AND_GROUP.md) décrivent les permissions et les messages. La [procédure du premier échange TLS](docs/GROUP_EXCHANGE.md) explique comment tester deux instances sur un PC Linux avec `identity export-cert` et `group configure/listen/exchange/revoke`. Les compteurs et le stockage privé Windows restent indisponibles.

Le dépôt Git est propre à ce dossier et utilise la branche `main`. La commande `git remote -v` permet de consulter les dépôts distants configurés dans chaque copie locale.
