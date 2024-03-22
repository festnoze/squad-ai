Critère d’acceptance: Les utilisateurs doivent pouvoir sauvegarder leurs dessins dans un espace personnel sur la plateforme

Scénario: Sauvegarder un dessin dans un espace personnel
Étant donné un utilisateur connecté sur la plateforme LMS
Lorsqu’il crée un dessin
Et qu’il choisit de le sauvegarder
Alors le dessin est enregistré dans l’espace personnel de l’utilisateur
Et l’utilisateur reçoit une confirmation de la sauvegarde

Scénario: Accéder à un dessin sauvegardé dans son espace personnel
Étant donné un utilisateur connecté sur la plateforme LMS
Et un dessin sauvegardé dans son espace personnel
Quand il accède à la liste de ses dessins sauvegardés
Alors il peut voir la liste de ses dessins
Et il peut sélectionner un dessin pour le modifier ou le visualiser


Critère d’acceptance: Les dessins sauvegardés doivent pouvoir être partagés avec d’autres utilisateurs de la plateforme, en fonction des rôles (étudiants, enseignants, administrateurs)

Scénario: Partager un dessin avec un autre utilisateur
Étant donné un utilisateur connecté sur la plateforme LMS
Et un dessin sauvegardé dans son espace personnel
Et un autre utilisateur de la plateforme
Quand l’utilisateur partage le dessin avec l’autre utilisateur
Alors l’autre utilisateur peut accéder au dessin partagé
Et il peut le visualiser ou le modifier selon ses permissions

Scénario: Modifier les permissions de partage d’un dessin
Étant donné un utilisateur connecté en tant qu’administrateur sur la plateforme LMS
Et un dessin sauvegardé dans l’espace personnel d’un utilisateur
Quand l’administrateur modifie les permissions de partage du dessin
Alors les nouvelles permissions sont appliquées
Et seul le groupe d’utilisateurs autorisé peut accéder au dessin partagé


Critère d’acceptance: Les permissions de partage et d’accès aux dessins doivent être configurables afin de respecter l’intégrité académique et la confidentialité

Scénario: Configurer les permissions de partage
Étant donné un utilisateur connecté en tant qu’administrateur sur la plateforme LMS
Et un dessin sauvegardé dans l’espace personnel d’un utilisateur
Quand l’administrateur configure les permissions de partage pour ce dessin (par exemple, permettre l’accès aux enseignants uniquement)
Alors seuls les utilisateurs ayant le rôle d’enseignant peuvent accéder au dessin partagé
Et les autres utilisateurs ne peuvent pas voir ou modifier le dessin

Scénario: Respecter la confidentialité des dessins sauvegardés
Étant donné différentes utilisateurs connectés sur la plateforme LMS, avec des rôles différents (étudiants, enseignants, administrateurs)
Et un dessin sauvegardé dans l’espace personnel d’un utilisateur
Quand un utilisateur tente d’accéder à un dessin dont il n’a pas les permissions
Alors il reçoit un message d’erreur indiquant qu’il n’est pas autorisé à voir ou modifier le dessin
Et le dessin reste confidentiel pour cet utilisateur