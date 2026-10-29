# Cible TCP du laboratoire

Ce programme Go est un outil de développement utilisé par `lab-network.sh run-tcp`, distinct des applications distribuées. Il accepte puis ferme les connexions TCP sans lire ni envoyer de données applicatives. Il ne produit aucune charge de saturation.

```sh
sh scripts/go.sh build -o .local/bin/coopace-lab-tcp ./scripts/lab-tcp
```

| Option | Contraintes |
| --- | --- |
| `--listen` | Obligatoire : IPv4 privée ou de boucle locale explicite, port de 1024 à 65535. Les noms DNS, adresses indéfinies, IPv6 et IPv4 publiques sont refusés. |
| `--connections` | De 1 à 100 ; défaut : 5. |
| `--duration` | De 1s à 30s ; défaut : 15s. |

Le programme annonce `READY IP:port` sur stdout seulement après l'ouverture de l'écoute. Il termine avec le code `0` après le nombre de connexions demandé, `1` après une erreur, expiration ou interruption, et `2` pour des options invalides. L'expiration ferme l'écoute et débloque l'attente de connexion. SIGINT, SIGTERM et SIGHUP annulent le contexte ; SIGKILL ne peut pas être intercepté.

Le binaire seul n'exige pas de privilèges ; le script les utilise pour entrer dans l'espace réseau neuf du serveur. La durée est une limite applicative ; ce programme n'est pas un superviseur indépendant de la passerelle.

Les tests utilisent `net.Pipe` et une écoute simulée pour vérifier les fermetures sans contenu, les limites, l'annulation et les erreurs. Un test TCP en boucle locale est aussi fourni et explicitement ignoré si les sockets sont interdites :

```sh
sh scripts/go.sh test -count=1 -v ./scripts/lab-tcp
```

Voir le [scénario du laboratoire](../../docs/VIRTUAL_LAB.md) pour l'exécution à travers la passerelle. Un [premier essai natif routé](../../docs/VALIDATION_VIRTUAL_LAB_2026-10-29.md) a réussi ; il n'ajoute aucun résultat natif au test Go de boucle locale lorsqu'il est ignoré dans l'environnement isolé.
