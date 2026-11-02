# Pilote privé des six phases après Go

## État et portée

Le pilote `scripts/lab_cake_go_campaign_traffic.py` et son entrée privée `scripts/lab-cake-go-campaign-traffic.py` sont implémentés. Ils utilisent les [lecteurs et l’automate de campagne](LAB_CAKE_GO_CAMPAIGN_PROTOCOL.md). Les tests exécutent de vrais processus, pipes et groupes Linux ; les outils réseau et leurs rapports sont simulés.

**Le [collecteur interne](LAB_CAKE_GO_CAMPAIGN_COLLECT.md) est implémenté et testé avec réseau simulé ; l’évaluation et la commande publique restent à développer. Aucune campagne réseau native n’a été exécutée.** Ce pilote ne possède, ne crée ni ne supprime de namespace et ne modifie aucune file ou route. Le superviseur établit le contexte Go, l’activation et le passage IPv4 avant son lancement.

## Entrée et inventaire

L’entrée privée exige `--session-id`, `--client`, `--server`, `--ip`, `--binaries` et `--tools-json`. Elle doit être lancée comme leader du groupe/session réservé par le superviseur. Les noms client/serveur sont exactement `cg-JETON-c` et `cg-JETON-s` ; ils ne prouvent pas la possession des espaces.

L’inventaire contient exactement `schema_version: 1`, `kind: lab_cake_go_campaign_tools`, `session_id` et `tools`, avec les quatre rôles `ip`, `agent`, `target`, `load`. Les chemins canoniques et empreintes SHA-256 sont vérifiés avant chaque lancement. Les trois programmes de trafic doivent correspondre aux noms attendus dans `--binaries`. La vérification ELF et la provenance globale restent à la charge de l’inventaire du superviseur.

L’inventaire réutilise les vérifications du [pilote à flux unique](LAB_CAKE_GO_TRAFFIC.md) sous une enveloppe distincte. Il autorise uniquement cible puis sondage en idle ; cible, récepteur, émetteur puis sondage en loaded. Saut de rôle, phase différente et double lancement sont refusés avant création du processus concerné. Chaque outil reçoit `/dev/null` en entrée et reste dans le groupe du pilote.

## Séquence exécutée

Le pilote annonce chaque `begin`, puis attend `start` avant de créer le moindre outil de cette phase. Après disponibilité, il annonce un PID en idle ou trois en loaded, en vérifiant leur vie et leur appartenance au groupe courant. Il attend le `continue` lié à la session et à la phase avant tout sondage.

La phase idle lance une cible neuve et dix établissements TCP avec condition `idle`. La phase loaded réutilise `lab_active.measure_loaded` : cible/récepteur/émetteur, première écriture, accord, stabilisation et dix sondes. Les paramètres du [contrat de campagne](LAB_CAKE_GO_CAMPAIGN.md) sont inchangés.

Les outils de la phase sont récupérés avant l’émission de `end`. Le pilote attend ensuite `advance` ; il ne décide pas lui-même du vidage de CAKE. L’ordre est idle/loaded, loaded/idle, idle/loaded, avec des outils neufs à chaque phase. Après le sixième `advance`, il transmet `complete` et termine.

Une mesure TCP sans réussite reste une donnée de phase, avec code de mesure 1 et tentatives échouées conservées. Elle n’empêche pas à elle seule les six phases de se terminer. Le code 0 du pilote signifie dialogue et résultats compatibles ; il ne qualifie ni charge ni connexions et ne valide aucun gain réseau.

## I/O, délais et captures

Les deux sens du dialogue sont non bloquants. Le lecteur accepte les contrôles fragmentés, puis exige une seule ligne complète sans données supplémentaires à la frontière attendue. Un contrôle reçu avant publication de LF, répété ou hors phase interdit la poursuite ; un EOF avant le dernier `advance` est refusé.

