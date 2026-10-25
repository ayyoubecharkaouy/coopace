# Adaptation Linux

État : première lecture de compteurs d'interfaces implémentée à l'étape 3.1. Gestion des files et routage non implémentés.

`ReadTrafficCounters()` lit les compteurs d'octets RX/TX de `/proc/net/dev` dans l'espace réseau courant. Le décodeur est testé avec des données contrôlées, notamment les compteurs élevés, données tronquées et erreurs de lecture. Les modèles retournés appartiennent au noyau ; le calcul des taux y reste indépendant de Linux.

Cette adaptation fournira progressivement les autres mesures et opérations réseau Linux nécessaires à l'agent et à la passerelle. L'intégration de `tc`, CAKE/SQM et des mécanismes de routage exigera une vérification des capacités et permissions.

La source, les unités et les limites sont décrites dans [OBSERVATIONS.md](../../docs/OBSERVATIONS.md).

Le support OpenWrt dépendra du matériel, des paquets disponibles et du packaging retenu. Les changements réseau devront être réversibles.
