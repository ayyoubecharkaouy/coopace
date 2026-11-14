# Session Go et restauration indépendante validées — 14 novembre 2026 (UTC)

## Résultat

Les deux modes du [pilotage de session](GATEWAY_SESSION.md) ont réussi depuis la révision `c2a196c3115ec0ddade2fab9eaeaf9ab22222cf5`. Les quatre codes conservés — contrôle et relecture, pour `check` puis `check-crash` — sont `0`. Une nouvelle relecture indépendante retrouve les mêmes rapports et vérifie 109 pièces par mode, sans opération réseau.

Le pilote Go sans privilèges importe une référence noqueue, exige l'accord local, demande l'application de CAKE, puis vérifie sa capture. Après sa sortie normale ou son arrêt forcé, le superviseur récupère son groupe, retire la file possédée et confirme le retour à l'état initial avant de supprimer ses ressources. Chaque rapport porte `complete`, `restored_and_closed` et `selected_state_matches` pour la comparaison sélectionnée.

| Observation | `check` | `check-crash` |
| --- | --- | --- |
| Début UTC | `2026-11-14T11:15:17.400161+00:00` | `2026-11-14T11:15:29.987091+00:00` |
| Fin UTC | `2026-11-14T11:15:29.083019+00:00` | `2026-11-14T11:15:41.673472+00:00` |
| UID opérateur consigné par Go | `1000` | `1000` |
| PID / code du pilote | `18996` / `0` | `19203` / `-9` (SIGKILL attendu) |
| Descendants récupérés | `0` | `0` |
| Événements Go / lignes de son journal | `4` / `6` | `3` / `4` |
| Trames de contrôle / événements | `4` / `4` | `3` / `3` |
| Journal superviseur / commandes | `104` / `45` | `104` / `45` |
| Restauration / nettoyage | Confirmés | Confirmés |
| Pièces vérifiées | `109` | `109` |

Le binaire vérifié refuse UID 0, UID effectif différent ou capacités effectives non nulles avant d'ouvrir le protocole. Les deux journaux consignent son lancement avec l'UID 1000 et aucune commande réseau exécutée par Go. Cela valide son démarrage après entrée dans le namespace et abandon des privilèges via le bootstrap ; les opérations privilégiées restent dans le superviseur. Aucun relevé indépendant de `/proc/PID/status` pendant l'exécution n'a été enregistré.

## Dialogue et retour initial

Chaque initialisation est liée au namespace retenu, à l'identifiant de réservation, au profil `cake-ipv4-lab-4mbit-v1`, à l'accord local explicite et au SHA-256 exact de `before.json`. Les trames et le journal durable Go concordent avec les événements du superviseur. Le profil initial est reconnu, et une nouvelle capture précède l'installation unique.

| Événement superviseur | Séquence dans les deux modes |
| --- | --- |
| Référence initiale vérifiée | `40` |
| Intention de lancement Go | `43` |
| `ready`, puis `apply_requested` | `44`, `45` |
| Intention d'ajout CAKE | `52` |
| File possédée vérifiée | `61` |
| `applied` reçu de Go | `62` |
| `release_requested` ou intention de SIGKILL | `63` |
| Groupe du pilote récupéré | `64` |
| Intention de retrait ciblé | `79` |
| Racine possédée retirée | `82` |
| Retour initial comparé et confirmé | `97` |
| Descripteurs de namespaces fermés | `98` |

Les commandes d'ajout/retrait suivent leurs intentions durables. Le retrait intervient après récupération du groupe ; la suppression des espaces intervient après comparaison et fermeture des références. Le journal Go normal finit par `awaiting_supervisor_recovery: true` ; il ne prétend pas avoir observé la restauration. En mode panne, le journal s'arrête après `applied` et le superviseur réalise seul la récupération.

Les cinq captures par mode (`before`, `pre-add`, `applied`, `pre-restore`, `after`) sont complètes pour les six sélections, avec identité du veth `wan` stable au sein de chaque session : index 2, MTU 1500 et flags 51. Elles montrent `noqueue 0:` → CAKE `10:` → `noqueue 0:`. Les classes et filtres sélectionnés restent vides. La CAKE de référence conserve ses options à 4 Mbit/s, avec compteurs octets/paquets nuls, conformément à l'absence de trafic de test. Les imports de captures CAKE peuvent retourner le refus métier attendu du profil initial noqueue ; la validation CAKE est distincte.

