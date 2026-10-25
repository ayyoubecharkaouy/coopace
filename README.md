# Coopace

Coopace vise à améliorer la latence sous charge et le partage de la connexion Internet d'un foyer, grâce à une passerelle et à des agents coopératifs facultatifs.

Le produit est organisé dans un dépôt Git unique, dans le dossier `coopace`.

Le [périmètre produit](docs/PRODUCT.md) décrit le résultat visé, l'état réel de chaque composant et les critères nécessaires pour démontrer un bénéfice réseau.

## État du projet

**Étape 3.1 terminée sous Linux : premières observations locales en lecture seule.** `coopace status` affiche l'état local et `coopace observe` mesure le trafic reçu/envoyé par interface pendant environ une seconde. Ces compteurs ne mesurent pas la capacité Internet. Les tests passent sous Linux et le programme compile pour Windows ; l'observation des compteurs Windows n'est pas encore implémentée et l'exécution native Windows reste à vérifier.

Les [choix techniques](docs/TECH_STACK.md) détaillent les raisons, les limites et les décisions différées.

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
├── ml/                   # Futur module ML : recherche, entraînement et évaluation
└── docs/
    ├── ARCHITECTURE.md
    ├── DEVELOPMENT.md
    ├── OBSERVATIONS.md
    ├── PRODUCT.md
    ├── ROADMAP.md
    ├── TECH_STACK.md
    └── WINDOWS_VALIDATION.md
```

Chaque répertoire de module contient un README qui définit sa responsabilité et son état.

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
sh scripts/go.sh test ./...
```

Les [instructions de développement](docs/DEVELOPMENT.md) détaillent l'installation, la compilation du binaire, l'aide et les vérifications. Les [observations locales](docs/OBSERVATIONS.md) précisent les sources, les unités et les limites. La [procédure Windows](docs/WINDOWS_VALIDATION.md) décrit la compilation et les essais natifs encore à effectuer. L'application Android reste à développer.

Le dépôt Git est propre à ce dossier et utilise la branche `main`. La commande `git remote -v` permet de consulter les dépôts distants configurés dans chaque copie locale.
