Fonctionnalité: Utiliser le module de dessin en mode collaboratif

Scénario: Plusieurs utilisateurs peuvent travailler sur le même dessin en temps réel
Étant donné que j’ai accès à la plateforme LMS
Et que je suis connecté à mon compte utilisateur
Quand je sélectionne le module de dessin
Et que j’invite un autre utilisateur à rejoindre mon dessin en utilisant son identifiant utilisateur
Alors nous pouvons tous les deux travailler sur le même dessin en temps réel
Et nos modifications sont synchronisées instantanément

Scénario: Le propriétaire du dessin peut contrôler les droits d’accès et de modification
Étant donné que j’ai accès à la plateforme LMS
Et que je suis connecté à mon compte utilisateur
Quand je crée un nouveau dessin
Alors je suis automatiquement désigné comme le propriétaire du dessin
Et j’ai tous les droits d’accès et de modification sur le dessin

Scénario: Le propriétaire peut définir les droits d’édition pour les autres utilisateurs
Étant donné que je suis le propriétaire d’un dessin
Quand j’invite un autre utilisateur à rejoindre mon dessin en utilisant son identifiant utilisateur
Et que je lui attribue les droits d’édition partiels
Alors cet utilisateur peut modifier certaines parties du dessin
Mais il ne peut pas modifier les parties du dessin auxquelles je lui ai restreint l’accès

Scénario: Le propriétaire peut définir les droits d’édition complets pour les autres utilisateurs
Étant donné que je suis le propriétaire d’un dessin
Quand j’invite un autre utilisateur à rejoindre mon dessin en utilisant son identifiant utilisateur
Et que je lui atribue les droits d’édition complets
Alors cet utilisateur peut modifier toutes les parties du dessin
Et il a les mêmes droits d’accès et de modification que moi en tant que propriétaire