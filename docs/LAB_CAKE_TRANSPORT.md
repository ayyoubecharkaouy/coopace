# Transport hérité et pilote interne CAKE Go

## État

Le transport Linux et un pilote interne de séquence sont implémentés dans `apps/gateway/internal/labcontrol`. Les tests lancent un vrai processus Go et des outils simulés. Ils vérifient les canaux hérités, les événements, l’annulation des I/O et la fermeture des descripteurs. Le [backend natif borné](LAB_CAKE_BACKEND.md) est maintenant implémenté et assemblé en privé ; l’[entrée interne et le journal durable](LAB_CAKE_ENTRY.md) sont maintenant livrés, sans intégration au superviseur Python.

Cette livraison prolonge le [contexte de session](LAB_CAKE_CONTEXT.md) et le [contrat d’exécuteur](LAB_CAKE_EXECUTOR.md). La passerelle publique conserve `inspect` et `plan` ; le pilote `runWorker` reste privé et est assemblé par l’entrée interne. Aucun réglage réseau n’est appliqué par les essais.

## Descripteurs fixes

| Descripteur dans le processus Go | Usage |
| --- | --- |
| 3 | Lecture du canal de contrôle : initialisation, `apply`, `finish`. |
| 4 | Écriture du canal d’événements. |
| 5 | Référence conservée de l’espace réseau cible. |
| 6 | Référence de l’espace réseau d’origine du superviseur. |
| 7 | Journal durable, validé et fermé séparément par l’entrée interne. |

`OpenInheritedTransport` est réservé au montage initial des I/O pollables d’un processus dédié dont le lanceur possède ces quatre emplacements. Il les consomme, y compris après un échec, et les ferme après usage. Il ne doit pas servir de sonde dans un autre processus en cours d’exécution. Aucun numéro de descripteur ni chemin d’espace ne provient du JSON.

Les quatre emplacements sont examinés avant l’enregistrement des canaux auprès du poller Go, pour qu’un descripteur manquant ne soit pas confondu avec une nouvelle allocation interne. Le contrôle et les événements doivent être deux objets FIFO distincts, respectivement ouverts en lecture seule et en écriture seule. Le futur lanceur doit créer ces canaux anonymes ; leur type seul ne prouve pas leur origine.

Les deux références d’espace sont contrôlées en lecture seule avec `platforms/linux.InspectNetworkNamespaceDescriptor`, avant l’initialisation JSON. Leur liaison à l’espace courant et leur différence avec l’origine restent vérifiées par `Session.BindNamespace`. La première version exige Linux amd64. Aucun changement d’espace ni création de ressource n’est effectué par ce transport.

Tous les descripteurs sont marqués close-on-exec avant le lancement d’un outil. Le test de sous-processus contrôle l’absence des objets hérités dans l’outil, à partir de leurs identités, sans supposer que les mêmes numéros de descripteurs restent libres dans un runtime Go.

## I/O bornées

Les canaux hérités sont enregistrés en mode non bloquant pour permettre les échéances de `os.File`. Une plateforme qui ne fournit pas ces échéances provoque un refus.

Chaque lecture/écriture prend la borne la plus proche entre la frontière de session et le contexte appelant. L’initialisation est limitée à cinq secondes depuis le départ capturé ; la durée totale du pilote reste de trente secondes. L’annulation du contexte expire le canal, y compris pendant une lecture partielle ou une écriture bloquée. Le callback d’annulation est terminé avant de rendre la main, pour ne pas modifier l’échéance d’un appel suivant.

Une erreur d’I/O rend le transport inutilisable pour la suite. Aucune trame partiellement lue ou écrite n’est réessayée. Les écritures partielles ordinaires sont poursuivies ; une écriture sans progression est refusée. EOF, EPIPE et dépassements de délai restent des erreurs.

Ces propriétés concernent les canaux. Un contexte transmis à une opération métier ne peut pas arrêter une fonction qui l’ignore : le [backend natif](LAB_CAKE_BACKEND.md) borne et récupère maintenant ses appels aux outils avec les limites de deux secondes et de sortie du contrat. Aucun arrêt autonome d’un backend arbitraire ou nettoyage de ressources réseau n’est revendiqué ici.

