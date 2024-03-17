Fonctionnalité: Surveillance des conversations par les administrateurs

Scenario: Accès aux logs de conversation après un signalement
Given Un administrateur est connecté au système de gestion d’apprentissage
And Un utilisateur signale une conversation suspecte
When L’administrateur recherche les logs de conversation liés au signalement
Then L’administrateur peut accéder aux logs de la conversation suspecte

Scenario: Alertes en temps réel basées sur des mots-clés
Given Un administrateur est connecté au système de gestion d’apprentissage
And Des mots-clés de monitoring ont été définis
When Une conversation contenant un mot-clé est créée ou modifiée
Then L’administrateur reçoit une alerte en temps réel concernant la conversation contenant le mot-clé

Scenario: Respect de la confidentialité lors de la surveillance
Given Un administrateur est connecté au système de gestion d’apprentissage
And La confidentialité des utilisateurs est garantie
When L’administrateur décide de surveiller une conversation pour des raisons légitimes
Then L’administrateur accède uniquement aux informations nécessaires pour la surveillance
And Les informations des utilisateurs non concernés par la surveillance restent confidentielles.