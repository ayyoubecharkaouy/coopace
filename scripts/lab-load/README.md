# Transfert synthétique borné

Ce programme Go est un outil de laboratoire. `send` écrit un volume borné d'octets nuls vers une seule connexion TCP ; `receive` accepte une connexion, jette les données et exige exactement le volume annoncé suivi de la fin du flux. Aucun fichier utilisateur n'est lu et aucun contenu reçu n'est conservé.

```sh
sh scripts/go.sh build -o .local/bin/coopace-lab-load ./scripts/lab-load
./.local/bin/coopace-lab-load --help
```

| Option | Contraintes |
| --- | --- |
| `send --target` / `receive --listen` | IPv4 privée ou de boucle locale explicite, port de 1024 à 65535. Noms DNS, adresses indéfinies, IPv6 et IPv4 publiques refusés. |
| `--bytes` | Volume exact de 1 à 33 554 432 octets ; défaut : 8 388 608 (8 Mio). |
| `send --rate` | Plafond moyen applicatif de 65 536 à 4 194 304 octets/s ; défaut : 1 048 576 (1 Mio/s). |
| `--duration` | Délai de 1s à 30s ; défaut : 12s en émission et 15s en réception. |

Le volume divisé par le débit demandé doit être strictement inférieur au délai d'émission. Le délai couvre la connexion, les écritures et leur cadence ; en réception, il couvre aussi l'attente du premier client et de la fin du flux. SIGINT, SIGTERM et SIGHUP annulent le contexte et ferment les sockets. Ce délai applicatif ne constitue pas un superviseur indépendant.

Le bloc synthétique fait au plus 16 Kio. L'émetteur cadence les écritures selon leur cumul et attend aussi après le dernier bloc. Le premier bloc peut partir immédiatement ; un retard de traitement peut être suivi d'écritures rapprochées. Le plafond porte sur la moyenne des écritures et pauses, sans garantir un plafond instantané sur le lien. Le noyau peut tamponner les données ; les en-têtes réseau ne sont pas comptés. Cet outil ne configure pas les files de la passerelle.

Le récepteur annonce `READY IP:port` sur stdout après ouverture de l'écoute. Il ferme l'écoute après la première connexion et lit au plus le volume attendu plus un octet, ce qui permet de rejeter un dépassement. Un volume incomplet, un dépassement, une erreur ou une expiration retourne `1`. Après réception exacte et fin du flux, il retourne `0` et inscrit le comptage sur stderr. Une annonce de disponibilité peut donc précéder un échec ultérieur.

L'émetteur publie un objet JSON local v1 seulement si son envoi a abouti. Le format `synthetic_tcp_send` contient la cible, les versions et plateforme, le volume demandé et écrit, le plafond demandé, la taille du bloc, le délai, les horodatages UTC, la durée monotone en millisecondes et la moyenne en octets/s. Ce rapport décrit les écritures côté émetteur ; il ne prouve pas à lui seul la réception distante. Une erreur réseau retourne `1`, sans JSON de réussite ; des arguments invalides retournent `2` sans accès réseau. Les erreurs et détails vont sur stderr.

Le mode `lab-network.sh run-load` attend en plus la réussite du récepteur et du nettoyage avant de publier ce JSON. Son protocole et sa validation native encore à effectuer sont dans [VIRTUAL_LOAD.md](../../docs/VIRTUAL_LOAD.md).

Les tests utilisent des connexions en mémoire : volume exact, octets nuls, écritures partielles, absence de progression, cadence, arguments invalides, délais et libération des sockets. Un test en boucle locale est ignoré explicitement si les sockets sont interdites :

```sh
sh scripts/go.sh test -count=1 -v ./scripts/lab-load
```
