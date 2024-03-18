Fonctionnalité: Notification aux apprenants lors de la disponibilité d’une ressource ’brouillon’

Scénario: Les apprenants ayant exprimé leur intérêt sont notifiés lorsque la ressource devient disponible
    Given un apprenant qui a exprimé son intérêt pour une ressource en statut ’brouillon’
    And la ressource est devenue disponible
    When le système envoie les notifications aux apprenants
    Then l’apprenant est notifié via email ou notification interne au LMS

Scénario: Le système de notification fonctionne correctement et envoie les notifications au bon moment
    Given un apprenant qui a exprimé son intérêt pour une ressource en statut ’brouillon’
    And la ressource est devenue disponible
    When le système envoie les notifications aux apprenants
    Then l’apprenant reçoit la notification au bon moment