Chaque écriture possède une borne de 5 s. Le délai d’attente d’un accusé est fixé à 5 s depuis publication du LF, sans remise à zéro à chaque fragment. Le pilote conserve une échéance applicative de 150 s depuis son entrée, incluant l’inventaire. La disponibilité de phase est bornée à 15 s après `start`, et les attentes individuelles des outils à 5 s ; les sondes restent bornées à 16 s. Ces limites ne remplacent pas l’échéance indépendante de 180 s du propriétaire.

Les stdout/stderr de chaque outil sont lus par blocs bornés, avec contrôle d’annulation entre tours. stdout est limité à 256 Kio cumulés par outil, annonce de disponibilité comprise. Les messages du pilote restent limités à 1 Kio ou 256 Kio pour `end`, et 2 Mio cumulés.

Les stderr des outils ont leurs propres pipes. Le pilote les collecte avec un budget cumulé de 256 Kio moins 2 Kio réservés à son diagnostic, puis les transmet progressivement sur son stderr sans attendre une écriture bloquante sur pipe. Une sortie excessive ou un lecteur bloqué provoque un échec. Un échec peut conserver seulement la partie de sortie déjà transmise ; le collecteur conserve ces octets et le code non nul, sans les présenter comme une capture complète de succès.

## Arrêt et responsabilités restantes

Les signaux HUP/INT/TERM enregistrent un drapeau ; chaque nouveau processus est enregistré avant le contrôle suivant de ce drapeau. Les outils sont terminés puis tués si nécessaire, avec récupération bornée et fermeture de leurs captures. Un arrêt ou une fin de capture incertain reste un échec et interdit la phase suivante.

L’arrêt normal d’un outil est borné à 1 s ; la récupération de tous les outils dispose d’un budget partagé de 10 s lors de la fermeture de phase ou sur erreur. Ce nettoyage ne dépend pas d’un contrôle encore attendu sur stdin. Le propriétaire doit toujours récupérer le groupe complet avant retrait des espaces, même après une erreur du pilote.

SIGKILL ne permet aucun nettoyage par le pilote. Le test tue le seul leader au premier `ready` chargé après une phase idle complète ; le garde externe récupère alors ses trois outils orphelins. Ce garde de test ne constitue pas encore le raccordement au superviseur Go de campagne.

Le collecteur vérifie les identités annoncées, les outils et ressources possédés, conserve les temps de réception avant validation des lignes, mesure CAKE, impose le vidage et journalise ses décisions avant accusés. Les faits de namespace, la collecte, les comparaisons et le certificat natif ne sont pas produits par ce pilote.

## Vérification et suite

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go_campaign_traffic.py' -v
```

Les tests couvrent six phases normales, accusés fragmentés, mesures échouées, contrôles absents/prématurés/répétés/hors session ou phase, EOF, dépassement de délai, sorties excessives, modification d’outil, sortie bloquée, interruption et récupération après SIGKILL. Les marqueurs des outils vérifient aussi leur stdin fermé, l’absence de sondage avant `continue` complet et leur disparition avant `end`.

Les tests de l’inventaire vérifient le périmètre de campagne et l’ordre fermé des rôles. La suite du dialogue pur et celle du pilote à flux unique restent vérifiées séparément. Aucun test ne crée de socket, namespace ou qdisc réel ; les transferts de 8 Mio et les durées des rapports sont simulés.

Validation locale du 1er novembre 2026 : les 33 tests ciblés passent en 76,734 s, dont huit nouveaux (six tests de processus et deux d’inventaire), quatorze de dialogue de campagne et onze du pilote à flux unique. L’aide de l’entrée privée est également vérifiée. La suite complète du dépôt n’a pas été relancée pour cet ajout isolé.

Ce pilote est raccordé au [collecteur interne](LAB_CAKE_GO_CAMPAIGN_COLLECT.md), avec contrôles de PID, journal durable et vidage entre phases testés en simulation. L’évaluation pure, la préparation figée/relecture puis les essais natifs restent à réaliser avant toute conclusion expérimentale.
