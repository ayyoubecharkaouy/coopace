# Campagne TBF sous supervision — mise en œuvre du protocole v1

## État et périmètre

`scripts/lab-campaign.py` et le module `lab_campaign.py` implémentent les trois paires du [protocole de goulot virtuel v1](VIRTUAL_BOTTLENECK.md). Les tests utilisent des commandes réseau simulées et de vrais processus/signaux. **La première validation native de cette campagne reste à réaliser.** Le [contrôle fonctionnel d'un transfert](VALIDATION_LAB_ACTIVE_2026-10-30.md) reste une preuve préalable distincte.

La campagne conserve une seule TBF à 4 Mbit/s, burst 65 536 et limit 131 072 octets, sur `wan` dans une passerelle neuve. Les six phases suivent exactement idle/loaded, loaded/idle, idle/loaded. Chaque phase mesure dix connexions TCP, timeout 1s et pause 250ms. Chaque phase loaded transfère 8 Mio avec les délais de 25s/28s et la stabilisation d'au moins 1s déjà déclarés. Les paramètres et seuils du protocole v1 restent inchangés.

Les commandes historiques de `lab-network.sh` et les modes de `lab-active.py` gardent leur rôle. Les applications du produit ne changent pas ; ces pilotes Python restent des outils de développement.

## Propriété et coordination

Le [superviseur indépendant](LAB_GUARD.md) possède trois espaces, les deux veth, la configuration et la file. Avant le pilote, il désactive puis réactive le forwarding dans la passerelle neuve, en relisant chaque valeur : une sonde ICMP doit sortir avec `1` sans forwarding, puis trois réponses doivent être reçues avec forwarding. Les codes inattendus et les réponses incomplètes arrêtent l'essai. Les sorties ping en locale C sont conservées. Il n'y a ni route par défaut, NAT, interface physique ni accès Internet.

Un unique pilote reste dans un groupe distinct pendant toute la campagne. À chaque début de phase, il attend un accusé du superviseur : celui-ci capture d'abord la file. Le pilote démarre ensuite ses outils, effectue la mesure et les arrête/récupère avant d'annoncer la fin. Le superviseur capture la file puis exige backlog et qlen nuls à deux lectures espacées d'au moins 500ms, dans un délai de 3s. Il autorise ensuite la phase suivante. Les outils restent dans le groupe du pilote, sans création de session supplémentaire.

Pendant chaque phase, les lectures `tc -j -s -r` reprennent après une pause d'au moins 250ms depuis la fin de la précédente. Conserver les temps réels ; aucune cadence exacte de 4 Hz n'est garantie. Chaque lecture revalide la possession des espaces et les paramètres TBF. Les compteurs cumulés sont séparés des jauges ; une baisse observée invalide la différence concernée, y compris entre phases.

Le délai du pilote est 150s, celui du superviseur 180s, et le nettoyage a 10s. Chaque outil doit être disponible en 5s ; la commande de latence a 16s. Les commandes de configuration et comparaison ont 2s ; les contrôles ICMP ont respectivement 4s et 6s pour englober leurs délais ping de 3s et 5s. Le canal d'accusés est borné à 8s, la sortie totale du pilote à 1 Mio, une ligne à 256 Kio, les lectures à 720/4 Mio et le journal à 8 Mio.

Le superviseur garde le leader non récupéré jusqu'au dernier signal collectif, puis récupère les descendants avant suppression des espaces. Sa propre destruction par SIGKILL ou la panne de l'hôte restent hors garantie. Il ne restaure pas une passerelle existante.

## Preuves conservées et décisions

Le dossier passé par `--artifacts` doit exister. Les fichiers sont créés exclusivement, sans écrasement ni suivi d'un lien symbolique à leur emplacement. Ils restent en dehors de la réservation jetable et sont conservés en cas d'échec :

| Pièce | Contenu |
| --- | --- |
| `progress.jsonl` | Journal horodaté, écrit et vidé après chaque événement : ressources possédées, contrôles de passage, messages du pilote, lectures brutes/normalisées, comparaisons et nettoyage confirmé. |
| `phase-N-idle.json`, `phase-N-loaded.json` | Rapport TCP local v1 complet, conservant chaque tentative et les échecs ; créé après réception/arrêt des outils et contrôle du vidage de la phase. |
| Rapport final sur stdout | JSON v1 `lab_bottleneck_campaign`, configuration, contrôles, phases avec émission/réception, lectures, différences, comparaisons, décisions et preuves de nettoyage. |

Après chaque paire, le superviseur appelle la vraie CLI `coopace latency compare` sur les deux fichiers. Elle valide strictement les schémas, statistiques recalculées et paramètres/provenances compatibles. Sa sortie descriptive est conservée ; elle ne décide pas de la congestion.

`decision.technical_valid` exige les six phases, trois réceptions exactes, les rapports validés, le recouvrement avec les écritures, une stabilisation d'au moins 1s et des différences de compteurs disponibles. Les contrôles de passage, paramètres et nettoyage doivent aussi avoir réussi avant publication. Les critères de file alimentée, débit reçu entre 350 000 et 525 000 octets/s et augmentation de p50 d'au moins 10ms dans deux paires sont appliqués séparément, tels que déclarés dans le protocole v1.

| Résultat | Code et signification |
| --- | --- |
| Collecte valide, critères de congestion réunis | Code `0`, `technical_valid: true`, `congestion: observed`. |
| Collecte valide, critères non réunis | Code `0`, `technical_valid: true`, `congestion: not_demonstrated`. |
| Six phases collectées, mais recouvrement/stabilisation ou compteurs non conformes | Code `1`, rapport conservé après nettoyage, `technical_valid: false`, `congestion: non_exploitable`. |
| Erreur opérationnelle ou collecte interrompue | Code non nul, stderr et preuves intermédiaires conservés ; aucun rapport final de réussite. Un nettoyage incomplet conserve aussi le journal de possession. |

Une série entièrement en échec garde ses dix tentatives et ses percentiles indisponibles. Elle ne satisfait pas le critère de latence ; un échec ne devient jamais une durée nulle. Les percentiles des paires ne sont pas moyennés. Aucun résultat n'est un gain Coopace, une capacité WAN ou une référence CAKE.

## Contrôle de panne et lancement natif

Le mode `check-crash` suit le même pilote et le même canal de coordination. Après la première phase idle, il tue le pilote après la première écriture du premier transfert loaded. Il exige une sortie du pilote `-9`, trois outils orphelins récupérés et le nettoyage confirmé. Le rapport conserve la phase terminée et les relevés de la phase interrompue ; `technical_valid` vaut `null` et `congestion` vaut `not_assessed`. Les réceptions partielles et annulations sont attendues dans ce mode. La dernière lecture de file précède l'arrêt des outils.

Prévisualisation et tests sans privilèges :

```sh
python3 -I -B scripts/lab-campaign.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_campaign.py' -v
```

Les tests vérifient ordre des six phases, trois réceptions, comparaisons, données conservées, critères et seuils, interruptions, échéance, erreurs de statistiques/comparaison et récupération après mort forcée. Les commandes réseau et le comparateur sont simulés dans ces tests de processus ; ils ne prouvent pas une congestion native.

Pour l'essai natif, préparer un dossier neuf contenant protocole figé, source, versions, empreintes, trois binaires compilés avec le compte habituel et deux sous-dossiers de preuves distincts pour `check-crash` et `run`. Le lanceur appelle `sudo` uniquement pour ces modes, vérifie les entrées et conserve stdout/stderr/codes. Il exige Linux, Python 3, `ip`, `tc`, `sysctl`, `ping`, `CAP_NET_ADMIN`, `CAP_SYS_ADMIN` et `CAP_NET_RAW`. Valider d'abord le contrôle de panne, puis lancer la campagne. Une collecte sans congestion démontrée doit être conservée autant qu'une collecte satisfaisant les critères.
