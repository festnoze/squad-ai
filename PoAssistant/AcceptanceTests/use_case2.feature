Fonctionnalité : Utilisateur participe à des discussions publiques

Scenario: Les utilisateurs peuvent voir la liste des discussions publiques disponibles
    Given L’utilisateur est connecté à la plateforme LMS
    When L’utilisateur accède à la section des discussions publiques
    Then L’utilisateur voit la liste des discussions publiques disponibles

Scenario: Les utilisateurs peuvent rejoindre une discussion publique existante
    Given L’utilisateur est connecté à la plateforme LMS
    And L’utilisateur accède à la section des discussions publiques
    When L’utilisateur choisit une discussion publique existante
    And L’utilisateur clique sur le bouton "Rejoindre la discussion"
    Then L’utilisateur est ajouté à la discussion publique

Scenario: Les utilisateurs peuvent commencer une nouvelle discussion publique, sous réserve des règles de la plateforme
    Given L’utilisateur est connecté à la plateforme LMS
    And L’utilisateur accède à la section des discussions publiques
    When L’utilisateur clique sur le bouton "Nouvelle discussion publique"
    And L’utilisateur saisit les informations requises pour la nouvelle discussion
    And L’utilisateur poste la nouvelle discussion publique
    Then La nouvelle discussion publique est créée et apparaît dans la liste des discussions publiques disponibles