## Événements et séquence

Les événements ont un préfixe uint32 big-endian puis un objet JSON v1 `lab_cake_worker_event`, avec `session_id`, `event` et la référence fixe `cake-ipv4-lab-4mbit-v1`.

- `ready` : après liaison de session et validation du relevé initial fourni par le backend ; aucun relevé appliqué attaché.
- `applied` : après `apply` et validation du relevé fourni ; contient `producer_profile` et `qdisc`.

Le relevé est revérifié avant encodage. Le JSON embarqué conserve champs et nombres sans conversion flottante, mais son espacement et ses échappements sont normalisés par l’encodeur ; il ne remplace pas l’archivage futur des octets source. La taille est contrôlée après encodage, car l’échappement peut agrandir une entrée valide.

La limite est de 128 Kio de JSON par événement et 512 Kio au total, préfixes inclus dans le budget total. Les événements ne portent aucune attestation de nettoyage ni autorisation d’une autre action. Leur lecture stricte, ordre et journalisation côté superviseur restent à raccorder.

Le pilote privé enchaîne initialisation, liaison, lecture initiale, `ready`, réception de `apply`, opération d’application, validation, `applied`, réception de `finish`, puis relecture finale conforme et fermeture des quatre références. La relecture finale conserve la frontière précédant `finish` : aucune nouvelle fenêtre de cinq secondes n’est accordée. Une erreur de fermeture empêche également un succès du pilote.

Les callbacks du pilote sont maintenant assemblés au [backend natif](LAB_CAKE_BACKEND.md) par `native_linux.go` : interfaces DOWN, chemins/empreintes, arguments fixes, limites stdout/stderr et traces. L’[entrée interne](LAB_CAKE_ENTRY.md) transmet maintenant le journal durable au backend ; les essais positifs actuels utilisent des outils simulés. Le pilote n’est pas un exécuteur de commandes configurables par JSON.

## Vérifications disponibles

```sh
sh scripts/go.sh test -count=1 -v ./apps/gateway/internal/labcontrol ./platforms/linux
sh scripts/go.sh test -race -count=1 ./apps/gateway/internal/labcontrol
```

Les essais couvrent initialisation bloquée, préfixe/corps partiel, lecture et écriture annulées, sortie bloquée, budget dépassé, pair fermé, mauvais sens/type de canal, référence absente, session différente, refus natif de l’espace d’origine, EOF, fin prématurée, doublon `apply` et relecture finale invalide.

L’essai positif transmet les quatre références à un vrai enfant lancé dans son groupe de processus, puis lance des outils qui renvoient les fixtures. Il confirme absence d’application avant l’instruction, une seule application simulée, relecture finale et EOF après sortie. Le vérificateur positif simule explicitement la distinction entre cible et origine : **il ne démontre pas une liaison à un espace neuf**. Le chemin natif sans cette substitution refuse l’espace d’origine et ne lance aucun outil.

Un autre essai annule un outil simulé bloqué et constate sa récupération. La mort forcée après `ready`, lorsque aucun outil n’est actif, ferme le canal d’événements. Ces essais ne prouvent pas la récupération d’un outil orphelin après mort forcée du processus Go pendant son exécution ; elle relève du [superviseur raccordé](LAB_CAKE_GO_GUARD.md), testé avec un outil orphelin simulé ; sa validation avec le vrai processus Go reste à réaliser.

## Suite

Le [backend natif borné](LAB_CAKE_BACKEND.md) est maintenant implémenté et testé avec des outils simulés. L’[entrée interne et son journal durable](LAB_CAKE_ENTRY.md) sont livrés. Le [raccordement au superviseur](LAB_CAKE_GO_GUARD.md) est implémenté et testé en simulation. Il reste à démontrer l’héritage des références à travers l’entrée dans un espace réseau neuf, puis les deux contrôles natifs DOWN. Les commandes et preuves Python historiques restent distinctes.
