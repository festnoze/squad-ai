Fonctionnalité: Gestion des modifications techniques pour la gestion des permissions
  Afin de restreindre les actions possibles sur les ressources ’brouillon’
  En tant qu’apprenant
  Je souhaite que les modifications nécessaires soient identifiées et implémentées correctement
 
Scénario: Les modifications nécessaires pour gérer les permissions autour des ressources ’brouillon’ sont identifiées et implémentées correctement
    Etant donné que je suis un apprenant
    Quand je consulte les ressources disponibles dans mon parcours d’apprentissage
    Alors je peux voir uniquement les ressources qui sont validées ou en statut ’brouillon’

Scénario: Les mécanismes d’autorisation prennent en compte le statut ’brouillon’ des ressources pour restreindre les actions possibles
    Etant donné que je suis un apprenant
    Quand je consulte les détails d’une ressource en statut ’brouillon’
    Alors je ne peux pas modifier ou supprimer cette ressource
    Et je ne peux pas marquer cette ressource comme complétée ou la mettre en favori