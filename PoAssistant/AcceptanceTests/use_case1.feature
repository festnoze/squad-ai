Fonctionnalité: Initier une conversation avec un officiel

Règle : Utilisateurs peuvent choisir un officiel parmi une liste pour démarrer une conversation

Scénario: Initier une conversation avec un officiel
    Etant donné que je suis connecté en tant qu’utilisateur
    Etant donné que je suis sur la page de messagerie
    Etant donné que je peux voir une liste d’officiels disponibles
    Quand je sélectionne un officiel dans la liste
    Alors l’officiel sélectionné devrait être ajouté comme destinataire de la conversation
    Et je devrais pouvoir taper mon message
    Et je devrais pouvoir envoyer le message

Règle : La possibilité d’initier des conversations est clairement signalée dans l’interface utilisateur

Scénario: Vérifier que la possibilité d’initier des conversations est signalée
    Etant donné que je suis connecté en tant qu’utilisateur
    Etant donné que je suis sur la page de messagerie
    Alors je devrais voir un bouton clairement indiqué pour initier une conversation avec un officiel

Règle : Les utilisateurs reçoivent confirmation que leur message a été envoyé

Scénario: Vérifier la confirmation d’envoi du message
    Etant donné que je suis connecté en tant qu’utilisateur
    Etant donné que je suis sur la page de messagerie
    Etant donné que j’ai déjà initié une conversation avec un officiel
    Quand j’envoie un message
    Alors je devrais voir une confirmation indiquant que mon message a été envoyé avec succès