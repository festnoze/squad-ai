Fonctionnalité: Utilisation de la messagerie individuelle et en groupe pour collaboration sur des projets

Scénario: Envoi de messages individuels
  Etant donné que je suis connecté en tant qu’utilisateur A
  Etant donné que je suis sur la page de messagerie
  Quand je saisis le destinataire du message "utilisateur B"
  Et que je saisis le contenu du message "Salut, comment ça va ?"
  Et que je clique sur le bouton "Envoyer"
  Alors le message est envoyé avec succès à "utilisateur B"
  Et "utilisateur B" reçoit le message dans sa boîte de réception

Scénario: Envoi de messages en groupe
  Etant donné que je suis connecté en tant qu’utilisateur A
  Etant donné que je suis sur la page de messagerie
  Quand je crée un groupe de messagerie nommé "Projet de cours"
  Et que j’invite les utilisateurs "utilisateur B" et "utilisateur C" dans le groupe
  Et que je saisis le contenu du message "Bonjour à tous !"
  Et que je clique sur le bouton "Envoyer"
  Alors le message est envoyé avec succès au groupe "Projet de cours"
  Et tous les membres du groupe reçoivent le message dans leur boîte de réception

Scénario: Création et gestion des groupes par les officiels et administrateurs
  Etant donné que je suis connecté en tant qu’officiel ou administrateur
  Etant donné que je suis sur la page de gestion des groupes
  Quand je crée un groupe de messagerie nommé "Projet de cours"
  Et que j’invite les utilisateurs "utilisateur A" et "utilisateur B" dans le groupe
  Alors le groupe "Projet de cours" est créé avec succès
  Et les utilisateurs "utilisateur A" et "utilisateur B" sont membres du groupe

Scénario: Création et gestion des groupes par les officiels et administrateurs (suite)
  Etant donné que je suis connecté en tant qu’officiel ou administrateur
  Etant donné que je suis sur la page de gestion des groupes
  Quand je supprime le groupe "Projet de cours"
  Alors le groupe "Projet de cours" est supprimé avec succès
  Et les utilisateurs "utilisateur A" et "utilisateur B" ne sont plus membres du groupe