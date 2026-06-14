Feature: Feedback
  Scenario: Prise en compte
    Given un feedback utilisateur
    When il est analysé
    Then une story est créée
