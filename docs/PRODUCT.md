# Produit, périmètre et critères de réussite

Ce document synthétise la direction de Coopace à partir du rapport de recherche V5 fourni au démarrage, rédigé sous l'ancien nom du projet. Il distingue le produit visé des fonctions effectivement disponibles dans ce dépôt.

## Problème à résoudre

Lorsque plusieurs appareils utilisent la même connexion, des files saturées ou un partage déséquilibré peuvent rendre les appels, les jeux ou la navigation moins réactifs. Coopace vise une meilleure latence sous charge, une expérience plus stable et un partage raisonnable entre appareils.

La contribution à évaluer est une coordination locale qui observe, propose une intervention autorisée, mesure son effet collectif et revient en arrière si nécessaire. Son bénéfice supplémentaire par rapport aux outils existants reste à démontrer.

## Forme du produit final

Coopace est un produit composé d'applications adaptées aux rôles et aux systèmes :

| Composant | Rôle dans le produit |
| --- | --- |
| Passerelle | Observer et gérer le trafic Internet qui la traverse réellement. Nécessaire pour la gestion globale des files du foyer. |
| Agent | Faire participer un appareil volontaire au groupe et fournir les mesures ou actions réellement disponibles sur son système. |
| Tableau de bord | Consulter les appareils, les mesures, les interventions et les résultats depuis une interface locale. |
| ML facultatif | Proposer des estimations après validation, sous le contrôle des règles déterministes. |

Tous les appareils n'installent pas tous les composants. Un participant actif installe un agent compatible ; un appareil sans agent peut bénéficier des files gérées par la passerelle. Une même machine peut cumuler les rôles d'agent et de passerelle.

Un PC Linux n'est pas obligatoire parmi les membres du groupe. Les capacités de la passerelle dépendent cependant du moteur réseau effectivement intégré et validé sur son système. Le fonctionnement de base visé est local et ne nécessite pas de serveur cloud.

## État réel des composants

| Fonction ou cible | État actuel |
| --- | --- |
| Modèles appareil, rôle et capacités | Implémentés et testés sous Linux. |
| Agent local Linux | État, mesures et identité persistante ; premier échange TLS borné entre deux instances implémenté et testé en mémoire. Son essai TCP réel reste à confirmer. |
| Agent local Windows | Compilation Windows amd64 validée ; exécution native non vérifiée, collecte des compteurs et stockage protégé de clé non implémentés. |
| Application Android | Prévue ; aucun APK ni intégration native disponible. |
| Groupe coopératif | Prototype Linux à deux pairs : approbation et consentement persistés, TLS mutuel et observations facultatives. Tests en mémoire validés, TCP réel à confirmer ; coordination avancée non implémentée. |
| Passerelle Linux/OpenWrt | Diagnostic Linux en lecture seule implémenté ; inventaire partiel dans l'environnement isolé et complet dans la passerelle virtuelle lors du premier essai natif ICMP/TCP. Gestion de trafic et restauration non implémentées ; OpenWrt non validé. |
| Passerelle Windows | Cible à étudier ; moteur et performances non validés. |
| Tableau de bord et relais | Prévus ; aucune implémentation. |
| ML | Périmètre documenté ; aucun dataset ni modèle entraîné dans ce dépôt. |

La présence d'un modèle Android ou Windows dans les tests ne valide pas l'application correspondante. La compilation validée et l'exécution future de `coopace status` sous Windows ne prouvent pas la faisabilité d'une passerelle Windows. Les résultats et essais natifs à effectuer sont décrits dans [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md).

Les observations de l'étape 3.1 portent sur les interfaces visibles par le processus. Elles ne prouvent ni une couverture Internet du foyer, ni une mesure de capacité WAN, ni une amélioration réseau. Voir leurs [limites précises](OBSERVATIONS.md).

L'étape 3.2 mesure l'établissement TCP, pas un RTT ICMP ou une perte de paquets. Le [protocole de référence](LATENCY.md) prépare les comparaisons sans démontrer de gain ; aucune mesure WAN ni comparaison après optimisation n'a encore été validée.

L'[étape 3.3](IDENTITY_AND_GROUP.md) prépare les fondations du groupe. Le [premier échange de l'étape 3.4](GROUP_EXCHANGE.md) exige approbation mutuelle, TLS et consentement local ; posséder une identité ou valider un JSON ne suffit pas. La clé privée reste locale et le partage est désactivé par défaut. Chaque échange se termine par une déconnexion.

