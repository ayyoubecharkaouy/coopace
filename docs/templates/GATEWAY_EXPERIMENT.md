# Protocole d'expérience passerelle

État : À COMPLÉTER — aucune mesure ni modification effectuée par ce modèle.

Copier ce document dans `.local/experiments/` et remplacer les champs ci-dessous. Garder « inconnu », « indisponible » ou « non vérifié » lorsqu'une information n'est pas établie ; ne pas remplacer par zéro.

## Identification et objectif

- Identifiant local de l'essai : À RENSEIGNER
- Date, responsable et question mesurable : À RENSEIGNER
- Phase : référence initiale / moteur manuel / pilotage Coopace sans ML — À CHOISIR
- Plateforme candidate, système et version : À CONFIRMER
- Commit Git, modifications locales et empreinte du binaire : À RENSEIGNER
- Inventaire associé, date et rubriques indisponibles : À RENSEIGNER

## Topologie et couverture

```text
Appareils de test -> point d'application à confirmer -> routeur/accès -> cible autorisée
```

- Liens et interfaces réels, rôles LAN/WAN, éventuels VPN/ponts : À DÉCRIRE
- Chemin observé en IPv4 et preuve associée : NON VÉRIFIÉ
- Chemin observé en IPv6 et preuve associée : NON VÉRIFIÉ
- Trafic couvert, trafic exclu et autres usages connus : À RENSEIGNER
- Configuration initiale du moteur, des files et du routage concernés : À CONSERVER

## Méthode fixée avant la collecte

| Paramètre | Valeur prévue |
| --- | --- |
| Cible de mesure et autorisation d'usage | À RENSEIGNER |
| Méthode, unités et versions des outils | À RENSEIGNER |
| Charge contrôlée et appareil qui la produit | À RENSEIGNER |
| Nombre de répétitions et durée de chaque phase | À FIXER |
| Ordre des essais et conditions comparables | À FIXER |
| Métriques disponibles et métriques manquantes | À RENSEIGNER |
| Fichiers de résultats et horodatages | À RENSEIGNER |

## Critères chiffrés avant l'essai

| Critère | Seuil, unité et justification |
| --- | --- |
| Latence sous charge et échecs admissibles | À FIXER |
| Débit utile minimal et dégradation maximale | À FIXER |
| Équité et impact sur les autres appareils | À FIXER |
| CPU/mémoire et autres ressources pertinentes | À FIXER |
| Conditions d'arrêt, d'abstention et de retour arrière | À FIXER |

## Restauration avant toute modification

- Objets qui seraient modifiés et état initial complet à conserver : À DÉFINIR
- Procédure indépendante du processus de pilotage : NON IMPLÉMENTÉE / NON VÉRIFIÉE
- Comportement choisi en cas de panne et justification : À DÉFINIR
- Test d'interruption, retour arrière et délai maximal accepté : À DÉFINIR
- Vérification de connectivité IPv4, IPv6 et DNS après restauration : NON VÉRIFIÉE
- Preuves de restauration avant l'autorisation d'un essai avec intervention : ABSENTES

## Résultats après exécution seulement

- Séries au repos, séries sous charge, échecs et fichiers associés : NON MESURÉS
- Comparaison avec la même cible, méthode et configuration : NON EFFECTUÉE
- Écarts au protocole, dégradations et limites : À CONSIGNER
- Décision fondée sur les critères prédéfinis : AUCUNE

L'inventaire JSON seul n'est pas une sauvegarde restaurable. Le remplissage de ce document n'active aucune politique réseau et ne prouve pas un bénéfice.
