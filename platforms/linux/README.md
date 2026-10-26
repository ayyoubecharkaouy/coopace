# Adaptation Linux

État : compteurs d'interfaces de l'étape 3.1 et inventaire de passerelle de l'étape 4.1 implémentés. Modification des files et du routage non implémentée.

`ReadTrafficCounters()` lit les compteurs d'octets RX/TX de `/proc/net/dev` dans l'espace réseau courant. Le décodeur est testé avec des données contrôlées, notamment les compteurs élevés, données tronquées et erreurs de lecture. Les modèles retournés appartiennent au noyau ; le calcul des taux y reste indépendant de Linux.

Cette adaptation fournira progressivement les autres mesures et opérations réseau Linux nécessaires à l'agent et à la passerelle. L'intégration de `tc`, CAKE/SQM et des mécanismes de routage exigera une vérification des capacités et permissions.

La source, les unités et les limites sont décrites dans [OBSERVATIONS.md](../../docs/OBSERVATIONS.md).

Le support OpenWrt dépendra du matériel, des paquets disponibles et du packaging retenu. Les changements réseau devront être réversibles.

`InspectGateway(ctx)` inventorie en lecture seule les interfaces visibles, les flags de forwarding, la capacité effective `CAP_NET_ADMIN`, les outils `ip`/`tc`/`nft`, les routes par défaut et les files annoncées par `tc`. Les requêtes externes ont des arguments fixes, un délai et des limites de sortie ; `nft` est seulement recherché. Les parseurs utilisent des données de test, et les informations manquantes restent explicites.

Le [diagnostic de passerelle](../../docs/GATEWAY_DIAGNOSTIC.md) détaille les sources et les limites. Cet inventaire ne vérifie pas la couverture du foyer ni la restauration et ne sélectionne pas de WAN.

Les fichiers sont regroupés par fonction : `traffic*.go` pour les compteurs, `gateway*.go` pour l'inventaire. Pour ce dernier, [gateway.go](gateway.go) orchestre la collecte, [gateway_parse.go](gateway_parse.go) décode les données sans I/O et [gateway_linux.go](gateway_linux.go) contient les lectures natives et commandes bornées. Les tests de parseurs, de collecte et de processus externes sont séparés dans les fichiers correspondants.
