# Noyau métier

État : module prévu, sans implémentation.

Ce module définira les modèles et règles communs : appareils, rôles, capacités, consentements, mesures, décisions bornées, évaluation et abstention.

Il sera développé en Go et restera indépendant des API réseau propres aux systèmes et du tableau de bord. Les applications Linux et Windows partageront cette bibliothèque. Sa réutilisation sur Android nécessite une validation séparée, décrite dans les [choix techniques](../../docs/TECH_STACK.md).
