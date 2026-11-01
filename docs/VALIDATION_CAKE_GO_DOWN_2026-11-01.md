# Premier contrôle natif CAKE Go DOWN — 1er novembre 2026 (UTC)

## Résultat et portée

Les deux contrôles du [protocole natif](LAB_CAKE_GO_NATIVE.md) ont réussi avec le véritable processus Go, l’entrée réseau avant son démarrage et les outils `ip`/`tc` du laboratoire. La relecture automatique puis une seconde revue hors ligne ont confirmé les preuves, sans relancer de contrôle réseau.

| Contrôle | Code superviseur | Code OS Go | Appels d’outils | Lignes du journal | Descendants récupérés |
| --- | --- | --- | --- | --- | --- |
| `check` | 0 | 0 | 14 | 36, jusqu’à `worker_exit` | 0 |
| `check-crash` | 0 | -9, SIGKILL attendu | 11 | 27, jusqu’à `applied` | 0 |

Le code de relecture est `0`. Les deux rapports portent `state: complete`, `cleanup_verified: true`, `traffic_generated: false`, `active_path_verified: false` et `link_state: DOWN`.

Le résultat valide le cycle supervisé d’ajout/relecture de CAKE sur un veth neuf désactivé. Il ne mesure ni latence, débit utile, équité, bénéfice propre à Coopace ou fonctionnement sur le réseau du foyer.

## Séquence et relevés confirmés

Chaque contrôle conserve exactement `ready`, puis `applied`, avec jeton conforme et référence `cake-ipv4-lab-4mbit-v1`. Le journal confirme l’acceptation du contexte réseau avant tout outil, deux relevés initiaux vides et un seul ajout après `apply_received`. Les sorties d’outils et le relevé `applied` concordent ; tous les appels consignés se terminent avec le code `0`, sans troncature ni erreur.

Le mode normal conserve quatre lectures de lien et quatre lectures d’adresses ; le mode panne en conserve trois de chaque. Dans chaque contrôle, `wan` reste un veth DOWN, sans drapeau `UP` et avec `addr_info: []`. Son indice, l’indice du pair, le MTU de 1500 et la MAC restent stables pendant le contrôle. Les MAC diffèrent entre les deux liens créés.

Les durées des outils Go vont de 3,698660 à 4,989079 ms en mode normal et de 3,710832 à 4,157332 ms en mode panne. Les journaux Go s’étendent de `00:19:35.106522220Z` à `00:19:35.305306441Z`, puis de `00:19:36.029462879Z` à `00:19:36.140124519Z`.

Trois relevés CAKE Go sont conformes : deux en mode normal et un en mode panne. Les quatre relevés indépendants du superviseur, après ajout et après arrêt dans chaque contrôle, confirment les mêmes configurations et statistiques. Leurs durées vont de 10,741307 à 10,906117 ms.

| Paramètre effectif | Valeur |
| --- | --- |
| Racine | CAKE `10:` sur `wan` |
| Producteur | iproute2-6.1.0, libbpf 1.3.0 |
| Bande passante nominale | 500 000 octets/s, soit `4mbit` |
| Classe et isolation | `besteffort`, `flows` |
| RTT de réglage / mémoire | 100 000 µs / 1 048 576 octets |
| Options | raw, overhead nul, egress, sans NAT/wash/filtre ACK, `split_gso: true`, masque `"0"` |

Les omissions de `mpu`, `atm` et `autorate` sont justifiées par le profil du producteur. Les cinq compteurs racine, les jauges backlog/qlen et la mémoire utilisée rapportée restent nuls. Les deux différences de compteurs sont disponibles et nulles. Ces valeurs sont cohérentes avec un lien sans trafic ; les paramètres non nuls de CAKE ne deviennent pas des mesures de débit ou de latence.

## Nettoyage et limites de panne

Le superviseur confirme la récupération du processus Go, la relecture après arrêt, la fermeture des références puis le retrait des espaces possédés. Les journaux stderr concordent avec les réservations ; le diagnostic stderr du processus Go est vide dans les deux modes.

| Contrôle | Réservation supprimée | Noms supprimés |
| --- | --- | --- |
| `check` | `/tmp/coopace-guard.2vg28jn3` | `cg-2vg28jn3-c/g/s` |
| `check-crash` | `/tmp/coopace-guard.zxvcu0m5` | `cg-zxvcu0m5-c/g/s` |

Les six noms sont absents sous `/run/netns` et `/var/run/netns`. Les deux réservations et les 27 PID consignés — deux processus Go et 25 outils — sont absents au moment de la revue.

Dans les deux lancements, la cible observée est distincte de l’origine : device 5, inode cible 4026532716 contre origine 4026531833. Le noyau a réutilisé l’inode cible entre les contrôles successifs ; les noms et réservations sont distincts. L’identité retenue sert à vérifier une ressource pendant sa durée de possession, pas à identifier globalement des expériences successives.

Le nombre nul de descendants récupérés est attendu ici : SIGKILL intervient après `applied` et après récupération des outils. **La mort du véritable processus Go pendant qu’un outil est encore actif reste à valider séparément.** La destruction du superviseur, une panne de l’hôte, des références détenues par un processus étranger et la restauration d’une passerelle existante restent hors garantie.

## Provenance et conservation

Commit source : `e104994a15120814ae58e9b38f9bde1f6261bc7b`. Dossier local : `.local/experiments/go-native-validation-e104994/`. Début du lanceur : `2026-11-01T00:19:26.857927+00:00`. Première relecture : `2026-11-01T00:19:38.077951+00:00`.

Les 263 empreintes d’entrée sont conformes et les sources suivies correspondent au commit. La provenance du binaire et du journal indique Go 1.27.3, Linux amd64, Git au commit préparé et `vcs.modified: false`. L’exécution utilise Linux `7.0.0-38-generic` et Python 3.12.3. Les empreintes des 31 pièces consignées dans `validation.json` ont également été revérifiées.

| Pièce | SHA-256 |
| --- | --- |
| Binaire Go | `754e2e00575744f34879f1722c6349b912a254c8ca9ccdef8759672b8f28a7e9` |
| `check/report.json` | `25d3e100a206088e17de8ffcc8b14165ae2ee22978b3f7bf336cb2fde3589384` |
| `check-crash/report.json` | `4f1efa5251d758d459480b16c2600b504d42b34cda9e4369e7489803d9059580` |

Les fichiers figés et données brutes restent inchangés. `prepared.json` conserve son état historique `not_run` ; `validation.json` porte le résultat natif. Les mises à jour documentaires ultérieures diffèrent des entrées figées : pour reproduire leur vérification complète, utiliser le checkout du commit source, sans modifier le manifeste de cette expérience.

La prochaine activité définit le contrôle Go sur chemin actif, avec transfert, mesures, faits observés et récupération des processus. Le backend actuel exige un lien DOWN ; cette extension demande son propre contrat et ses propres validations. La planification publique reste une simulation et l’étape 4.2 demeure ouverte pour le foyer et sa restauration.
