# Campagne CAKE sous supervision

## État et périmètre

`scripts/lab-cake-campaign.py` et `lab_cake_campaign.py` implémentent une campagne CAKE de trois paires, telle que définie avant collecte dans le [protocole comparatif v1](CAKE_COMPARISON.md). Les tests utilisent des commandes réseau simulées et de vrais processus/signaux. **La première validation native est consignée** : six phases, 60 connexions réussies, trois réceptions complètes, charge qualifiée et nettoyage normal ou après mort forcée. Voir le [compte rendu du 30 octobre](VALIDATION_LAB_CAKE_CAMPAIGN_2026-10-30.md). Le [contrôle fonctionnel CAKE actif](VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md) est déjà validé pour un transfert et le nettoyage après panne.

Cette sous-étape prépare un bras CAKE isolé. L'orchestration des six campagnes neuves et l'agrégateur des neuf comparaisons TBF/CAKE restent à développer. Une ancienne campagne TBF ne devient pas le bras de comparaison de cet essai.

## Configuration et coordination

La campagne utilise les options et le validateur du [contrôle CAKE DOWN](LAB_CAKE.md), sans modification : débit fixe 4 Mbit/s, `besteffort`, `flows`, `nonat`, `nowash`, `raw`, `mpu 0`, `rtt 100ms`, `split-gso`, `no-ack-filter`, `egress`, `memlimit 1048576`, `fwmark 0`. Le producteur JSON doit correspondre au profil identifié iproute2-6.1.0. Les omissions reconnues restent justifiées ; les statistiques absentes ne deviennent pas zéro.

Le superviseur crée trois espaces neufs et ajoute la file sur le veth `wan` désactivé, puis active le chemin IPv4 par la fonction commune de `lab_active.py`. La classe `Passage` de `lab_campaign.py` vérifie le forwarding désactivé avec une sonde ICMP (sortie `1`), puis réactivé avec trois réponses reçues. Aucun accès Internet, route par défaut, interface physique ou NAT n'est ajouté.

La coordination des phases et le pilote sont ceux de la [campagne TBF](LAB_CAMPAIGN.md) : idle/loaded, loaded/idle, idle/loaded ; dix tentatives TCP par phase, timeout 1s et pause 250ms ; trois transferts de 8 Mio, plafond applicatif 1 Mio/s, délais émission/réception 25s/28s. Les sondes loaded commencent au moins 1s après la première écriture et doivent rester dans la fenêtre d'écritures. Chaque phase exige ensuite deux lectures de file vide espacées d'au moins 500ms, sous 3s.

Le pilote dure au plus 150s, le superviseur 180s et le nettoyage 10s. Les limites des outils, du canal d'accusés, des lectures et du journal sont celles de la campagne TBF. Les lectures périodiques reprennent après une pause d'au moins 250ms ; chaque lecture vérifie les options CAKE et la possession des espaces. Toute baisse observée d'un compteur, même entre phases, invalide sa différence. Les jauges et détails de classe ne sont pas additionnés aux compteurs racine. La mémoire rapportée par ce producteur reste un maximum historique du noyau, pas une mesure de RAM instantanée.

## Preuves et décisions

`--artifacts` désigne un dossier existant, neuf pour cet essai. Les fichiers y sont créés exclusivement, sans écrasement ni suivi d'un lien symbolique à leur emplacement :

| Pièce | Contenu |
| --- | --- |
| `progress.jsonl` | Ressources possédées, toutes les relectures CAKE brutes/normalisées, contrôles de passage, événements du pilote, échantillons par phase, comparaisons et nettoyage confirmé. |
| `phase-N-idle.json`, `phase-N-loaded.json` | Six rapports TCP locaux v1 complets, conservant les tentatives et échecs. |
| Rapport stdout | JSON v1 `lab_cake_campaign`, six phases, émission/réception, configuration, statistiques, décisions et nettoyage. |

Chaque paire passe par la vraie CLI `coopace latency compare`, comme sous TBF. La comparaison est descriptive et interne à cette paire CAKE. Le journal est vidé après chaque événement et reste hors de la réservation jetable, y compris en cas d'erreur. L'événement `cleaned` est publié seulement après un nettoyage confirmé et la constitution du rapport.

`decision.technical_valid` exige l'ordre des six phases, les rapports validés, trois réceptions exactes, recouvrement et stabilisation conformes, différences de compteurs disponibles et au moins deux lectures dans chaque fenêtre de sondes loaded. Paramètres, contrôles de passage et nettoyage sont aussi vérifiés avant publication. Une erreur opérationnelle conserve les preuves partielles et donne un code non nul, sans rapport final de réussite.

La qualification de charge est séparée : pour chacune des trois fenêtres loaded, les octets racine doivent progresser et le débit utile reçu doit appartenir à l'intervalle inclusif [350 000 ; 525 000] octets/s. **Aucun backlog CAKE durablement positif ni augmentation de p50 n'est exigé.** Le protocole TBF conserve ses propres critères inchangés.

| Résultat | Code et décision |
| --- | --- |
| Collecte exploitable, charge qualifiée | `0`, `technical_valid: true`, `load_scenario: qualified`. |
| Collecte exploitable, progression ou débit non conforme | `0`, `technical_valid: true`, `load_scenario: not_qualified`. Toutes les phases sont conservées. |
| Collecte complète mais contexte ou compteurs non exploitables | `1`, `technical_valid: false`, `load_scenario: non_exploitable`. Rapport conservé après nettoyage. |
| Contrôle de panne réussi | `0`, `technical_valid: null`, `load_scenario: not_assessed`. |

`congestion` et `comparison` restent `not_assessed` dans tous ces résultats CAKE. La différence p50 loaded−idle reste signée, sans moyenne de percentiles. Des percentiles indisponibles restent `null` ; les échecs TCP sont conservés dans les rapports. Même une charge qualifiée avec des connexions réussies ne démontre pas une amélioration TBF/CAKE ni un gain Coopace. Le futur agrégateur devra appliquer les garde-fous et critères des trois blocs.

## Contrôle de panne et lancement

`check-crash` utilise le même pilote. Après la première phase idle, le superviseur tue le leader après la première écriture du premier transfert loaded. Il garde le leader non récupéré jusqu'au dernier signal collectif, récupère les trois outils orphelins, puis supprime uniquement les espaces possédés. Le rapport conserve la phase achevée et la phase interrompue. Une destruction du superviseur ou une panne de l'hôte reste hors garantie ; ce nettoyage ne restaure pas une passerelle réelle.

Prévisualisation et tests sans privilèges :

```sh
python3 -I -B scripts/lab-cake-campaign.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_campaign.py' -v
```

L'essai natif exige Linux, Python 3, `ip`, `tc`, `sysctl`, `ping`, UID 0 et les capacités `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, `CAP_NET_RAW`. Préparer avec le compte habituel trois binaires Go figés, sources/protocoles, versions et empreintes ; séparer les dossiers `check-crash` et `run`. Le lanceur appelle `sudo` pour ces deux commandes, capture stdout/stderr/codes, s'arrête sur erreur et refuse tout écrasement. Après l'essai, analyser les rapports et preuves, puis vérifier l'absence des processus, espaces et réservations avant de consigner la validation native. Conserver aussi une charge non qualifiée sans modifier les paramètres ni sélectionner une reprise favorable.
