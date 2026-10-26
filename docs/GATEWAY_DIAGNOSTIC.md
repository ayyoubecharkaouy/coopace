# Diagnostic de la passerelle — étape 4.1

## Fonction disponible

`coopace-gateway inspect` produit un inventaire local en lecture seule sous Linux. Il aide à préparer le choix du point d'application, des mesures et de la restauration. Il ne configure pas la machine comme routeur et ne sélectionne pas automatiquement une interface WAN.

L'application passerelle possède son propre point d'entrée dans `apps/gateway`, séparé de l'agent `coopace`. Les deux exécutables font partie du même projet et du même module Go ; leur packaging final reste à définir. Ce programme de diagnostic se termine après l'affichage et ne démarre aucun service.

Depuis la racine du dépôt Linux, sans `sudo` :

```sh
sh scripts/go.sh run ./apps/gateway/cmd/coopace-gateway inspect
```

Pour produire un exécutable réutilisable :

```sh
sh scripts/go.sh build -o .local/bin/coopace-gateway ./apps/gateway/cmd/coopace-gateway
./.local/bin/coopace-gateway inspect
./.local/bin/coopace-gateway --help
```

Le code de sortie est `0` pour un rapport produit, même partiel ; `1` pour une erreur globale, une plateforme non prise en charge ou un échec d'affichage ; `2` pour des arguments invalides ; `130` pour une annulation par Ctrl+C. Une rubrique indisponible n'est remplacée ni par `false` ni par une liste vide. `go run` peut présenter les codes de sortie à travers son propre processus.

## Sources et portée

| Information | Source | Interprétation limitée |
| --- | --- | --- |
| Interfaces | `net.Interfaces` : noms, index, MTU, état administratif et boucle locale | Interfaces de l'espace réseau visible ; aucune adresse IP ou MAC n'est ajoutée au rapport. Une interface active administrativement n'est pas une preuve de liaison utilisable. |
| Forwarding IPv4 | `/proc/sys/net/ipv4/ip_forward` | Valeur globale observée ; ne prouve ni le chemin des appareils ni l'autorisation du pare-feu. |
| Forwarding IPv6 global | `/proc/sys/net/ipv6/conf/all/forwarding` | Ne constitue pas un examen complet des réglages par interface. |
| Capacité réseau effective | Champ `CapEff` de `/proc/self/status`, bit `CAP_NET_ADMIN` | Observation du processus, sans essai d'intervention ni conclusion sur tous les droits des commandes exécutées. |
| Outils | Recherche de `ip`, `tc`, `nft` dans `PATH` | Exécutable trouvé, sans installation automatique ni preuve de compatibilité du noyau. `nft` n'est pas exécuté. |
| Routes par défaut IPv4/IPv6 | Requêtes JSON `ip route show`, toutes tables | Inventaire des interfaces et types annoncés, sans calcul du routage effectif pour chaque flux. |
| Files visibles | Requête JSON `tc qdisc show` | Types, interfaces et identifiants ; les options, classes et filtres ne sont pas sauvegardés. |

Les trois seules commandes externes sont :

```text
ip -j -4 route show table all exact default
ip -j -6 route show table all exact default
tc -j qdisc show
```

Elles utilisent des arguments fixes, sans shell ni élévation de privilèges. Chaque commande est limitée à deux secondes ; stdout est limité à 256 Kio et stderr à 4 Kio. Les fichiers lus sont limités à 64 Kio. Le contexte global demande une annulation après huit secondes ; les lectures locales et l'énumération des interfaces n'offrent pas elles-mêmes de délai d'I/O interruptible. Ctrl+C interrompt les commandes actives et empêche les requêtes suivantes.

Les routes conservent leur table, leur type et les interfaces, y compris plusieurs nexthops. Un identifiant de nexthop indirect est indiqué comme non résolu. Les adresses de destination et de prochain saut ne sont pas conservées dans le modèle ni affichées. Les sorties brutes des outils sont traitées en mémoire, sans journal ni fichier automatique.

Les lectures sont successives ; elles ne constituent pas un instantané atomique. Une sortie JSON invalide, tronquée ou trop grande rend la rubrique indisponible. Une liste vide valide signifie seulement qu'aucune entrée n'a été renvoyée pour cette requête.

