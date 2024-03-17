Fonctionnalité: Confidentialité et sécurité des messages

Scénario: Chiffrement de bout en bout des messages
     Soit Alice est un apprenant dans une institution éducative
     Et Alice a ouvert l’application de messagerie
     Quand Alice envoie un message à Bob
     Alors Bob reçoit le message chiffré de bout en bout
     
Scénario: Accès aux conversations restreint selon le rôle de l’utilisateur
     Soit Alice est un administrateur dans une institution éducative
     Et Alice a ouvert l’application de messagerie
     Quand Alice accède aux conversations
     Alors Alice peut voir toutes les conversations de tous les utilisateurs
     
Scénario: Accès aux conversations restreint selon le rôle de l’utilisateur
     Soit Bob est un enseignant dans une institution éducative
     Et Bob a ouvert l’application de messagerie
     Quand Bob accède aux conversations
     Alors Bob peut voir les conversations des apprenants dont il est l’enseignant
     
Scénario: Accès aux conversations restreint selon le rôle de l’utilisateur
     Soit Charlie est un apprenant dans une institution éducative
     Et Charlie a ouvert l’application de messagerie
     Quand Charlie accède aux conversations
     Alors Charlie peut voir seulement ses propres conversations