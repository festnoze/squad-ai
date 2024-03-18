Fonctionnalité: Gestion des notifications de messages

Scénario: Personnalisation des préférences de notification par type de message
    Etant donné un utilisateur connecté
    Lorsque l’utilisateur accède à ses préférences de notification
    Et que l’utilisateur sélectionne le type de message "Nouveau message privé"
    Et que l’utilisateur active la notification pour ce type de message
    Alors les préférences de notification sont enregistrées
    Et l’utilisateur recevra des notifications pour les nouveaux messages privés

Scénario: Personnalisation des préférences de notification par expéditeur
    Etant donné un utilisateur connecté
    Lorsque l’utilisateur accède à ses préférences de notification
    Et que l’utilisateur sélectionne un expéditeur spécifique
    Et que l’utilisateur active la notification pour cet expéditeur
    Alors les préférences de notification sont enregistrées
    Et l’utilisateur recevra des notifications pour les messages provenant de cet expéditeur

Scénario: Personnalisation des préférences de notification par thématique
    Etant donné un utilisateur connecté
    Lorsque l’utilisateur accède à ses préférences de notification
    Et que l’utilisateur sélectionne une thématique spécifique
    Et que l’utilisateur active la notification pour cette thématique
    Alors les préférences de notification sont enregistrées
    Et l’utilisateur recevra des notifications pour les messages liés à cette thématique

Scénario: Application instantanée des modifications des préférences de notification
    Etant donné un utilisateur connecté
    Lorsque l’utilisateur modifie ses préférences de notification
    Alors les modifications sont appliquées instantanément
    Et l’utilisateur recevra les notifications selon les nouvelles préférences

Scénario: Notification sans retard selon les préférences de l’utilisateur
    Etant donné un utilisateur connecté
    Lorsqu’un autre utilisateur envoie un message à l’utilisateur connecté
    Et que l’utilisateur a des préférences de notification activées
    Et que l’utilisateur a une connexion Internet stable
    Alors l’utilisateur reçoit une notification sans délai
    Et la notification correspond aux préférences de l’utilisateur.