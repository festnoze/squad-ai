Fonctionnalité: Envoi et réception de fichiers

Critères d’acceptance:
- Les utilisateurs peuvent joindre des fichiers à leurs messages selon des critères prédéfinis (taille, format).
- Les restrictions (taille, format) sont clairement communiquées aux utilisateurs.
- Les utilisateurs reçoivent un feedback immédiat en cas d’échec de l’envoi d’un fichier non conforme.

Scénario: Envoi d’un fichier conforme
    Etant donné que je suis connecté en tant qu’utilisateur
    Et que je suis dans une conversation avec un autre utilisateur
    Lorsque j’envoie un message en y joignant un fichier de format PDF
    Alors le système envoie le fichier avec succès
    Et les utilisateurs peuvent accéder et télécharger le fichier dans la conversation

Scénario: Envoi d’un fichier non conforme (format incorrect)
    Etant donné que je suis connecté en tant qu’utilisateur
    Et que je suis dans une conversation avec un autre utilisateur
    Lorsque j’essaie d’envoyer un fichier de format EXE
    Alors le système bloque l’envoi du fichier avec un message d’erreur mentionnant le format non autorisé
    Et les utilisateurs ne peuvent pas accéder ou télécharger le fichier dans la conversation

Scénario: Envoi d’un fichier non conforme (taille trop grande)
    Etant donné que je suis connecté en tant qu’utilisateur
    Et que je suis dans une conversation avec un autre utilisateur
    Lorsque j’essaie d’envoyer un fichier de taille supérieure à0 Mo
    Alors le système bloque l’envoi du fichier avec un message d’erreur mentionnant la taille maximum autorisée
    Et les utilisateurs ne peuvent pas accéder ou télécharger le fichier dans la conversation