# Application passerelle

État : module prévu, sans implémentation.

Cette application pilotera l'observation et la gestion du trafic qui traverse réellement la machine passerelle. Elle utilisera les règles du noyau et l'adaptation du système pour appliquer des politiques autorisées, en évaluer les effets et restaurer la configuration.

Le moteur réseau dépendra du système : CAKE/SQM est envisagé sous Linux ; une passerelle Windows exige une intégration et une validation spécifiques. Les privilèges et leur séparation restent à définir.
