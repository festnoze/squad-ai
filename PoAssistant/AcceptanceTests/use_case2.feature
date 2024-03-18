Fonctionnalité: Gestion des prérequis pour la visualisation des ressources ’brouillon’
Afin de permettre aux apprenants de visualiser les ressources ’brouillon’ correspondantes, 
En tant qu’administrateur du LMS, 
Je souhaite définir et gérer les prérequis dans le système et permettre aux seuls apprenants remplissant ces prérequis de visualiser ces ressources.

Scénario: Les prérequis sont clairement définis et gérés dans le LMS
    Etant donné que je suis un administrateur connecté au LMS
    Lorsque je configure les prérequis pour une ressource ’brouillon’
    Alors je dois pouvoir saisir et enregistrer les prérequis requis pour cette ressource

Scénario: Seuls les apprenants ayant rempli les prérequis spécifiques peuvent visualiser les ressources ’brouillon’ correspondantes
    Etant donné que je suis un apprenant connecté au LMS
    Et que j’ai rempli tous les prérequis pour une ressource ’brouillon’
    Lorsque je consulte ma liste de ressources
    Alors je ne devrais voir que les ressources ’brouillon’ pour lesquelles j’ai rempli les prérequis

Scénario: Le système de gestion du parcours d’apprentissage du LMS permet de suivre les prérequis remplis par les apprenants
    Etant donné que je suis un apprenant connecté au LMS
    Et que je viens de remplir un prérequis pour une ressource ’brouillon’
    Lorsque je consulte mon parcours d’apprentissage
    Alors je devrais voir le prérequis que j’ai rempli pour cette ressource ’brouillon’ dans ma progression

Scénario: Les apprenants qui n’ont pas rempli les prérequis ne peuvent pas visualiser les ressources ’brouillon’
    Etant donné que je suis un apprenant connecté au LMS
    Et que je n’ai pas rempli tous les prérequis pour une ressource ’brouillon’
    Lorsque je consulte ma liste de ressources
    Alors je ne devrais pas voir cette ressource ’brouillon’ dans ma liste

Scénario: Les apprenants ne peuvent pas accéder aux ressources ’brouillon’ par une URL directe sans remplir les prérequis
    Etant donné que je suis un apprenant connecté au LMS
    Et que je dispose de l’URL d’une ressource ’brouillon’
    Lorsque j’accède directement à cette URL
    Alors je devrais être redirigé vers une page d’erreur indiquant que je ne remplis pas les prérequis pour cette ressource ’brouillon’