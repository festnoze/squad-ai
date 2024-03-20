Fonctionnalité: Affichage des noms dans les profils utilisateurs

Scénario: Les apprenants voient seulement leur nom complet dans leur profil, mais ont accès au nom et à l’initiale du prénom des autres dans les contextes sécurisés.
  Given un apprenant est connecté à la plateforme LMS
  When il consulte son profil
  Then il voit son nom complet
  And il voit le nom et l’initiale du prénom des autres apprenants dans les contextes sécurisés

Scénario: Les enseignants voient les noms complets de tous leurs apprenants dans les profils.
  Given un enseignant est connecté à la plateforme LMS
  When il consulte son profil
  Then il voit son nom complet
  And il voit les noms complets de tous ses apprenants

Scénario: Les administrateurs ont accès aux noms complets de tous les utilisateurs.
  Given un administrateur est connecté à la plateforme LMS
  When il consulte son profil
  Then il voit son nom complet
  And il voit les noms complets de tous les utilisateurs

Scénario: Les utilisateurs peuvent configurer la visibilité de leur nom complet dans les paramètres de confidentialité.
  Given un utilisateur est connecté à la plateforme LMS
  When il accède aux paramètres de confidentialité
  Then il peut configurer la visibilité de son nom complet
  And la visibilité de son nom complet est mise à jour conformément à sa configuration