Les références de ces lectures sont la [bibliothèque réseau Go](https://pkg.go.dev/net#Interfaces), les [réglages IP du noyau](https://docs.kernel.org/networking/ip-sysctl.html), la [définition Linux des capacités](https://github.com/torvalds/linux/blob/master/include/uapi/linux/capability.h), les manuels [ip-route](https://man7.org/linux/man-pages/man8/ip-route.8.html) et [tc](https://man7.org/linux/man-pages/man8/tc.8.html). Les processus bornés utilisent [os/exec](https://pkg.go.dev/os/exec#Cmd.WaitDelay).

## Ce que le résultat ne décide pas

Le diagnostic indique toujours que la couverture du trafic du foyer reste à établir. Une route par défaut ne prouve pas que les autres appareils passent par ce PC. Un VPN peut utiliser des routes plus spécifiques, des règles de routage ou des espaces réseau qui ne sont pas analysés ici. L'absence de route `/0` ne prouve donc pas une coupure Internet.

Le programme ne choisit aucun rôle LAN/WAN, ne mesure pas la capacité Internet et ne conclut pas à une congestion. Il ne vérifie pas le pare-feu, le NAT, le DNS, les ponts, l'offload, la prise en charge de CAKE non utilisé ou les performances de la machine. Une file `cake` visible est une configuration observée, sans preuve que tout le trafic attendu la traverse.

L'inventaire n'est **pas une sauvegarde rejouable** : il ne permet pas de restaurer automatiquement la configuration. Aucun `sysctl`, route, file ou filtre n'est modifié, et aucun paquet de test n'est envoyé vers une cible réseau.

Le stockage d'identité et le groupe ne sont pas utilisés par cette commande. Un participant Linux n'est pas requis dans le produit final ; ce premier adaptateur de diagnostic est Linux. Sous Windows, l'aide compile mais `inspect` retourne explicitement une indisponibilité avec le code `1`. L'adaptateur Windows et son moteur restent à étudier.

## Préparer l'expérience avant toute intervention

La prochaine sous-étape doit consigner ces éléments pour un scénario précis :

| Élément | À définir et vérifier |
| --- | --- |
| Point d'application | Plateforme candidate, schéma des liens, interfaces et chemin réel du trafic de chaque appareil ; vérifier IPv4 et IPv6. |
| Référence initiale | Configuration conservée, versions, commit Git, cible de mesure autorisée, charge utilisée, nombre de répétitions et conditions déclarées au repos/sous charge. |
| Comparaison | Configuration initiale, moteur configuré manuellement, puis pilotage Coopace sans ML. Le moteur de référence dépend du système ; CAKE/SQM reste la référence du rapport pour Linux/OpenWrt. |
| Mesures | Latence sous charge, débit utile, équité, CPU/mémoire, couverture et connectivité. Les mesures TCP existantes sont complémentaires aux futurs tests de RTT, pertes, gigue et usages applicatifs. |
| Acceptation | Seuils de latence, de débit minimal et de coût système définis avant l'essai ; conditions d'abstention et de retour arrière. Aucun seuil universel n'est inventé par le diagnostic. |

Le [protocole de latence](LATENCY.md) explique la méthode actuelle, les percentiles et leurs limites. Il ne génère pas la charge ni ne démontre une amélioration.

La restauration devra disposer d'un état initial suffisamment complet pour les objets réellement modifiés : files, classes, filtres, règles de routage et pare-feu concernés. Elle devra fonctionner indépendamment du processus de pilotage et être vérifiée après interruption, avec IPv4, IPv6 et DNS. Le comportement en cas de panne doit être choisi avant l'activation. Ces mécanismes restent à développer ; ce diagnostic n'autorise ni n'effectue une intervention.

Pour conserver volontairement ce rapport texte dans un dossier exclu de Git :

```sh
mkdir -p .local/gateway-reports
./.local/bin/coopace-gateway inspect > .local/gateway-reports/inspection.txt
```

Les noms d'interfaces et les chemins des outils restent des métadonnées locales ; le rapport n'est envoyé ni au groupe ni au ML.

## Validation actuelle

Les tests utilisent des données contrôlées pour vérifier les valeurs manquantes, les sorties JSON, les tables multiples et les routes non résolues. Ils vérifient les requêtes en lecture seule, l'absence d'exécution d'un outil manquant, l'annulation d'une commande bloquée et le refus des sorties trop grandes. Les tests de CLI couvrent aide, arguments invalides, rapport partiel et erreurs d'affichage.

Le lancement Linux réel a produit un rapport partiel dans l'environnement isolé : flags IPv4/IPv6 et capacité effective lus, outils détectés, mais interfaces, routes et files indisponibles car Netlink y est interdit. Une lecture complète sur le PC Linux utilisateur reste à consigner. La compilation et l'analyse statique Windows ne valident pas une collecte Windows ni une passerelle Windows.

```sh
sh scripts/go.sh test ./apps/gateway/... ./platforms/linux
sh scripts/go.sh test ./...
```
