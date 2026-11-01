# Phase Go réutilisable et groupes de processus

## État et portée

La première sous-étape du [contrat Go puis trafic](LAB_CAKE_GO_ACTIVE.md) est implémentée : une phase Go termine son groupe en conservant les espaces possédés. Le superviseur peut ensuite réserver un nouveau groupe sur les mêmes ressources. L’activation du réseau, le pilote à accusé et la collecte active combinée restent à développer.

Les tests simulent espaces réseau, entrée réseau et processus du contrôle Go. Ils exécutent réellement les descripteurs, pipes, `exec`, signaux et récupérations. Un second groupe de test contient trois enfants réellement récupérés après SIGKILL de son pilote. Ce groupe ne transfère aucune donnée. La [validation native DOWN du 1er novembre](VALIDATION_CAKE_GO_DOWN_2026-11-01.md), au commit `e104994`, précède cette extraction ; la nouvelle séquence devra avoir sa propre validation native.

## Organisation

| Élément | Responsabilité |
| --- | --- |
| `scripts/lab_process_group.py`, `ProcessGroup` | Conserver un leader non récupéré, signaler son groupe puis récupérer leader/descendants, sans posséder de namespace. |
| `scripts/lab-guard.py`, `Guard` | Posséder les espaces et la réservation, garder le délai global et l’historique des groupes, puis confirmer le nettoyage. |
| `Guard.advance_group` | Réserver le groupe suivant après récupération confirmée des précédents, sans changer les espaces ou le délai global. |
| `scripts/lab_cake_go.py`, `run_phase` | Exécuter et vérifier un cycle Go DOWN sur les ressources déjà préparées, conserver ses preuves et rendre un résultat de phase. |
| `GoGuard.advance_group` | Autoriser la transition uniquement après une phase Go normale vérifiée. |

`Guard.child`, `driver_code` et `reaped_descendants` décrivent le groupe courant. Les objets précédents restent dans `process_groups`, avec leurs codes et nombres de descendants propres. La transition remet à zéro le tampon de sortie et l’annonce du pilote ; le délai monotone et les identités possédées restent identiques.

## Arrêt et transitions

Un groupe passe par `new`, `running`, `stopping`, puis `stopped` ou `failed`. Un appelant de confiance lui fournit le processus qu’il vient de lancer avec `start_new_session=True`. L’activation subreaper reste à la charge du superviseur.

L’observation de sortie utilise `waitid/WNOWAIT`. Avant chaque signal collectif, le leader doit encore être un enfant non récupéré. TERM puis KILL précèdent `wait` ; les orphelins du groupe sont ensuite récupérés. Une fermeture réussie répétée ne renvoie aucun signal. Un leader récupéré à l’extérieur, un échec d’attente ou des descendants non confirmés rendent l’échec permanent : aucune nouvelle tentative ne peut signaler un identifiant de groupe éventuellement réutilisé.

`Guard.advance_group` exige un superviseur ouvert, aucune commande en cours et tous les groupes précédents récupérés. `GoGuard` exige en plus la validation de la phase Go normale. Le mode DOWN `check-crash` reste terminal, même lorsque son code `-9` et son nettoyage sont conformes au contrôle de panne. Une phase échouée ne peut pas ouvrir une phase suivante.

## Phase et possession des ressources

`run_phase` reçoit le propriétaire, les outils identifiés, le dossier de preuves et le lien DOWN préparé. Elle ne crée aucun espace et n’installe pas de gestionnaire de signal. Elle refuse les fichiers de preuves Go déjà présents, revérifie les identités, empreintes et sources, lance la session existante, récupère le groupe, relit la file et valide le journal complet ou le préfixe de panne. La récupération avant transition reste bornée par le délai global et le budget de 10s.

Les références héritées sont fermées avant retour et les trames/diagnostics sont conservés exclusivement. Le résultat local `lab_cake_go_down_phase` contient le jeton, le code OS, les descendants récupérés, le journal vérifié, les identités réseau et une copie des relevés DOWN. Son état `finished` porte `cleanup: deferred_to_supervisor` : il ne déclare pas les espaces supprimés et ne publie pas `cleanup_verified: true`.

Après retour réussi, l’appelant conserve la responsabilité du `finally` qui ferme le propriétaire, y compris si une activité suivante échoue. En cas d’erreur dans la phase, celle-ci interdit la transition, ferme le propriétaire et conserve les preuves disponibles avant de propager l’erreur. Une erreur de relecture après arrêt garde l’échec technique tout en permettant le retrait des ressources dont la possession reste confirmée.

Une fermeture de références non confirmée reste un échec permanent ; ses numéros de descripteurs ne sont pas réessayés. Un nettoyage de propriétaire échoué reste également échoué lors des appels suivants. Cela empêche de transformer une fermeture répétée en attestation de succès. Les groupes incertains empêchent la suppression des espaces ; le journal de possession reste disponible.

## Compatibilité et preuves

`lab-cake-go.py check/check-crash` utilise maintenant la phase extraite puis ferme le propriétaire. Ses rapports restent des objets `lab_cake_go_control` avec nettoyage complet avant succès. Les commandes historiques du superviseur utilisent la même primitive de groupe ; leur format demeure inchangé. Les empreintes de provenance du contrôle Go incluent désormais `lab_process_group.py`.

Les tests couvrent :

- Conservation des trois espaces, de la réservation et du délai après fin normale de la phase.
- Nouveau groupe distinct, arrêt de son pilote et récupération de trois enfants avant suppression simulée des espaces.
- Mauvais jeton/journal, code OS incompatible, délai avant transition, preuves préexistantes, outil orphelin, erreur de relecture et nettoyage incomplet, avec transition refusée.
- Groupe déjà récupéré, récupération externe du leader et erreur après récupération, sans signal ultérieur.
- Fermeture répétée et références non confirmées, sans nouvelle utilisation d’un FD ou lancement après fermeture.

Les tests dédiés sont `test_lab_process_group.py` et `test_lab_cake_go_phase.py`. Ils s’exécutent dans la suite Python ordinaire ; les scénarios subreaper sont isolés dans des sous-processus. Les contrôles réseau privilégiés restent distincts des tests automatiques.

La prochaine sous-étape ajoute l’activation et les relectures de continuité sur les ressources conservées. Le pilote de trafic à accusé, la collecte combinée et les deux essais natifs complets viendront ensuite, conformément au contrat.
