# Campagne Go 0440c5d refusée : durée de réception

## Essai conservé

Le dossier `.local/experiments/go-campaign-native-validation-0440c5d/` conserve la première campagne native de ce chemin Go, préparée depuis le commit `0440c5d`. Le lanceur s’est arrêté après `run.exit: 1`. Le mode `check-crash` et la relecture automatique n’ont pas été lancés.

Le rapport original garde `state: failed`, `technical_valid: false` et l’erreur `Durée de réception incompatible avec les horodatages.`. Son SHA-256 est `409cd4ec972c83d76de8d0ca8654642a494049b2506413e728e0f97b2539fae4`.

## Faits conservés dans les preuves

| Élément | Observation |
| --- | --- |
| Go | Code 0, 14 appels, 36 lignes de journal |
| Pilote de campagne | Code 0, six phases collectées |
| TCP | 60 réussites, zéro échec |
| Réceptions | Trois volumes exacts de 8 388 608 octets |
| Collecte | 234 échantillons globaux |
| Récupération | Deux groupes arrêtés ; nettoyage confirmé |
| Bilan global | Refus lors du calcul après collecte et nettoyage |

Ces faits ne suffisent pas à valider les deux modes du protocole. Aucun certificat natif n’est publié et le rapport original reste inchangé.

## Cause du refus

Le récepteur Go mesure déjà `receive_elapsed_ms` avec l’horloge monotone, depuis la première lecture ayant progressé jusqu’à la lecture indiquant EOF. Le test Go `TestReceiptTimesIncludeEOFAfterLastBytes` vérifie explicitement l’attente d’EOF. `last_read_at` indique seulement le dernier octet reçu ; `finished_at` indique EOF.

L’évaluateur de campagne recalculait à tort cette durée depuis `last_read_at - first_read_at`, puis exigeait un accord relatif de 1e-9. Pour les trois transferts, la durée de réception déclarée dépasse cette différence de 3 428 ns, 3 888 ns et 2 720 ns. L’écart correspond ici à l’attente de fin du flux, après le dernier octet. Par ailleurs, les UTC sérialisés ne conservent pas la composante monotone des horloges Go.

Le récepteur, les volumes et les seuils de qualification ne sont pas modifiés. La correction utilise la durée monotone déclarée, déjà positive, bornée et reliée au débit par le validateur du flux, pour recalculer exactement le débit reçu. Les UTC gardent leurs contrôles d’ordre et de fenêtre ; leur soustraction ne remplace pas la durée monotone.

## Correction et nouvelle collecte

Le [contrat v1.1](LAB_CAKE_GO_CAMPAIGN.md) clarifie cette définition avant le nouvel essai, conformément à l’[instrumentation existante](LAB_INSTRUMENTATION.md). Ordre des phases, volumes, délais et bornes de débit [350 000 ; 525 000] octets/s sont conservés.

Une fixture de régression extraite de ce rapport conserve les six résultats et les relevés initiaux, ceux des fenêtres de sondage et les derniers relevés de vidage. Elle porte le hash du rapport source, le commit et l’état original refusé ; elle ne contient aucun certificat. Les tests ajoutent l’attente d’EOF, la différence entre UTC et durée monotone, et le refus des débits incohérents ou durées non positives.

Un recalcul rétrospectif retrouve des mesures exploitables, trois charges qualifiées et 60 connexions confirmées. Une copie temporaire du rapport, avec son seul bilan recalculé, passe aussi la relecture Go/IPv4/phases. Ce diagnostic ne requalifie pas le dossier original, ne remplace pas le mode de panne manquant et ne constitue pas une nouvelle validation native.

Les 35 fichiers du dossier original ont été réempreintés pour vérifier leur conservation. Le nouvel essai doit être préparé dans un autre dossier, depuis le commit corrigé, puis exécuter les deux modes et leur relecture.

## Vérification de la correction

Les 54 tests ciblés de calcul, rapport global, relecture globale, phases et dialogue passent en 143,954 s, dont quatre nouveaux tests de régression. Les deux tests Go ciblés de réception (attente d’EOF et durée nulle explicite) passent également. La suite complète n’a pas été relancée pour cette correction ciblée. Les 35 fichiers du dossier refusé conservent leurs empreintes après diagnostic ; les résultats originaux ne sont pas réécrits.
