Fonctionnalité: Interaction et accès aux profils via les listes de classe et les espaces de discussion

Critères d’acceptance:
1. Les utilisateurs doivent pouvoir accéder au profil d’un autre membre en cliquant sur son nom, si les permissions et les paramètres de confidentialité le permettent.
2. Les membres d’un même groupe de travail ou de classe ont la permission de voir le profil des autres membres.
3. Les fonctionnalités spécifiques pour l’envoi de messages privés doivent respecter les paramètres de confidentialité.

Scénarios de test:

Scénario: Accès au profil d’un autre membre via une liste de classe
Étant donné que je suis connecté en tant qu’utilisateur
Et que je suis membre d’une classe
Quand je navigue dans la liste des membres de la classe
Et je clique sur le nom d’un autre membre
Alors je devrais être redirigé vers le profil de ce membre

Scénario: Accès au profil d’un autre membre via un espace de discussion
Étant donné que je suis connecté en tant qu’utilisateur
Et que je suis membre d’un groupe de travail ou d’un espace de discussion
Quand je navigue dans les messages ou commentaires de cet espace
Et je clique sur le nom d’un membre mentionné
Alors je devrais être redirigé vers le profil de ce membre

Scénario: Vérification des permissions d’accès au profil d’un autre membre
Étant donné que je suis connecté en tant qu’utilisateur
Et que je suis membre d’une classe ou d’un groupe de travail
Quand j’essaie d’accéder au profil d’un autre membre
Et que je n’ai pas les permissions pour le voir
Alors je devrais recevoir un message d’erreur indiquant que je n’ai pas les permissions nécessaires pour accéder au profil

Scénario: Envoi de messages privés respectant les paramètres de confidentialité
Étant donné que je suis connecté en tant qu’utilisateur
Et que j’ai les permissions pour envoyer des messages privés
Quand j’envoie un message privé à un autre membre
Et que les paramètres de confidentialité de ce membre permettent de recevoir des messages privés
Alors le message privé devrait être correctement envoyé au destinataire

Scénario: Vérification des paramètres de confidentialité pour l’envoi de messages privés
Étant donné que je suis connecté en tant qu’utilisateur
Et que j’ai les permissions pour envoyer des messages privés
Quand j’essaie d’envoyer un message privé à un autre membre
Et que les paramètres de confidentialité de ce membre ne permettent pas de recevoir des messages privés
Alors je devrais recevoir un message d’erreur indiquant que ce membre ne souhaite pas recevoir de messages privés