Feature: Envoie de messages privés entre utilisateurs

Scenario: Utilisateur envoie un message privé à un autre utilisateur
    Given L’utilisateur est connecté sur la plateforme LMS
    And L’utilisateur a des contacts enregistrés dans son compte
    When L’utilisateur sélectionne un destinataire parmi ses contacts ou via une recherche
    And L’utilisateur saisit son message
    And L’utilisateur envoie le message
    Then Le message est envoyé avec succès
    And L’historique des messages inclut le message envoyé