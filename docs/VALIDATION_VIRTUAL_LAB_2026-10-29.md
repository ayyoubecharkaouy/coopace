# Validation native du laboratoire IPv4 — 29 octobre 2026

## Résultat et portée

Les modes `run` et `run-tcp` ont été exécutés depuis le terminal de l'utilisateur sur son PC Linux x86_64, avec `sudo`. Les deux codes de sortie conservés valent `0`. Le premier chemin IPv4 synthétique client → passerelle → serveur et la cible TCP sont validés dans ce scénario.

L'étape 4.2 reste ouverte : cet essai ne génère aucune charge de saturation et ne valide ni une référence WAN, ni une gestion des files, ni la restauration d'une passerelle réelle. Il ne valide pas non plus l'échange TLS du groupe, dont le test TCP reste distinct.

## Provenance conservée

- Commit de préparation et de compilation : `c8961242d9c136a1aa0351ea81b272e918039550`.
- Diagnostic : Go `go1.27.3`, Linux amd64, `vcs_modified: false`.
- Fin de collecte de l'inventaire : `2026-10-29T18:09:24.850492252Z`.
- Série TCP : `2026-10-29T18:09:30.152398206Z` à `2026-10-29T18:09:31.161441858Z`.
- Dossier local : `.local/experiments/virtual-validation-c896124-20261029T144154Z/`.

Ce dossier contient `prepared.json`, `scenario.md`, `plan.txt`, les deux rapports JSON, les journaux et codes de sortie, puis `validation.json` avec les empreintes des pièces vérifiées. Les trois empreintes binaires courantes correspondent à celles de la préparation. Le fichier de préparation reste historique : ses valeurs `not_run` décrivent l'état avant l'essai ; `validation.json` consigne le résultat ultérieur.

Les données brutes restent locales et exclues de Git. Ce document suivi conserve la synthèse et les empreintes des deux rapports :

| Fichier | SHA-256 |
| --- | --- |
| `inventory.json` | `c19e18a00e037c0d9c861814ef439588432cbf5b10afc4c4b86de498e1ea7b08` |
| `tcp.json` | `d60abdc7214f10f89a709cb24dd6bcacddc2c83026b4873a8698f96ea5a2d994` |

## Vérifications effectuées

| Contrôle | Résultat |
| --- | --- |
| Sans forwarding IPv4 | Aucune réponse à la sonde dans chacun des deux journaux. |
| Après activation du forwarding | Trois réponses ICMP sur trois dans chaque exécution. |
| Inventaire dans la passerelle virtuelle | `partial: false`, interfaces `lo`, `lan`, `wan` actives, forwarding IPv4 et CAP_NET_ADMIN effectifs. |
| Routage par défaut | Listes IPv4 et IPv6 vides, conformément au scénario isolé sans Internet. |
| Files observées | `noqueue` sur les trois interfaces ; aucune configuration CAKE/SQM appliquée. |
| Mesure TCP | Cinq tentatives vers `10.203.0.6:46001`, cinq réussites, zéro échec. |
| Serveur TCP | Journal de fin normale après cinq connexions acceptées. |
| Rapport TCP | Accepté par le lecteur strict existant ; statistiques également recalculées depuis les cinq essais. |
| Nettoyage normal | Journal de suppression réussie dans les deux exécutions ; les six noms et les deux réservations temporaires ne sont plus visibles depuis l'environnement de développement. |

Le lecteur de comparaison a chargé le rapport dans ses deux entrées, puis l'a refusé comme prévu pour une comparaison `idle`/`loaded`, car sa condition est `unspecified`. Les données brutes n'ont pas été réétiquetées.

Les espaces appartiennent à deux créations indépendantes : `cp-2OoB6Vkf-c/g/s` pour ICMP et `cp-neO92mzp-c/g/s` pour TCP. Les suppressions et absences de noms ne constituent pas un test de restauration indépendante, ni une preuve de disparition d'un espace encore référencé par un processus étranger. Les erreurs et interruptions restent couvertes par les tests simulés ; elles n'ont pas été injectées pendant cet essai natif.

## Durées TCP descriptives

| Statistique | Millisecondes |
| --- | --- |
| Minimum | 0.213127 |
| p50 | 0.244443 |
| p95 | 4.443816 |
| p99 | 4.443816 |
| Maximum | 4.443816 |

Avec cinq échantillons, p95 et p99 sont le maximum observé. Ces durées d'établissement TCP proviennent d'espaces partageant le même noyau ; elles ne représentent pas la latence Internet ni un gain d'optimisation. La condition `unspecified` n'établit pas le repos de la machine physique.

## Prochaine activité

Préparer maintenant une charge synthétique contrôlée et des séries répétées, en fixant leurs paramètres, critères et limites avant de mesurer. Les essais au repos/sous charge et les métriques complémentaires restent nécessaires. Avant toute première politique de files, développer et vérifier une restauration adaptée, indépendante du processus de pilotage.

IPv6, DNS, UDP/QUIC, équité, débit utile, ressources, appareils physiques et fonctionnement sous panne restent hors de la validation présente. Voir [VIRTUAL_LAB.md](VIRTUAL_LAB.md), [GATEWAY_BASELINE.md](GATEWAY_BASELINE.md) et [ROADMAP.md](ROADMAP.md).
