# Relecture indépendante des phases de campagne

## État et portée

Le module `scripts/lab_cake_go_campaign_review.py` expose `replay(folder, report, tools, owned)`. Cette première sous-étape de relecture traite les preuves des six phases, ou de la première phase idle suivie du premier ready chargé en mode panne. Elle ne réutilise pas le verdict du [rapport global](LAB_CAKE_GO_CAMPAIGN_REPORT.md).

**Le [raccordement global et au dossier figé](LAB_CAKE_GO_CAMPAIGN_GLOBAL_REVIEW.md) est maintenant livré.** Le lanceur natif reste à développer. Ce module ne publie ni `validation.json`, ni certificat natif. La [préparation seule](LAB_CAKE_GO_CAMPAIGN_PREPARE.md) conserve `native_launcher_available: false`.

## Entrées et sortie

Le dossier contient `supervisor.jsonl`, `driver.stdout.bin` et `driver.stderr.bin`. Les tailles et empreintes sont rapprochées des captures déclarées. Le JSON refuse les clés dupliquées et nombres non finis ; les enveloppes du journal, leur séquence, leurs dates et leur temps écoulé sont contrôlés. Les captures conservent leurs fins de ligne originales : CRLF, troncature, mauvais ordre, mauvaise session et contrôle répété sont refusés.

`tools` et `owned` sont les outils épinglés et les identités des trois namespaces que le futur relecteur global devra authentifier depuis la préparation et les preuves de possession. Le module vérifie leur utilisation dans les phases, sans prétendre authentifier seul cette provenance.

La sortie porte `kind: lab_cake_go_campaign_phase_review`, `scope: phases_only`, `phase_evidence_valid: true` et `native_certificate: false`, avec les PID des helpers consignés, le nombre de phases et les mesures recalculées. Une preuve incohérente provoque un refus. Des preuves de phase cohérentes peuvent cependant conserver des mesures inexploitables : ces deux résultats restent distincts.

## Vérifications réalisées

- Rapprochement des événements stdout et du journal ; relecture de l’automate et des intentions/envois de chaque contrôle.
- Ordre des frontières begin, relevé initial, start, ready, identités vérifiées, continue, observation de fin, end, arrêt des helpers, vidage et advance.
- Exécutable, arguments, parent, groupe, session, start-time et namespace des helpers annoncés, à partir de leurs identités consignées ; rôles cible/récepteur/émetteur.
- Arrêt des identités avant advance : absence ou PID réutilisé avec start-time distinct, sans signal ni action sur le processus courant.
- Reconstruction de CAKE depuis les sorties brutes du `tc` épinglé, vérification du profil, options, statistiques et monotonie ; rapprochement des échantillons avec leurs lectures brutes.
- Budget de 720 échantillons et 4 Mio, temps monotones de lecture, relevé initial unique et cadence minimale de 250 ms pour les relevés périodiques.
- Empreinte de la ligne end reçue, série finale de lectures vides espacée d’au moins 500 ms, puis advance sous trois secondes depuis l’observation de fin.
- Différences de compteurs par phase recalculées et rapprochées du journal et du rapport ; percentiles, fenêtres et charge recalculés par l’[évaluation pure](LAB_CAKE_GO_CAMPAIGN_ASSESS.md).

La disponibilité est vérifiée avec une borne conservatrice de 15 s entre les preuves d’envoi de start et de ready dans le journal. Cette observation peut inclure le temps de conservation des preuves ; elle ne reconstitue pas un instant de réception non consigné.

En mode panne, le dialogue doit s’arrêter après la vérification des trois helpers du premier ready chargé, avant continue. L’intention de tuer le pilote doit correspondre au leader consigné. Cette relecture des phases ne suffit pas à attester la récupération finale du groupe ou le retrait des ressources.

## Limites et raccordement restant

Le [relecteur global](LAB_CAKE_GO_CAMPAIGN_GLOBAL_REVIEW.md) vérifie les manifestes et objets Git, les quatre provenances Go, la phase Go et ses appels, les commandes du passage IPv4, toute la topologie, les codes OS des deux modes, les groupes, le nettoyage et l’absence finale des ressources/PID. Il rapproche les décisions recalculées avec le rapport final et fige les empreintes du dossier avant/après relecture.

Ce module ne lance aucune commande Git, Go, ip, tc ou ping, n’envoie aucun signal, ne nettoie rien et n’écrit pas les preuves. Ses calculs utilisent les fichiers conservés et les validations pures partagées. Une qualification de charge locale n’est pas une démonstration du bénéfice propre à Coopace.

## Vérification et suite

```sh
PYTHONPATH=scripts/tests python3 -B -m unittest test_lab_cake_go_campaign_review -v
```

Les tests synthétiques couvrent les six phases, les altérations avec empreintes recalculées, les options CAKE, les compteurs, les identités, les contrôles, le vidage, les différences, la troncature et le PID réutilisé sans commande ni signal. Un test relit aussi les journaux des vrais processus du collecteur, avec réseau simulé, dans les deux modes. Les dates synthétiques incohérentes de ce contrôle normal restent explicitement inexploitables. Aucun certificat natif n’est créé.

Validation locale du 3 novembre 2026 : 40 tests ciblés passent en 43,684 s, dont six nouveaux pour la relecture des phases, neuf de calcul, quatorze du dialogue de campagne, six du protocole à flux unique et cinq du verdict global. Le test des journaux réels utilise des processus Linux et un noyau réseau simulé. La suite complète n’a pas été relancée pour cet ajout autonome.

Le [raccordement Go/IPv4 et au dossier figé](LAB_CAKE_GO_CAMPAIGN_GLOBAL_REVIEW.md) est livré. Prochaine sous-étape : lanceur des deux modes et nouvelle préparation avant les essais natifs.
