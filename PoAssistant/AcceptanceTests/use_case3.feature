Fonctionnalité : Attachement de fichiers aux messages avec restrictions

Scénario : Les utilisateurs peuvent attacher des fichiers à leurs messages
    Etant donné que je suis connecté(e) en tant qu’utilisateur
    Et que je suis sur la page de messagerie
    Quand je compose un nouveau message
    Et que j’attache un fichier au message
    Alors je devrais voir le fichier attaché dans la zone de message
    Et les autres utilisateurs devraient voir le fichier attaché dans le message reçu

Scénario: Les fichiers attachés ne doivent pas dépasser une taille maximale définie
    Etant donné que je suis connecté(e) en tant qu’utilisateur
    Et que je suis sur la page de messagerie
    Quand je compose un nouveau message
    Et que j’attache un fichier dont la taille est supérieure à la limite définie
    Alors je devrais voir un message d’erreur indiquant que la taille du fichier dépasse la limite autorisée
    Et les autres utilisateurs ne devraient pas voir le fichier attaché dans le message reçu

Scénario: Les types de fichiers autorisés doivent être préalablement définis pour des raisons de sécurité
    Etant donné que je suis connecté(e) en tant qu’utilisateur
    Et que je suis sur la page de messagerie
    Quand je compose un nouveau message
    Et que j’attache un fichier avec une extension non autorisée
    Alors je devrais voir un message d’erreur indiquant que le type de fichier n’est pas autorisé
    Et les autres utilisateurs ne devraient pas voir le fichier attaché dans le message reçu