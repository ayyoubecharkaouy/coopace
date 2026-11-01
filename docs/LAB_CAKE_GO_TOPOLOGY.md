# Activation après la phase Go et continuité de CAKE

## État et portée

`scripts/lab_cake_go_topology.py` implémente l’activation prévue par le [contrat Go puis trafic](LAB_CAKE_GO_ACTIVE.md), après la [phase Go réutilisable](LAB_CAKE_GO_PHASE.md). Les tests enchaînent la phase puis l’activation avec un noyau réseau simulé et de vrais processus/descripteurs pour le contrôle précédent.

Le chemin du laboratoire peut être configuré et relu par ce module interne. Il ne lance pas de transfert, de sonde ou de contrôle négatif ICMP. Le pilote à accusé, la collecte combinée, la CLI active et la validation native de l’enchaînement restent à développer. La [preuve native DOWN](VALIDATION_CAKE_GO_DOWN_2026-11-01.md) reste liée à sa révision source historique.

## Entrée et responsabilités

`activate_after_phase(owner, down, sysctl, record)` reçoit le propriétaire encore ouvert, son lien DOWN, un outil `sysctl` identifié par chemin canonique/SHA-256 et un enregistreur de preuves obligatoire. L’appelant de confiance prépare ces outils et le journal ; le callback doit borner, dater et synchroniser ses écritures avant de rendre la main.

L’activation exige une phase Go normale vérifiée, son leader et son groupe récupérés, ses références héritées fermées et son journal complet relu. Elle utilise la session retenue par le propriétaire ; un simple objet JSON de phase ne remplace pas ce contexte. Le mode DOWN de panne ne permet pas l’activation.

Le module vérifie une nouvelle fois outils, sources et identité des espaces. Il rapproche les liens `lo`/`wan` du dernier relevé brut `ip` dans le journal Go. Le client doit encore contenir seulement `lo`, la passerelle `lo`/`wan` et le serveur `lo`/`eth0`, tous DOWN ; les extrémités n’ont aucune adresse et les tables IPv4 principales sont vides. Les adresses locales de loopback éventuelles restent admises.

Après ces contrôles, le propriétaire réserve son groupe suivant sans changer les espaces ni le délai global. Ce groupe reste vide, disponible pour le futur pilote de trafic. Le module réutilise `lab_active.activate` pour les seuls quinze changements fixes : ajout de `lan`/pair client, quatre adresses IPv4, activation des interfaces et loopbacks, deux routes spécifiques et forwarding IPv4 dans la passerelle possédée.

La séquence des changements est imposée et à usage unique ; une commande échouée peut déjà avoir eu un effet. Aucune commande d’ajout/remplacement/suppression de qdisc n’est admise dans cette phase. Le profil ajouté par Go reste `cake-ipv4-lab-4mbit-v1`.

## Relectures et continuité

La méthode `Topology.verify(label)` relit :

- Les interfaces détaillées attendues dans les trois espaces : `lo`/`eth0`, `lo`/`lan`/`wan`, `lo`/`eth0`.
- Les indices, pairs, MTU et MAC des veth ; les identités préexistantes restent celles observées avant activation et dans le journal Go.
- Les états UP, les adresses IPv4 exactes du laboratoire et les seules adresses IPv6 locales automatiques éventuellement présentes.
- Les deux routes de chaque table IPv4 principale : routes connectées et routes spécifiques, sans défaut, autre table déclarée, chemin multiple ou route inactive.
- Le forwarding IPv4 égal à `1`, puis les options et statistiques de CAKE.

Les nouvelles extrémités `lan`/client sont rapprochées par indices de pairs réciproques et conservées pour les relectures suivantes. Les observations brutes des interfaces, adresses et routes restent dans les preuves. La lecture porte sur IPv4 dans la table principale ; elle ne valide ni le routage IPv6, les règles de routage avancées, le DNS ou la couverture du foyer.

Chaque lecture CAKE passe par les validateurs existants du producteur `iproute2-6.1.0`. Aucun des cinq compteurs racine ne peut diminuer entre relevés. Les jauges ne sont pas soustraites. Une progression pendant l’activation peut provenir du trafic IPv6 automatique et ne devient pas un volume utile ou une mesure de capacité WAN.

Le relevé de fin de phase Go est conservé comme `after_go_exit`. `down_statistics_delta` garde sa différence historique ; `activation_statistics_delta` compare ce relevé à la dernière relecture d’activation. Les futures différences de trafic auront leur propre point de départ juste avant le pilote.

## Preuves, état et nettoyage

Le callback reçoit contexte/empreintes, intention et résultat de chaque commande, sorties exactes encodées en base64, durées monotones, topologies brutes et relevés CAKE normalisés. Une erreur avant l’enregistrement de l’intention empêche le lancement de la commande. Une erreur d’enregistrement après exécution interdit le succès et déclenche le nettoyage via l’appelant de l’activation.

Les chemins/empreintes des exécutables concernés sont revérifiés avant les appels ; tous les outils et sources sont revérifiés avant confirmation. Les commandes restent bornées par l’exécuteur existant à deux secondes, avec les limites de sortie et l’échéance du propriétaire.

Le checker retourné porte `state: activated`, avec ressources conservées et nettoyage différé. Cela ne constitue pas un rapport global de réussite. En cas d’échec de l’activation, le module interdit la suite et ferme le propriétaire. Une identité de namespace incertaine empêche sa suppression et conserve la réservation. Une erreur lors d’une relecture ultérieure rend le checker défaillant ; son appelant doit toujours fermer le propriétaire dans `finally`.

Une activation réussie exige encore ce `finally` après utilisation. L’événement intermédiaire `activation_verified` conserve `cleanup: deferred_to_supervisor` et `traffic_generated: false` pour la charge synthétique. Il ne fournit aucune autorisation issue de `plan` et aucune preuve de transfert.

## Vérification et suite

Les tests de `test_lab_cake_go_topology.py` vérifient la transition, les quinze changements, les relectures répétées et l’absence de mutation de qdisc. Ils refusent modifications de lien, interface étrangère, adresse/route incorrecte, forwarding non confirmé, profil altéré, baisse des compteurs, outil modifié, preuve défaillante et activation après panne Go. Les validateurs d’adresses/routes ont aussi des cas de types et chemins incompatibles.

Les appels réseau et le processus du contrôle Go sont simulés ; la suppression des espaces est représentée par des fichiers. Ces essais ne valident pas encore les nouveaux relevés sur `ip`/`tc` natifs. Les commandes DOWN et les contrôles actifs historiques restent indépendants.

La prochaine sous-étape développe le pilote de trafic à accusé de disponibilité sur les ressources activées. La collecte et le rapport combinés, puis les deux contrôles natifs complets, suivront selon le contrat.
