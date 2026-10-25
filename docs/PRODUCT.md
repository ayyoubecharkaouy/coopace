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
| Agent local Linux | Commandes `status`, `observe` et d'aide implémentées et testées ; premières mesures de compteurs par interface. |
| Agent local Windows | Compilation Windows amd64 validée ; exécution native non vérifiée et collecte des compteurs non implémentée. |
| Application Android | Prévue ; aucun APK ni intégration native disponible. |
| Groupe coopératif | Prévu ; identité, adhésion, authentification et échanges restent à développer. |
| Passerelle Linux/OpenWrt | Prévue ; aucune gestion de trafic implémentée dans ce dépôt. |
| Passerelle Windows | Cible à étudier ; moteur et performances non validés. |
| Tableau de bord et relais | Prévus ; aucune implémentation. |
| ML | Périmètre documenté ; aucun dataset ni modèle entraîné dans ce dépôt. |

La présence d'un modèle Android ou Windows dans les tests ne valide pas l'application correspondante. La compilation validée et l'exécution future de `coopace status` sous Windows ne prouvent pas la faisabilité d'une passerelle Windows. Les résultats et essais natifs à effectuer sont décrits dans [WINDOWS_VALIDATION.md](WINDOWS_VALIDATION.md).

Les observations de l'étape 3.1 portent sur les interfaces visibles par le processus. Elles ne prouvent ni une couverture Internet du foyer, ni une mesure de capacité WAN, ni une amélioration réseau. Voir leurs [limites précises](OBSERVATIONS.md).

À chaque jalon, mettre à jour cette table et les états du README et de la feuille de route en distinguant ce qui est prévu, compilé, testé et mesuré.

## Premier résultat réseau utile à viser

Le premier agent en ligne de commande est un socle logiciel. Le premier résultat réseau utile sera un prototype de passerelle observable et réversible, évalué face à une configuration de référence.

Il devra permettre de :

1. Définir le trafic couvert et mesurer la connexion au repos et sous charge.
2. Identifier un problème mesurable avant de proposer un changement.
3. Appliquer manuellement une politique conservatrice sur un moteur validé, avec sauvegarde et restauration.
4. Comparer le résultat à la référence, en tenant compte des autres appareils et des ressources consommées.
5. Présenter ce qui s'est amélioré, dégradé ou n'a pas changé.

Un groupe minimal de mesure peut préparer cette évaluation. La coordination avancée, une interface complète, les relais automatiques et le ML attendront ce premier résultat. L'absence de groupe complet ne doit pas bloquer l'évaluation du moteur de passerelle.

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
