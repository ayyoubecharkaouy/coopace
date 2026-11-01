# Raccordement du contrôle CAKE Go au superviseur

## État

Le raccordement est implémenté dans `scripts/lab_cake_go.py`, avec contrat de messages et relecture des preuves dans `lab_cake_go_protocol.py`. L’entrée `lab-cake-go.py` expose `plan`, `check` et `check-crash`. Les contrôles Python historiques sont conservés sans modification.

**Les tests automatiques positifs simulent les namespaces, l’entrée réseau et le processus du contrôle.** Ils exécutent réellement les descripteurs, pipes, `exec`, signaux, récupérations et écritures. Les [deux contrôles natifs DOWN](VALIDATION_CAKE_GO_DOWN_2026-11-01.md), réalisés séparément selon le [protocole figé](LAB_CAKE_GO_NATIVE.md), confirment le cycle avec le véritable processus Go et les vrais outils `ip`/`tc`, en fin normale et après SIGKILL.

## Responsabilités

Le raccordement réutilise `Guard` pour la possession des trois espaces, son échéance indépendante de 180s et son budget de nettoyage de 10s. Le superviseur crée uniquement le veth `wan`/`eth0`, laissé DOWN sans adresse ni route. Il ne configure pas CAKE : l’ajout appartient au backend Go après `apply`.

Les chemins canoniques et SHA-256 du processus Go, de `ip`, de `tc` et de Python sont enregistrés avant création des ressources, puis revérifiés. Les scripts du raccordement et les dépendances de supervision sont également identifiés. Cette provenance conserve le binaire sélectionné et les informations de compilation retournées ; elle complète le gel d’une expérience native sur un commit donné.

Le lanceur ouvre la cible réseau, vérifie son type noyau et son identité contre l’objet possédé, puis ouvre l’espace d’origine du superviseur. La cible doit différer de l’origine. Les références restent conservées jusqu’à l’arrêt du groupe, puis sont fermées avant suppression des espaces.

## Démarrage avant Go

Un court bootstrap Python isolé et sans thread copie les descripteurs au-dessus de la plage réservée avant de les redistribuer. Il entre dans la cible avec `os.setns` avant de démarrer Go, puis exécute le fichier binaire ouvert et vérifié via `/proc/self/fd`. Il ne change pas l’espace du superviseur.

Les rôles restent ceux de l’[entrée interne](LAB_CAKE_ENTRY.md) : contrôle 3, événements 4, cible 5, origine 6 et journal 7. Le journal est créé exclusivement en mode `0600`, en ajout, hors de la réservation jetable ; fichier et répertoire sont synchronisés avant lancement. Les nouveaux fichiers de preuves prennent le propriétaire du dossier d’expérience lorsque le lanceur s’exécute avec des privilèges supplémentaires.

Le processus reste leader de son propre groupe, extérieur au superviseur. L’identifiant du leader n’est pas libéré avant le dernier signal collectif. Les outils orphelins du groupe sont récupérés par le mécanisme subreaper existant ; aucun PID déclaré dans le journal ne sert à cibler un processus étranger.

## Dialogue et décision

1. Envoyer la requête interne liée au jeton et à l’identité retenue.
2. Attendre `ready`, puis revalider son préfixe durable avant d’envoyer `apply`.
3. Attendre `applied`, comparer son relevé aux octets du journal et relire CAKE indépendamment.
4. En mode normal, envoyer `finish` et attendre l’arrêt ; en mode panne, tuer le leader après `applied` durable.
5. Arrêter et récupérer le groupe, relire les interfaces et la file, fermer les références, puis retirer les seuls espaces possédés.
6. Vérifier le code OS, le journal complet ou le préfixe attendu et les empreintes avant de publier un succès.

Les messages inconnus, doublons, mauvais jetons, sorties supplémentaires, longueurs excessives, EOF et délais interrompent le contrôle. Les appels et sorties du journal sont recalculés : producteur, séquence exacte de quatorze appels en mode normal ou onze avant la panne, unique ajout, relevés initiaux vides/noqueue et statistiques CAKE conformes. La fin normale doit correspondre au code OS `0` ; la panne imposée doit correspondre à `-9`, sans reconstruire une fin absente.

Le superviseur ne déduit jamais le nettoyage du seul journal Go. Une erreur de relecture après récupération garde un résultat échoué, tout en permettant le retrait des ressources dont la possession reste vérifiée. Un arrêt de groupe incertain ou une identité modifiée empêche la suppression correspondante et le succès.

## Preuves et limites

Le dossier d’expérience doit exister et être vide. Il conserve :

- `environment.json` : outils, empreintes, sources et invocation locale du contrôle fixe.
- `worker.jsonl` : journal Go de 8 Mio maximum, avec son identité de fichier revérifiée lors des lectures.
- `events.bin` : trames reçues, bornées à 512 Kio.
- `worker.stderr` : diagnostic borné à 64 Kio.
- `report.json` : état explicite, code récupéré, descendants récupérés, relevés indépendants et état du nettoyage.

Un échec conserve les pièces disponibles et garde `state: failed`. Les rapports conservent `traffic_generated: false`, `active_path_verified: false` et `link_state: DOWN`. Il ne s’agit pas d’une mesure de bénéfice, d’une restauration de passerelle réelle ou d’une validation du foyer. La destruction du superviseur et une panne de l’hôte restent hors garantie.

## Vérification et prochaine activité

```sh
python3 -I -B scripts/lab-cake-go.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_cake_go.py' -v
```

Les tests utilisent des espaces représentés par des fichiers et remplacent seulement l’entrée réseau ainsi que le programme du contrôle. Ils vérifient fin normale, panne après `applied`, journal incompatible, mauvais jeton, trame excessive, échéance, outil orphelin, erreur de relecture et nettoyage incomplet. Les PID réels sont vérifiés absents avant suppression simulée des espaces.

Les modes natifs demandent les privilèges du laboratoire, Python avec `setns`, un binaire Go compilé et un dossier d’expérience neuf via `--worker` et `--artifacts`. Le [protocole des deux exécutions figées normales/panne](LAB_CAKE_GO_NATIVE.md) décrit la préparation et la relecture sur la machine Linux de laboratoire. Leur [validation native](VALIDATION_CAKE_GO_DOWN_2026-11-01.md) confirme l’héritage à travers `setns`, les relevés et le nettoyage dans les deux modes. La panne intervient après récupération des outils ; elle ne valide pas un outil encore actif lors de la mort du processus Go. Le [contrat du contrôle Go puis trafic](LAB_CAKE_GO_ACTIVE.md) est défini. Sa [première sous-étape](LAB_CAKE_GO_PHASE.md) est maintenant implémentée et testée en simulation : phase Go sans suppression des espaces et gestion des groupes avant transition. Les commandes DOWN conservent leur nettoyage complet ; l’activation combinée reste à développer.
