# Catalogue et validateurs CAKE Go

## État et portée

La première sous-étape du [contrat d'exécuteur](LAB_CAKE_EXECUTOR.md) est implémentée dans `platforms/linux` : catalogue du profil fixe, identification du producteur, validation des configurations/statistiques et différences de compteurs. **Ces fonctions sont pures** : elles ne lancent aucun appel `tc`, n’ouvrent aucun descripteur et n’ajoutent aucune file. Le [contexte et la vérification en lecture seule des descripteurs](LAB_CAKE_CONTEXT.md) sont livrés séparément ; le [backend natif](LAB_CAKE_BACKEND.md) est maintenant implémenté séparément, avec [entrée interne et journal durable](LAB_CAKE_ENTRY.md), avec [validation native DOWN de l’ajout et du nettoyage](VALIDATION_CAKE_GO_DOWN_2026-11-01.md).

La passerelle conserve `inspect` et [`plan`](GATEWAY_PLANNING.md). Les validations natives Python restent des preuves distinctes. Réutiliser leurs relevés dans des tests ne prouve pas l'application de CAKE par Go.

## API et rangement

| Fonction | Contrat |
| --- | --- |
| `LookupCakeReference` | Accepte seulement `core.CakeReferenceIPv4LabV1` ; retourne les paramètres et arguments fixes de `qdisc add`, sans chemin d'outil ni commande shell. Chaque appel retourne sa propre liste. |
| `ParseCakeProducer` | Reconnaît la bannière ASCII iproute2-6.1.0, limitée à 512 octets, et conserve sa valeur exacte. |
| `ValidateCakeInitial` | Accepte un relevé vide ou une unique racine `noqueue` conforme au contexte `wan` ; ne prouve ni propriété ni état DOWN. |
| `ParseCakeConfiguration` | Vérifie une unique racine CAKE `10:` et l'ensemble des options du profil, puis retourne unités explicites et omissions justifiées. |
| `ParseCakeReading` | Ajoute les statistiques obligatoires, les disponibilités de classe et une copie exacte du relevé brut, avec ses champs supplémentaires. |
| `DiffCakeCounters` | Compare les cinq compteurs cumulés d'une même file possédée. Une baisse rend la différence indisponible, avec motif `counter_decreased` et compteurs absents. |

`cake.go` contient catalogue et modèles, `cake_parse.go` la validation des objets/options, `cake_stats.go` les statistiques et différences ; `cake_test.go` porte leurs tests. Les types de normalisation ne définissent pas un nouveau rapport local ou message réseau. Leur future conversion appartient à l'application passerelle.

Une entrée de catalogue est une copie consultable et modifiable par son appelant. Le futur exécuteur devra résoudre lui-même l'identifiant depuis le catalogue, sans faire confiance à des arguments modifiés fournis par un appelant.

## Types, unités et valeurs indisponibles

Les paramètres restent ceux de la [référence statique](STATIC_CAKE_PLANNING.md) : débit nominal 4 000 000 bits/s, débit exporté 500 000 octets/s, RTT 100 000µs, mémoire 1 048 576 octets et options fixes `besteffort/flows`, raw, sans NAT/wash/filtre ACK, egress, segmentation GSO et masque nul.

Le producteur identifié permet uniquement les omissions justifiées de `mpu=0`, `atm=noatm` en mode raw et `autorate=false`. Un champ `autorate` explicitement présent est refusé pour ce profil. Une statistique manquante ou mal typée ne bénéficie pas de ces règles.

Chaque relevé est limité à **64 Kio**, UTF-8 valide, sans clés dupliquées, nombres non finis, données supplémentaires ni imbrication au-delà de 16 niveaux. Les noms natifs tels que `ack-filter` sont admis par `internal/strictjson.CheckSyntax` ; `Check` conserve les règles canoniques des formats applicatifs et du groupe.

Les compteurs requis utilisent des entiers uint64, sans conversion en flottants. Les formes fractionnaires/exponentielles, chaînes, booléens, valeurs nulles, négatives ou hors borne sont refusées pour ces champs. Le zéro entier JSON `-0` est conservé comme zéro, conformément au validateur Python étudié.

Les cinq compteurs racine restent séparés de backlog/qlen, de la mémoire et des statistiques de classe. Une unique entrée `tins` est requise ; ses vingt champs connus gardent chacun disponibilité, valeur ou absence et motif. Un détail absent donne `Available: false`, `Value: nil`, `Reason: not_reported`, jamais une mesure zéro inventée. Les champs supplémentaires restent dans le relevé brut.

`MemoryUsedReportedBytes` conserve le maximum historique fourni par le producteur étudié, même s'il dépasse le budget annoncé. Aucun taux de perte de bout en bout, débit WAN ou différence de jauge n'est calculé. Une différence de compteurs ne prouve pas la continuité de la file : l'appelant devra vérifier les identités et chaque paire de relevés successifs pour détecter une remise à zéro suivie d'une reprise.

## Preuves et vérification

Deux [fixtures issues des relevés natifs](../platforms/linux/testdata/cake/README.md) sont suivies dans Git : après ajout sur lien DOWN et pendant une campagne CAKE active déjà validée. Elles contiennent uniquement les objets de file, avec provenance et empreintes des rapports source. Les variantes de refus et de bornes uint64 sont construites en mémoire.

Les tests couvrent profil et arguments fixes, bannière/producteur, état initial, champs obligatoires, mauvais types/valeurs, omissions, limite de taille, données ambiguës, disponibilité des champs de classe, précision uint64, copie des données brutes et baisse de chaque compteur. Une vérification différentielle locale de **623 cas** retrouve les mêmes acceptations/refus et normalisations que `scripts/lab_cake.py`, dans le périmètre borné du parseur Go ; la profondeur maximale propre au Go est testée séparément.

```sh
sh scripts/go.sh test -count=1 -v ./internal/strictjson ./platforms/linux
```

Les tests Go généraux, `go vet` et compilations Linux/Windows restent distincts d'un contrôle natif privilégié. Cette sous-étape ne requiert aucune commande sudo et ne modifie pas les modes Python existants.

## Sous-étape suivante

Le [contexte interne, le contrôle de session et les vérifications de descripteurs](LAB_CAKE_CONTEXT.md) sont maintenant implémentés et testés. Le [transport et le pilote interne](LAB_CAKE_TRANSPORT.md) sont également implémentés et testés avec de vrais processus et outils simulés. Le [backend natif borné](LAB_CAKE_BACKEND.md) est maintenant implémenté et testé avec des outils simulés ; l’[entrée interne et le journal durable](LAB_CAKE_ENTRY.md) sont livrés et le [raccordement au superviseur](LAB_CAKE_GO_GUARD.md) est implémenté et testé en simulation, selon le [contrat](LAB_CAKE_EXECUTOR.md). Les [deux contrôles natifs DOWN](VALIDATION_CAKE_GO_DOWN_2026-11-01.md) confirment maintenant ajout/relecture et nettoyage avec le vrai processus Go. Le contrôle de chemin actif reste à développer.