La nouvelle revue constate l'absence des six noms de namespaces, des deux réservations et des 92 PID distincts consignés :

- `check` : `cg-t3j6n1oj-c`, `cg-t3j6n1oj-g`, `cg-t3j6n1oj-s` ; `/tmp/coopace-guard.t3j6n1oj`.
- `check-crash` : `cg-23s_qf08-c`, `cg-23s_qf08-g`, `cg-23s_qf08-s` ; `/tmp/coopace-guard.23s_qf08`.

Les identités de namespaces sont vérifiées pendant chaque session. Leurs numéros d'inode ont été réutilisés entre ces deux sessions successives après libération ; ils ne constituent pas des identifiants globaux persistants. La revue n'a exécuté aucun nettoyage supplémentaire.

## Provenance et pièces

Dossier conservé : `.local/experiments/gateway-session-validation-c2a196c/`. Les 262 entrées figées et l'environnement concordent avant cette consignation documentaire. Les deux binaires `coopace-gateway` et `coopace-session-worker` portent Go 1.27.3, Linux amd64, la révision ci-dessus et `vcs.modified=false`. Les environnements déclarent `simulation: false`, Linux `7.0.0-43-generic`, Python `3.12.3` et tc `iproute2-6.1.0, libbpf 1.3.0`.

| Pièce | SHA-256 |
| --- | --- |
| `prepared.json` | `d1c1006a9b9be451491da263daffefbd766ed4d56fec2ff88fd02d54ff11f1d8` |
| `check/report.json` | `5756a7e81cf41f523f176492f56d2b49abdb95e0136518fc8c5fbb3af216b263` |
| `check/comparison.json` | `7f10007e8485bd058b9dd87c94544dd3ee8f70df57b988be01b8f03096a381a6` |
| `check/worker.jsonl` | `2db8fdb16c8157d84248f58f999019cfa166fafc61b42b6fd5910759e0ec8920` |
| `check-crash/report.json` | `4e04bee9978860c41560ceef9eadfa19b9cd5cc63b22c2fda602350ae5be4c5a` |
| `check-crash/comparison.json` | `a26ebd2f2298cb4f6cca18d68ad6e783f32ae71f348a21c98eef2ebf9da8c32c` |
| `check-crash/worker.jsonl` | `23b12294d1a668f4fb715b568c9c0cbf5369f6173303a2fe812523c7e00ce446` |

Les deux nouvelles relectures produisent `gateway_session_evidence_reviewed`, `protocol_verified: true`, `execution_source: native_control_report` et `native_certificate: false`. Les journaux de diagnostic Go et de relecture sont vides. `prepared.json` conserve son état historique `not_run` ; les rapports séparés contiennent les résultats réels. Aucun manifeste ni aucune preuve d'essai n'est modifié.

L'ancien dossier `gateway-session-validation-2676d43` reste conservé avec son refus préalable pour changement de noyau. Après le commit documentaire, la vérification globale du nouveau dossier refusera le changement de HEAD ; il ne faut pas réécrire le manifeste pour relancer. Les relectures des preuves restent possibles avec les sources et les binaires concordants.

## Portée et suite

Ces deux essais valident le raccordement natif du pilote Go à la restauration indépendante, sur ressources virtuelles neuves sans IP ni trafic applicatif. Le prochain contrôle fonctionnel devra associer ce pilotage à du trafic mesuré et vérifier son retour initial après arrêt/panne, dans un protocole distinct.

Les commandes publiques restent en lecture seule pour le réseau. La topologie du foyer, la couverture de son trafic, la restauration d'une configuration existante, IPv6/DNS, la panne du superviseur et la coupure machine ne sont pas validées. Aucun gain réseau propre au pilotage Coopace n'est démontré par cet essai ; `real_gateway_restoration_validated` reste faux et l'étape 4.2 reste ouverte.
