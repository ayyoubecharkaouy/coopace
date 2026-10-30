# Coopace

Coopace vise à améliorer la latence sous charge et le partage de la connexion Internet d'un foyer, grâce à une passerelle et à des agents coopératifs facultatifs.

Le produit est organisé dans un dépôt Git unique, dans le dossier `coopace`.

Le [périmètre produit](docs/PRODUCT.md) décrit le résultat visé, l'état réel de chaque composant et les critères nécessaires pour démontrer un bénéfice réseau.

## État du projet

**Étape 4.2 en cours : premiers essais natifs du laboratoire Linux validés, gestion des files encore à développer.**

| Partie | État vérifié |
| --- | --- |
| Agent Linux | État local, compteurs, mesure d'établissement TCP, export/comparaison, identité et consentement persistés. |
| Groupe à deux pairs | Échange TLS mutuel testé en mémoire ; [essai TCP réel du groupe](docs/GROUP_EXCHANGE.md) encore à confirmer. |
| Diagnostic passerelle | Lecture seule ; [inventaire complet dans la passerelle virtuelle](docs/VALIDATION_VIRTUAL_LAB_2026-10-29.md), sans validation du réseau du foyer. |
| Transfert et séries synthétiques | [8 Mio transférés](docs/VALIDATION_VIRTUAL_LOAD_2026-10-29.md), puis [trois paires de séries et 60 connexions réussies](docs/VALIDATION_VIRTUAL_SERIES_2026-10-29.md), sans goulot configuré. |
| Superviseur de laboratoire | [Fin normale et mort forcée du pilote validées](docs/VALIDATION_LAB_GUARD_2026-10-29.md) ; intégration aux scénarios de mesure encore à réaliser. |
| Autres plateformes et interfaces | Compilation Windows amd64 vérifiée, exécution native en attente ; Android, tableau de bord et ML non implémentés. |

Le [cycle de vie de la file virtuelle](docs/LAB_QUEUE.md) est implémenté sous le superviseur : création et relecture de TBF à 4 Mbit/s sur un lien désactivé, puis nettoyage après fin normale ou mort forcée du pilote. Les [quatre contrôles natifs](docs/VALIDATION_LAB_QUEUE_2026-10-29.md) sont validés. Les scénarios de mesure existants restent sans file ; les références WAN, la restauration d'une passerelle réelle et tout gain d'optimisation restent à démontrer.

L'[instrumentation du débit reçu et des statistiques TBF](docs/LAB_INSTRUMENTATION.md) est implémentée et [validée en natif](docs/VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) : réception TCP locale avec JSON et statistiques à zéro sur liens TBF désactivés. L'intégration de ces mesures au chemin actif et la campagne avec goulot restent à réaliser.

Le [périmètre produit](docs/PRODUCT.md) détaille les fonctions et limites ; la [feuille de route](docs/ROADMAP.md) fixe les validations restantes. Les protocoles et comptes rendus sont regroupés dans l'[index documentaire](docs/README.md).

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

`coopace latency compare --idle FICHIER --loaded FICHIER` compare deux rapports TCP locaux, sans lancer de mesure. Il affiche des différences descriptives et conserve les valeurs indisponibles. Des séries synthétiques sont validées dans le laboratoire ; les références WAN et les comparaisons après intervention restent à recueillir.

L'[identité locale et les contrats du groupe](docs/IDENTITY_AND_GROUP.md) décrivent les permissions et les messages. La [procédure du premier échange TLS](docs/GROUP_EXCHANGE.md) explique comment tester deux instances sur un PC Linux avec `identity export-cert` et `group configure/listen/exchange/revoke`. Les compteurs et le stockage privé Windows restent indisponibles.

Le dépôt Git est propre à ce dossier et utilise la branche `main`. La commande `git remote -v` permet de consulter les dépôts distants configurés dans chaque copie locale.
