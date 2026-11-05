# Campagne répétée après Go validée en natif — 5 novembre 2026 (UTC)

## Résultat et portée

Les deux modes du [contrat v1.1](LAB_CAKE_GO_CAMPAIGN.md) ont réussi depuis le commit `1247848021025e8c353fec2ab0609b65ddca72da`. Les codes `run`, `check-crash` et relecture sont `0`. Une seconde revue indépendante retrouve les mêmes faits et les mêmes 46 empreintes de pièces, sans relancer de commande réseau.

La campagne confirme Go DOWN → activation des mêmes ressources → passage IPv4 → trois paires repos/charge, puis le nettoyage normal et après panne dans un laboratoire distinct. Elle qualifie ce scénario de laboratoire CAKE statique ; elle ne compare pas deux politiques et ne démontre pas un bénéfice propre au pilotage Coopace.

| Observation | `run` | `check-crash` |
| --- | --- | --- |
| Go | Code 0, 14 appels, 36 lignes durables | Code 0, 14 appels, 36 lignes durables |
| Passage IPv4 | Une requête sans réponse sans forwarding, puis trois requêtes/réponses avec forwarding | Mêmes critères confirmés |
| Phases | Six complètes : idle/loaded, loaded/idle, idle/loaded | Une idle complète, puis interruption au premier ready chargé |
| Connexions mesurées | 60 réussites, zéro échec | Aucun verdict de mesure pour la campagne partielle |
| Réceptions normales | Trois fois 8 388 608 octets, soit 24 Mio utiles | Aucun résultat final chargé attendu |
| Code du pilote | 0 | -9, SIGKILL attendu |
| Helpers orphelins récupérés | 0 | 3 |
| Échantillons globaux | 232 | 15 |
| Nettoyage | Confirmé | Confirmé |
| Décisions | `technical_valid: true`, charge `qualified`, connexions `confirmed` | `technical_valid: null`, charge/connexions `not_assessed` |

Le [premier essai refusé 0440c5d](REVIEW_CAKE_GO_CAMPAIGN_FAILURE_2026-11-05.md) reste conservé. La correction utilise la durée monotone entre première lecture ayant progressé et EOF, déjà fournie par Go. Le présent dossier a été préparé et exécuté à nouveau ; les anciens résultats ne sont pas requalifiés.

## Mesures descriptives

Le profil reste `cake-ipv4-lab-4mbit-v1` : racine CAKE `10:` sur `wan`, bande passante nominale 4 Mbit/s, producteur iproute2-6.1.0. Chaque mode possède trois namespaces neufs et une installation CAKE par Go, conservée pendant ses phases.

| Paire | p50 idle (ms) | p50 loaded (ms) | Écart loaded − idle (ms) | Débit reçu (octets/s) |
| --- | --- | --- | --- | --- |
| 1 | 0,336129 | 1,481145 | +1,145016 | 478 116,41 |
| 2 | 0,202583 | 1,348554 | +1,145971 | 478 096,63 |
| 3 | 0,204347 | 1,403331 | +1,198984 | 478 096,74 |

Les trois débits sont dans les bornes fixées [350 000 ; 525 000] octets/s. Les stabilisations avant sondes sont 1 262,820 ms, 1 274,852 ms et 1 429,506 ms. Les fenêtres chargées contiennent respectivement huit, huit et sept relevés CAKE, avec progression de 1 004 514, 1 002 930 et 890 622 octets de file pendant les sondes.

Les écarts p95/p99 sont respectivement +1,531429 ms, +0,770233 ms et +0,638917 ms. Les percentiles sont recalculés depuis dix tentatives par condition ; les valeurs hautes restent exploratoires. Aucun seuil d’augmentation de latence ou de backlog durable n’est imposé à CAKE dans ce protocole.

Les outils de chaque phase sont neufs et récupérés avant advance. Les doubles lectures vides, la séparation d’au moins 500 ms et l’autorisation sous trois secondes depuis end observé ont été revérifiées. Les options et identités des liens restent conformes et les compteurs monotones.

| Différences de compteurs de campagne | `run` | `check-crash` |
| --- | --- | --- |
| Octets / paquets | 26 330 184 / 17 634 | 122 062 / 123 |
| Drops / overlimits / requeues | 436 / 46 731 / 0 | 4 / 300 / 0 |

Ces compteurs de file ne sont ni le volume utile reçu ni une mesure des pertes TCP. En mode panne, du trafic a déjà été généré avant la mort du pilote ; l’absence de résultat chargé final n’efface pas ces compteurs.

## Nettoyage et provenance

| Mode | Réservation supprimée | Namespaces supprimés |
| --- | --- | --- |
| `run` | `/tmp/coopace-guard.16vtb_a6` | `cg-16vtb_a6-c/g/s` |
| `check-crash` | `/tmp/coopace-guard.eao3u2p_` | `cg-eao3u2p_-c/g/s` |

Les six noms sont absents sous `/run/netns` et `/var/run/netns`. Les deux réservations et les 60 PID distincts consignés sont absents lors de la seconde revue. Aucune commande de nettoyage supplémentaire n’a été exécutée par le relecteur.

Dossier : `.local/experiments/go-campaign-native-validation-1247848/`. Préparation : `2026-11-05T16:53:27.526685+00:00`. Début du lanceur : `2026-11-05T17:08:51.890329+00:00`. Première revue : `2026-11-05T17:10:53.074201+00:00`. Seconde revue : `2026-11-05T18:37:39.336814+00:00`.

Les 351 entrées figées, les objets Git, les neuf outils et les quatre provenances Go concordent. Les binaires indiquent Go 1.27.3, Linux amd64, le commit source et `vcs.modified=false`. L’hôte utilise Linux `7.0.0-42-generic` et Python 3.12.3 ; les producteurs tc/ping correspondent à la préparation.

| Pièce | SHA-256 |
| --- | --- |
| `run/report.json` | `a8b509902e057eca06b147c9b4b60ebf461dd6e96c2076f5af059fcf58ec4c16` |
| `check-crash/report.json` | `7c3220b84a9c331e1ecd37aa188475735d62c2113a34612330c4f747dad7e65b` |
| `validation.json` | `afee5e09ebba4d81cc37722630d078fe3fdbd0e06fc3b7320bfbe4d366a9b492` |

Le relecteur automatique conserve son comportement sans écriture : `campaign_evidence_reviewed`, `native_certificate: false`. Après la seconde relecture et l’examen des résultats, un certificat local a été publié manuellement avec création exclusive : `state: native_cake_go_campaign_validated`, `native_certificate: true`, `publication: manual_after_independent_replay`. Les 46 pièces précédentes restent inchangées. `prepared.json` garde son état historique `not_run`.

Après la mise à jour de la documentation courante, une nouvelle vérification intégrale des entrées exigera de restituer les fichiers suivis du commit source à leurs chemins préparés. Les manifestes et preuves ne doivent pas être réécrits pour suivre les nouveaux documents.

## Suite et limites

Cette validation clôt la collecte répétée du laboratoire Go/CAKE et sa récupération après panne du pilote de trafic. L’étape 4.2 reste ouverte pour la référence WAN et le trafic réellement couvert. La passerelle du produit, la sauvegarde/restauration d’un réseau existant, IPv6/DNS, l’équité et le coût système restent à valider avant automatisation. La panne de Go pendant un outil actif et la destruction du superviseur ne sont pas couvertes par ce contrôle.

Les prochains travaux doivent préparer un premier chemin réel observable et réversible. Aucun gain de capacité Internet, bénéfice du foyer, optimisation coopérative ou résultat ML n’est démontré par cette seule campagne statique.
