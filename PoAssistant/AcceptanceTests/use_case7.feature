Fonctionnalité: Mise en forme des messages

Scénario: Les utilisateurs ont accès à des options de mise en forme de texte pour leurs messages
    Etant donné que je suis un utilisateur connecté
    Et que je suis sur la page de rédaction d’un message
    Lorsque je tape du texte dans la zone de saisie du message
    Alors je devrais voir les options de mise en forme (gras, italique, etc.) disponibles
    
Scénario: La mise en forme est appliquée correctement et est visible dans l’aperçu avant l’envoi
    Etant donné que je suis un utilisateur connecté
    Et que je suis sur la page de rédaction d’un message
    Lorsque je tape du texte dans la zone de saisie du message
    Et que je sélectionne une option de mise en forme (gras, italique, etc.)
    Alors je devrais voir le texte mis en forme dans l’aperçu du message avant de l’envoyer
    
Scénario: Les options de mise en forme avancées sont réservées aux rôles spécifiés
    Etant donné que je suis un utilisateur connecté en tant que [rôle spécifié]
    Et que je suis sur la page de rédaction d’un message
    Lorsque je tape du texte dans la zone de saisie du message
    Et que je sélectionne une option de mise en forme avancée réservée aux [rôles spécifiés]
    Alors je devrais voir le texte mis en forme de manière avancée dans l’aperçu du message avant de l’envoyer