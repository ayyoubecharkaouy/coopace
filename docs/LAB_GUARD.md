# Supervision indépendante du laboratoire

## État et périmètre

`scripts/lab-guard.py` prépare le nettoyage indépendant requis par le [protocole du goulot virtuel](VIRTUAL_BOTTLENECK.md). Le superviseur crée et possède trois espaces neufs, reste extérieur au groupe de processus du pilote, puis récupère ses processus avant de supprimer les espaces. **Les deux premiers contrôles natifs sont validés**, après fin normale et mort forcée du pilote. Le [compte rendu](VALIDATION_LAB_GUARD_2026-10-29.md) conserve les preuves et limites ; les tests avec espaces simulés restent disponibles.

Cette sous-étape livre uniquement le contrôle du cycle de vie. Elle ne configure aucune file TBF/CAKE, adresse, route ou interface physique et ne génère aucun trafic. Les commandes existantes de `lab-network.sh` conservent leur implémentation et leurs limites ; elles ne bénéficient pas encore de ce nouveau superviseur.

Le contrôle utilise Python 3 et sa bibliothèque standard, avec l'appel Linux `prctl` via `ctypes`. Il reste un outil de développement ; les applications du produit restent en Go/Kotlin.

## Deux contrôles ciblés

| Mode | Comportement et résultat attendu |
| --- | --- |
| `plan`, également le défaut | Affiche le périmètre ; aucune vérification de privilèges ni création de ressource. |
| `check` | Le pilote crée un descendant, attend sa disponibilité et termine normalement en le laissant vivant. Le superviseur doit arrêter et récupérer ce descendant. |
| `check-crash` | Après la même disponibilité, le superviseur tue volontairement le pilote par `SIGKILL`. Il doit ensuite arrêter et récupérer le descendant orphelin. |

Le descendant ignore volontairement `SIGTERM` et dispose d'une durée propre maximale de 120s. Le nettoyage envoie `SIGTERM` au groupe possédé, attend 200ms puis envoie `SIGKILL`. Un autre processus lancé dans un autre groupe n'est pas ciblé.

Le pilote est exécuté par `ip netns exec` dans l'espace passerelle neuf. Son descendant conserve donc aussi une référence à cet espace jusqu'à sa terminaison. Les trois espaces ont le préfixe `cg-`, un jeton propre à la réservation, et les suffixes `-c`, `-g`, `-s` ; ils n'ont aucun raccordement au foyer.

## Possession des ressources et bornes

Le superviseur arme une échéance monotone de 180s avant la première création. Le contrôle de disponibilité du pilote est borné à 5s et sa sortie à 4 096 octets. Les handlers HUP/INT/TERM enregistrent un signal, sans lancer le nettoyage au milieu de l'enregistrement d'une création ou d'un démarrage.

Le pilote est lancé dans une nouvelle session. Le superviseur observe sa fin avec `waitid(..., WNOWAIT)` et garde son PID réservé jusqu'au dernier signal envoyé à son groupe. Il récupère ensuite le pilote par `wait`, puis ses descendants adoptés par `waitpid` limité à ce groupe. Le rôle Linux de subreaper permet cette adoption ; voir les références [Python waitid](https://docs.python.org/3.12/library/os.html#os.waitid), [Python Popen](https://docs.python.org/3.12/library/subprocess.html#subprocess.Popen) et [PR_SET_CHILD_SUBREAPER](https://kernel.googlesource.com/pub/scm/docs/man-pages/man-pages/+/d99b5be0d8e18f175089c54e3ec04b170b4560a7/man2/prctl.2).

L'identité de chaque espace est conservée après création réussie sous forme de périphérique/inode. La suppression est refusée si cette identité n'est plus confirmée. Une collision n'autorise aucune suppression de l'objet existant. Une création échouée ou expirée peut avoir un effet ambigu : conserver son nom dans le journal et demander une inspection ciblée, sans la déclarer possédée ou la supprimer automatiquement.

Le nettoyage a un budget global de 10s, avec au plus 2s par commande `ip`. Si l'arrêt des processus n'est pas confirmé, les espaces sont conservés. Si une suppression échoue, les autres ressources possédées sont tout de même traitées et aucun JSON de réussite n'est publié. Ces délais ne garantissent pas l'interruption d'une opération bloquée dans le noyau.

