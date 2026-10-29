# Contrôles JSON partagés en Go

Ce paquet interne vérifie des limites de taille, la validité UTF-8 brute, les doublons de clés, une profondeur maximale de 16 et l'absence de données supplémentaires. Les noms de champs acceptés utilisent uniquement des lettres ASCII minuscules, des chiffres et `_`.

Il est utilisé par le décodeur du protocole et le lecteur des rapports TCP locaux. Les formats et leurs versions restent distincts : chaque appelant impose sa limite de taille, ses champs autorisés, ses champs requis et ses règles métier après ce contrôle commun.

Ce paquet ne réalise aucune lecture de fichier, authentification, connexion ou décision d'autorisation. Il dépend uniquement de la bibliothèque standard ; les tests du protocole et de la comparaison vérifient aussi son intégration.
