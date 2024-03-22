Fonctionnalité: Accéder au module de dessin depuis n’importe quelle interface

Scénario: Accéder au module de dessin depuis l’interface web de la plateforme LMS
  Given Je suis connecté à la plateforme LMS en tant qu’utilisateur
  When Je clique sur l’onglet "Module de dessin" dans l’interface web
  Then Le module de dessin s’ouvre correctement

Scénario: Accéder au module de dessin depuis l’application mobile de la plateforme LMS
  Given Je suis connecté à la plateforme LMS en tant qu’utilisateur
  When J’ouvre l’application mobile de la plateforme LMS
  And Je sélectionne l’option "Module de dessin" dans le menu
  Then Le module de dessin s’ouvre correctement

Scénario: L’interface utilisateur du module de dessin est responsive et adaptée à différents types d’écrans
  Given Je suis connecté à la plateforme LMS en tant qu’utilisateur
  When J’ouvre le module de dessin depuis l’interface web
  Then L’interface utilisateur du module de dessin s’adapte de manière appropriée à la taille de mon écran

  Given Je suis connecté à la plateforme LMS en tant qu’utilisateur
  When J’ouvre le module de dessin depuis l’application mobile
  Then L’interface utilisateur du module de dessin s’adapte de manière appropriée à la taille de mon écran