La réservation privée `/tmp/coopace-guard.JETON` contient `owner.json`, journal de diagnostic, sans commandes de restauration automatique. Quand le nettoyage réussit, le journal et la réservation vide sont retirés, y compris si le contrôle lui-même a échoué. Si le nettoyage échoue, le journal est conservé lorsque possible ; un fichier inconnu empêche le retrait du dossier, sans suppression récursive. Le chemin est imprimé dans le journal d'exécution avant la création des espaces. Les rapports, stderr et codes conservés par le lanceur restent donc les pièces durables de l'essai.

## Vérifications automatiques

Depuis la racine du dépôt, sans privilèges :

```sh
python3 -I scripts/lab-guard.py plan
python3 -B -m unittest discover -s scripts/tests -p 'test_lab_guard.py' -v
```

Les tests utilisent des dossiers temporaires à la place des espaces réseau. Ils lancent de vrais pilotes et descendants dans des processus dédiés, puis vérifient leur récupération avant toute suppression simulée, y compris après mort forcée, expiration et signal. Ils couvrent aussi les collisions, identités changées, créations ambiguës, erreurs de suppression, sorties excessives et préservation des objets inconnus. Aucun accès réseau ni privilège système n'est utilisé.

## Reproduire les contrôles natifs

Les modes `check` et `check-crash` exigent Linux, Python 3, `ip`, UID 0, `CAP_NET_ADMIN` et `CAP_SYS_ADMIN`. Le précontrôle les vérifie avant de réserver des ressources ; aucun binaire Go n'est requis. Les arguments n'acceptent ni nom d'espace existant ni commande arbitraire à exécuter.

Sur le PC Linux autorisé, préparer un nouveau dossier local, copier ce protocole et conserver le commit, les empreintes du script et du lanceur avant les deux contrôles. Exécuter ensuite chaque contrôle avec élévation, en conservant séparément stdout, stderr et le code de sortie exact. Les commandes prises en charge sont :

```sh
sudo python3 -I scripts/lab-guard.py check
sudo python3 -I scripts/lab-guard.py check-crash
```

Un lanceur local préparé dans `.local/experiments/` peut réaliser ces deux appels, capturer automatiquement leurs codes et refuser d'écraser des résultats existants. Le superviseur ne crée pas lui-même un dossier d'expérience persistant.

Critères de validation native : les deux contrôles sortent avec `0`, produisent chacun un unique JSON `lab_guard_check`, indiquent un descendant récupéré et `cleanup_verified: true`. Le code du pilote doit être `0` pour `check` et `-9` pour `check-crash` ; ce dernier est attendu par le contrôle. Vérifier les noms et la réservation annoncés, les logs et l'absence de file ou de trafic généré. Conserver aussi les essais échoués.

Le JSON local v1 contient le mode, les codes/PID du pilote, le PID du descendant, le nombre de descendants récupérés, les trois noms, la réservation et les indicateurs de nettoyage/file/trafic. Il sert à cet essai de cycle de vie, pas aux comparaisons de latence. `0` signifie que le contrôle attendu et le nettoyage ont réussi ; `1` indique une erreur et `2` des arguments invalides. Une interruption gérée conserve le code 129/130/143 lorsque le nettoyage réussit.

## Limites et suite

Le superviseur doit rester vivant. Sa destruction, une panne de l'hôte ou l'intervention d'un autre processus privilégié peuvent laisser des ressources. Les pilotes admis devront conserver leurs descendants dans le groupe possédé : un programme qui crée une autre session ou un groupe séparé sort de ce contrat. Ce contrôle n'est pas un environnement pour exécuter des programmes arbitraires.

La récupération vérifiée concerne les processus possédés. Elle n'établit pas l'absence de références détenues par un processus étranger entré dans l'espace réseau, ni la restauration du routage d'un foyer. Les dossiers et espaces résiduels nécessitent une inspection ciblée à partir du journal, sans nettoyage global.

Les [deux premiers contrôles natifs](VALIDATION_LAB_GUARD_2026-10-29.md) sont validés. La prochaine sous-étape consiste à intégrer le superviseur au futur cycle de vie de la file et tester ses erreurs de création/relecture. Le rapport du récepteur, les statistiques de file et la campagne avec goulot restent à développer. L'étape 4.2 reste ouverte.
