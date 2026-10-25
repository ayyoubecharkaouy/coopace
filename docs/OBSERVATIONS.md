# Premières observations locales — étape 3.1

## Fonction disponible

Sous Linux, `coopace observe` effectue deux lectures des compteurs d'interfaces, séparées par une pause demandée d'une seconde. Il affiche les taux moyens reçus et envoyés pendant la fenêtre effectivement mesurée, en **octets par seconde**.

```sh
sh scripts/go.sh run ./apps/agent/cmd/coopace observe
```

Ou, après compilation :

```sh
sh scripts/go.sh build -o .local/bin/coopace ./apps/agent/cmd/coopace
./.local/bin/coopace observe
```

La commande se termine après cette observation. Elle lit des statistiques agrégées, sans générer de trafic de test, modifier le routage ni inspecter les paquets. Elle n'enregistre aucun fichier de mesures et n'envoie aucune donnée à un groupe ou à un serveur.

## Provenance et calcul

L'adaptation Linux lit les champs d'octets reçus et envoyés de `/proc/net/dev`, dans l'espace réseau visible par le processus. Ce choix d'interface texte permet une première intégration avec la bibliothèque standard. La documentation du noyau décrit cette interface historique et recommande rtnetlink pour l'accès aux statistiques standard : voir les [statistiques d'interfaces Linux](https://docs.kernel.org/networking/statistics.html#procfs). Une adaptation future pourra utiliser rtnetlink si les besoins le justifient.

Le noyau métier calcule, pour chaque nom d'interface présent dans les deux lectures :

```text
octets reçus = compteur RX final - compteur RX initial
octets envoyés = compteur TX final - compteur TX initial
taux moyen = différence d'octets / durée effectivement mesurée en secondes
```

Les soustractions utilisent les entiers avant le calcul des taux, pour conserver les petites différences même lorsque les compteurs cumulés sont élevés. La durée est calculée avec l'horloge monotone de Go entre les fins des deux lectures. Les horodatages de ces lectures et la source sont conservés dans le rapport applicatif en mémoire.

Les lectures ne constituent pas un instantané atomique de tous les appareils ou du foyer. Leur durée et l'actualisation des statistiques par les pilotes limitent la précision d'une fenêtre courte.

## Valeurs absentes et changements d'interfaces

| Situation | Résultat |
| --- | --- |
| Compteurs identiques | Taux mesuré à zéro sur la fenêtre ; cela ne prouve pas une coupure Internet. |
| Interface apparue ou disparue | Taux indisponible, affiché avec `-`. |
| Baisse d'un compteur RX ou TX | Fenêtre invalidée pour cette interface, sans soustraction non signée erronée. |
| Source illisible ou données invalides | Erreur de la commande, sans mesures de remplacement. |

La comparaison se fait par nom d'interface. Une interface recréée sous le même nom peut ne pas être détectée si les compteurs finaux sont supérieurs aux compteurs initiaux. Cette première version ne prétend donc pas détecter tous les changements d'identité d'interface.

## Interprétation et limites

- Ces valeurs peuvent inclure du trafic local, des interfaces virtuelles, un VPN et la boucle locale `lo`.
- Elles ne distinguent pas le WAN du LAN et ne donnent pas le débit maximal disponible de l'accès Internet.
- Les interfaces ne sont pas additionnées : un même trafic peut traverser plusieurs interfaces et serait alors compté plusieurs fois.
- Aucun RTT, perte de bout en bout, gigue, diagnostic Wi-Fi ou gain d'optimisation n'est encore mesuré.
- Les noms d'interfaces, horodatages et compteurs sont les seules observations utilisées ; aucune adresse IP/MAC, URL, application ou charge utile n'est collectée par ce module.

Lors de la validation dans l'environnement isolé de développement, seule l'interface `lo` était visible. Le lancement réel a confirmé une observation à zéro sur cette interface. Cela valide le chemin de lecture et d'affichage, sans démontrer la couverture du trafic Internet de l'ordinateur ni un bénéfice réseau.

## Organisation

- `packages/core/traffic.go` : modèles, calcul des différences et traitement des fenêtres indisponibles.
- `platforms/linux/traffic*.go` : lecture et décodage des compteurs Linux.
- `apps/agent/internal/observe` : orchestration des deux lectures et provenance de l'observation.
- `apps/agent/internal/cli` : commande et affichage.

Les modèles métier n'ont pas de format JSON de communication. Les messages versionnés et leur conversion seront définis dans l'étape consacrée au protocole.

## Plateformes et suite

L'observation des compteurs est implémentée pour Linux. Sous Windows, la commande est compilable mais renvoie une erreur d'indisponibilité avec le code `1` ; elle n'affiche pas de faux compteurs à zéro. Le lancement natif Windows reste à vérifier. Aucune application Android n'est produite.

L'étape 3.2 devra définir les mesures de latence et le protocole de référence avant toute intervention. La collecte Windows, l'export de mesures et l'échange entre appareils restent à spécifier et à valider séparément.
