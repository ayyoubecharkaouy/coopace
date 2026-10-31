# Adaptation Linux

État : compteurs d’interfaces, inventaire de passerelle et catalogue/validateurs CAKE purs implémentés. Modification des files et du routage non implémentée.

`ReadTrafficCounters()` lit les compteurs d'octets RX/TX de `/proc/net/dev` dans l'espace réseau courant. Le décodeur est testé avec des données contrôlées, notamment les compteurs élevés, données tronquées et erreurs de lecture. Les modèles retournés appartiennent au noyau ; le calcul des taux y reste indépendant de Linux.

Cette adaptation fournira progressivement les autres mesures et opérations réseau Linux nécessaires à l'agent et à la passerelle. `tc` est déjà utilisé pour lire les files dans le diagnostic ; leur modification, CAKE/SQM et le pilotage du routage restent à intégrer avec vérification des capacités et permissions.

La source, les unités et les limites sont décrites dans [OBSERVATIONS.md](../../docs/OBSERVATIONS.md).

Le support OpenWrt dépendra du matériel, des paquets disponibles et du packaging retenu. Les changements réseau devront être réversibles.

`InspectGateway(ctx)` inventorie en lecture seule les interfaces visibles, les flags de forwarding, la capacité effective `CAP_NET_ADMIN`, les outils `ip`/`tc`/`nft`, les routes par défaut et les files annoncées par `tc`. Les requêtes externes ont des arguments fixes, un délai et des limites de sortie ; `nft` est seulement recherché. Les parseurs utilisent des données de test, et les informations manquantes restent explicites.

Le [diagnostic de passerelle](../../docs/GATEWAY_DIAGNOSTIC.md) détaille les sources et les limites. Cet inventaire ne vérifie pas la couverture du foyer ni la restauration et ne sélectionne pas de WAN.

Les fichiers sont regroupés par fonction : `traffic*.go` pour les compteurs, `gateway*.go` pour l'inventaire. Pour ce dernier, [gateway.go](gateway.go) orchestre la collecte, [gateway_parse.go](gateway_parse.go) décode les données sans I/O et [gateway_linux.go](gateway_linux.go) contient les lectures natives et commandes bornées. Les tests de parseurs, de collecte et de processus externes sont séparés dans les fichiers correspondants.

Le [catalogue et les validateurs CAKE Go](../../docs/CAKE_GO_VALIDATION.md) sont dans `cake.go`, `cake_parse.go` et `cake_stats.go`, avec leurs tests dans `cake_test.go`. Ils résolvent le profil fixe du laboratoire et valident des relevés fournis : producteur, options, statistiques uint64 et champs indisponibles. Ils ne lancent aucun outil. Deux fixtures natives de référence sont conservées dans `testdata/cake`, avec provenance ; le [contexte de session](../../docs/LAB_CAKE_CONTEXT.md) est maintenant implémenté, tandis que l’application du profil reste à développer.

`namespace*.go` expose `InspectNetworkNamespaceDescriptor` pour lire type et identité d’un descripteur emprunté, sans attester sa propriété. `VerifyLabNamespace` vérifie en lecture seule ces descripteurs, ainsi que leur cohérence avec l’espace courant et leur différence avec l’origine du superviseur. Le premier backend est limité à Linux amd64 et n’effectue aucun changement d’espace ; les autres cibles refusent l’opération. L’attestation de propriété et la transmission des descripteurs restent à raccorder au superviseur.
