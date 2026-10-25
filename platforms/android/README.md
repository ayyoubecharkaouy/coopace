# Adaptation Android

État : module prévu, sans implémentation.

Cette adaptation sera développée en Kotlin pour l'agent Android : mesures accessibles, permissions, participation au groupe et fonctionnement dans les limites du système mobile. La réutilisation du noyau Go sera étudiée séparément avant de fixer le mécanisme d'intégration.

L'utilisation éventuelle de `VpnService` sera réservée aux fonctions qui exigent de diriger le trafic IP, avec consentement et gestion des conflits avec un VPN existant. Rejoindre le groupe n'implique pas automatiquement l'activation d'un VPN.

Le rôle de passerelle domestique Android n'est pas prévu dans le périmètre initial.
