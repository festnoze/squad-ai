Fonctionnalité: Gestion des notifications

Scénario: Les notifications de nouveaux messages s’affichent en temps réel
    Etant donné que je suis connecté à mon compte utilisateur
    Et que je suis sur la page principale du module de messagerie
    Et que j’attends un nouveau message
    Lorsqu’un nouveau message est envoyé
    Alors je devrais voir une notification en temps réel

Scénario: Les utilisateurs peuvent personnaliser leurs préférences de notification (immédiatement)
    Etant donné que je suis connecté à mon compte utilisateur
    Et que je suis sur la page des paramètres de notification
    Lorsque je choisis l’option "immédiatement"
    Alors je devrais recevoir des notifications dès qu’un nouveau message arrive

Scénario: Les utilisateurs peuvent personnaliser leurs préférences de notification (une fois par jour)
    Etant donné que je suis connecté à mon compte utilisateur
    Et que je suis sur la page des paramètres de notification
    Lorsque je choisis l’option "une fois par jour"
    Alors je devrais recevoir un récapitulatif quotidien de toutes les notifications du jour

Scénario: Les utilisateurs peuvent personnaliser leurs préférences de notification (désactivation)
    Etant donné que je suis connecté à mon compte utilisateur
    Et que je suis sur la page des paramètres de notification
    Lorsque je choisis l’option "désactivation"
    Alors je ne devrais recevoir aucune notification

Scénario: Les notifications sont fonctionnelles sur les versions mobiles
    Etant donné que je suis connecté à mon compte utilisateur depuis mon téléphone mobile
    Et que je suis sur la page principale du module de messagerie
    Et que j’attends un nouveau message
    Lorsqu’un nouveau message est envoyé
    Alors je devrais voir une notification sur mon téléphone mobile

Scénario: Les notifications sont fonctionnelles sur les versions de bureau
    Etant donné que je suis connecté à mon compte utilisateur depuis mon ordinateur de bureau
    Et que je suis sur la page principale du module de messagerie
    Et que j’attends un nouveau message
    Lorsqu’un nouveau message est envoyé
    Alors je devrais voir une notification sur mon ordinateur de bureau