À chaque jalon, mettre à jour cette table et les états du README et de la feuille de route en distinguant ce qui est prévu, compilé, testé et mesuré.

## Premier résultat réseau utile à viser

Le premier agent en ligne de commande est un socle logiciel. Le premier résultat réseau utile sera un prototype de passerelle observable et réversible, évalué face à une configuration de référence.

Le [diagnostic de l'étape 4.1](GATEWAY_DIAGNOSTIC.md) prépare cette évaluation. La présence d'outils, d'une route par défaut ou du forwarding ne démontre ni une couverture du foyer ni un bénéfice ; le choix de la plateforme d'intervention et du chemin réel reste à consigner.

Il devra permettre de :

1. Définir le trafic couvert et mesurer la connexion au repos et sous charge.
2. Identifier un problème mesurable avant de proposer un changement.
3. Appliquer manuellement une politique conservatrice sur un moteur validé, avec sauvegarde et restauration.
4. Comparer le résultat à la référence, en tenant compte des autres appareils et des ressources consommées.
5. Présenter ce qui s'est amélioré, dégradé ou n'a pas changé.

Un groupe minimal de mesure peut préparer cette évaluation. La coordination avancée, une interface complète, les relais automatiques et le ML attendront ce premier résultat. L'absence de groupe complet ne doit pas bloquer l'évaluation du moteur de passerelle.

La [préparation de l’étape 4.2](GATEWAY_BASELINE.md) ajoute un export JSON local d’inventaire et un modèle de protocole. La plateforme et la topologie du foyer, ses seuils et ses références au repos/sous charge restent à confirmer ; l'inventaire seul ne fournit aucune de ces mesures.

La comparaison hors ligne des rapports TCP au repos/sous charge est disponible via `latency compare`. Elle vérifie les paramètres et les statistiques, sans vérifier le contexte réel ni attribuer un gain à Coopace. L'étape expérimentale reste ouverte.

Le [laboratoire virtuel de développement](VIRTUAL_LAB.md) prépare un chemin IPv4 contrôlé entre des espaces réseau Linux neufs. Le mode `run-tcp` ajoute cinq tentatives TCP vers une cible temporaire bornée, sans générer de charge de saturation. Le script ne raccorde aucun appareil du foyer et n'applique pas de politique de files. Un [premier essai natif Linux](VALIDATION_VIRTUAL_LAB_2026-10-29.md) confirme le passage ICMP/TCP et le nettoyage normal. Il ne valide pas un moteur de files ni un gain de performance réseau.

Le [générateur de trafic synthétique](VIRTUAL_LOAD.md) prépare ensuite un transfert de 8 Mio, limité en débit moyen et en durée. Un [premier transfert natif](VALIDATION_VIRTUAL_LOAD_2026-10-29.md) confirme les 8 Mio envoyés et reçus et le nettoyage normal ; le code de sortie exact `0` est conservé dans le compte rendu local. Le mode [`run-series`](VIRTUAL_SERIES.md) prépare la mesure de latence simultanée et trois paires de séries, avec contrôle du recouvrement et conservation des échecs. Un [premier essai natif](VALIDATION_VIRTUAL_SERIES_2026-10-29.md) confirme 60 réussites sans échec, les trois transferts, le recouvrement et le nettoyage normal. Ce trafic de laboratoire ne constitue pas une référence WAN ni une saturation démontrée.

Le [superviseur indépendant du laboratoire](LAB_GUARD.md) dispose de deux [contrôles natifs validés](VALIDATION_LAB_GUARD_2026-10-29.md) : fin normale et mort forcée du pilote, avec récupération des descendants et retrait des espaces possédés. Il s'agit d'un outil de développement distinct de l'application passerelle ; son intégration aux séries TBF est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md), sans restaurer la configuration d'un réseau existant.

Le [protocole du goulot virtuel](VIRTUAL_BOTTLENECK.md) définit TBF/FIFO à 4 Mbit/s et ses critères de congestion. Le [contrôle du cycle de vie de la file](LAB_QUEUE.md) est implémenté sous le superviseur et [validé en natif](VALIDATION_LAB_QUEUE_2026-10-29.md) sur un lien désactivé, avec les paramètres effectifs relus et le nettoyage vérifié. Le [rapport optionnel de réception et les statistiques TBF](LAB_INSTRUMENTATION.md) sont implémentés et [validés en natif](VALIDATION_LAB_INSTRUMENTATION_2026-10-29.md) pour un transfert local et des statistiques à zéro sur liens désactivés. Le [contrôle fonctionnel du chemin actif](LAB_ACTIVE.md) intègre maintenant un transfert, dix sondes, des statistiques périodiques et le superviseur ; sa [première validation native](VALIDATION_LAB_ACTIVE_2026-10-30.md) confirme les 8 Mio reçus, dix connexions réussies et le nettoyage normal ou après mort forcée. La [campagne de trois paires avec file](LAB_CAMPAIGN.md) est [validée en natif](VALIDATION_VIRTUAL_BOTTLENECK_2026-10-30.md) avec congestion observée selon le protocole v1. Le [protocole comparatif TBF/CAKE statique](CAKE_COMPARISON.md) fixe maintenant les paramètres, les six campagnes et leurs critères avant collecte. Le [contrôle CAKE sur lien désactivé](LAB_CAKE.md) est [validé en natif](VALIDATION_LAB_CAKE_2026-10-30.md) pour la configuration, les statistiques et le nettoyage normal ou après mort forcée. Le [contrôle fonctionnel CAKE actif](LAB_CAKE_ACTIVE.md) est [validé en natif](VALIDATION_LAB_CAKE_ACTIVE_2026-10-30.md) pour un transfert complet et le nettoyage normal ou après mort forcée. La comparaison et les validations sur le réseau réel restent à réaliser avant de revendiquer une gestion du trafic dans le produit.

## Références et mesures indispensables

| Expérience | Comparaisons nécessaires |
| --- | --- |
| Gestion des files | Configuration initiale, moteur configuré manuellement, puis pilotage Coopace sans ML. CAKE/SQM constitue la référence du rapport pour Linux/OpenWrt. |
| Classification ou capacité variable | Ajouter qosify ou cake-autorate lorsque leur usage correspond au scénario. |
| Relais | Chemin direct, relais manuel, sélection déterministe, puis éventuelle sélection assistée par ML. |
| ML | Décisions sans ML, modèle évalué hors des conditions d'entraînement, puis observation seule avant toute activation. |

Les mesures devront couvrir la latence au repos et sous charge (p50, p95, p99), les pertes et la gigue, le débit utile, l'équité et la consommation CPU/mémoire. La couverture réelle, IPv4/IPv6, DNS et le comportement lors d'une panne ou d'un retour arrière devront aussi être vérifiés. Les métriques applicatives seront recueillies avec autorisation ou à partir de tests synthétiques.

Chaque expérience définira ses seuils d'acceptation avant l'essai, répétera les mesures et précisera les conditions et limites. Aucun pourcentage de gain n'est annoncé à ce stade.

## Conditions de poursuite

- Conserver une solution simple si le moteur existant apporte déjà le bénéfice et que la surcouche ne l'améliore pas.
- Différer l'automatisation si la restauration, la couverture du trafic ou le coût système ne sont pas maîtrisés.
- Garder un relais manuel ou le retirer s'il dégrade les résultats ; vérifier l'existence d'un véritable chemin alternatif.
- Intégrer le ML uniquement si son bénéfice collectif est reproductible au-delà des références pertinentes.
- Prévoir l'abstention lorsqu'aucun problème n'est mesuré ou que les observations sont insuffisantes.

## Limites à conserver

Coopace ne dépasse pas la capacité physique de l'accès Internet et ne contrôle pas le trafic qui évite son point d'application. Plusieurs appareils sur un même accès ne créent pas une nouvelle capacité WAN.

Le projet ne prévoit ni interception TLS, ni déchiffrement des contenus, ni réhébergement de vidéos privées, ni identification certaine des applications chiffrées. Les relais et leur usage demandent un consentement distinct ; le ML reste facultatif.

Voir l'[architecture](ARCHITECTURE.md), les [choix techniques](TECH_STACK.md), la [feuille de route](ROADMAP.md) et les [instructions de développement](DEVELOPMENT.md).
