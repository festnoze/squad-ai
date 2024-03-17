Fonctionnalité : Organisation et recherche de messages
    En tant qu’utilisateur
    Afin de pouvoir organiser et rechercher facilement mes messages
    Je souhaite pouvoir les organiser par sujet ou par cours, et pouvoir les rechercher par mots-clés ou participants
    
Scénario : Organisation des messages par sujet
    Etant donné que je suis connecté en tant qu’utilisateur
    Lorsque je consulte la liste des messages
    Alors je devrais avoir la possibilité de les organiser par sujet
    
Scénario : Organisation des messages par cours
    Etant donné que je suis connecté en tant qu’utilisateur
    Lorsque je consulte la liste des messages
    Alors je devrais avoir la possibilité de les organiser par cours
    
Scénario : Création d’un espace de discussion spécifique à un sujet
    Etant donné que je suis connecté en tant qu’utilisateur
    Lorsque je clique sur le bouton "Créer un espace de discussion"
    Et que je saisis le nom du sujet dans le champ dédié
    Alors un nouvel espace de discussion devrait être créé spécifiquement pour ce sujet
    
Scénario : Création d’un espace de discussion spécifique à un cours
    Etant donné que je suis connecté en tant qu’utilisateur
    Lorsque je clique sur le bouton "Créer un espace de discussion"
    Et que je sélectionne un cours dans la liste déroulante
    Alors un nouvel espace de discussion devrait être créé spécifiquement pour ce cours
    
Scénario : Recherche de messages par mots-clés
    Etant donné que je suis connecté en tant qu’utilisateur
    Lorsque je saisis un mot-clé dans le champ de recherche
    Et que je clique sur le bouton "Rechercher"
    Alors seuls les messages contenant ce mot-clé devraient être affichés
    
Scénario : Recherche de messages par participants
    Etant donné que je suis connecté en tant qu’utilisateur
    Lorsque je sélectionne un participant dans la liste déroulante de recherche
    Et que je clique sur le bouton "Rechercher"
    Alors seuls les messages envoyés ou reçus par ce participant devraient être affichés