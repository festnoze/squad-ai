Fonctionnalité: Visualisation des ressources ’brouillon’ par l’apprenant

Scénario: Les ressources en statut ’brouillon’ sont visibles uniquement pour les apprenants remplissant les critères spécifiques
Etant donné un apprenant avec un compte validé et remplissant les critères spécifiques
Etant donné une ressource en statut ’brouillon’ dans le parcours d’apprentissage de l’apprenant
Quand l’apprenant accède à son parcours d’apprentissage
Alors l’apprenant voit la ressource en statut ’brouillon’

Scénario: Le titre, la mention ’indispensable’ ou non, une description ou résumé, le type de ressource, et une estimation de la date de disponibilité sont affichés
Etant donné un apprenant avec un compte validé et remplissant les critères spécifiques
Etant donné une ressource en statut ’brouillon’ avec un titre, une mention ’indispensable’ ou non, une description ou résumé, un type de ressource et une estimation de la date de disponibilité dans le parcours d’apprentissage de l’apprenant
Quand l’apprenant accède à la ressource en statut ’brouillon’
Alors l’apprenant voit le titre, la mention ’indispensable’ ou non, la description ou résumé, le type de ressource et l’estimation de la date de disponibilité de la ressource

Scénario: Les fonctionnalités d’interaction (commentaires, mise en favoris, téléchargement) sont désactivées pour les ressources ’brouillon’
Etant donné un apprenant avec un compte validé et remplissant les critères spécifiques
Etant donné une ressource en statut ’brouillon’ dans le parcours d’apprentissage de l’apprenant
Quand l’apprenant accède à la ressource en statut ’brouillon’
Alors l’apprenant ne voit pas les fonctionnalités d’interaction (commentaires, mise en favoris, téléchargement) pour la ressource

Scénario: Un moyen d’exprimer l’intérêt (’J’attends cela avec impatience’) est disponible et fonctionnel
Etant donné un apprenant avec un compte validé et remplissant les critères spécifiques
Etant donné une ressource en statut ’brouillon’ dans le parcours d’apprentissage de l’apprenant
Quand l’apprenant accède à la ressource en statut ’brouillon’
Et que l’apprenant clique sur le bouton ’J’attends cela avec impatience’
Alors la ressource est marquée comme étant attendue avec impatience par l’apprenant

Scénario: La visualisation des ressources ’brouillon’ n’influence pas le calcul de la progression de l’apprenant
Etant donné un apprenant avec un compte validé et remplissant les critères spécifiques
Etant donné une ressource en statut ’brouillon’ dans le parcours d’apprentissage de l’apprenant
Quand l’apprenant accède à la ressource en statut ’brouillon’
Alors la visualisation de la ressource n’affecte pas la progression de l’apprenant

Scénario: Les ressources ’brouillon’ sont visibles uniquement pour les apprenants remplissant les critères spécifiques, même en cas de ressources qui ne passent jamais en statut ’validé’
Etant donné un apprenant avec un compte validé et remplissant les critères spécifiques
Etant donné une ressource en statut ’brouillon’ dans le parcours d’apprentissage de l’apprenant qui ne passe jamais en statut ’validé’
Quand l’apprenant accède à son parcours d’apprentissage
Alors l’apprenant voit la ressource en statut ’brouillon’