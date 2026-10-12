# Jev : modèle et accès

Recherche vérifiée le 22 septembre 2026. Ce dossier est le répertoire de travail pour ce sujet.

## Ce que fait Jev

Jev est le modèle de décision de TypeSafe AI. On fournit un état (`state`) et des questions (`questions`). Les trois primitives sont :

- `choice` : sélection parmi des options définies, avec probabilités et confiance ;
- `score` : évaluation selon des niveaux décrits, avec probabilités et confiance ;
- `noul` : probabilité entre 0 et 1 que la réponse à une question soit oui.

Plusieurs questions peuvent partager le même état. Elles sont évaluées indépendamment : les dépendances entre décisions doivent être composées dans le code.

Source : [Introduction TypeSafe](https://docs.typesafe.ai/introduction).

Le typage borne les réponses possibles. Il ne garantit pas la justesse du jugement. Jev ne produit pas de texte libre ; pour extraire une chaîne, on peut lui proposer des candidats. TypeSafe documente notamment des faiblesses en calcul, comptage et comparaison de dates.

Source : [Limites de Jev 1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## OpenRouter

Oui, Jev est disponible sur OpenRouter sous l'identifiant `typesafe/jev-1.13`. La fiche affiche 32 000 tokens de contexte, 0,042 USD par million de tokens d'entrée et une sortie gratuite. Données susceptibles de changer.

Source : [Fiche Jev 1.13](https://openrouter.ai/typesafe/jev-1.13/).

L'interface actuellement exposée est spécifique aux décisions :

```text
POST https://openrouter.ai/api/alpha/decisions
Authorization: Bearer <OPENROUTER_API_KEY>
Content-Type: application/json
```

Le SDK officiel utilise `openRouter.alpha.decisions.create({ decisionsRequest: ... })`.

Conséquence pour une configuration existante : conserver la clé OpenRouter est possible, mais un client qui ne sait envoyer que `messages` à `/api/v1/chat/completions` doit être adapté. Changer uniquement le nom du modèle ne suffit pas pour utiliser cette interface. L'URL porte explicitement la mention `alpha`.

Sources : [Implémentation officielle de l'appel](https://github.com/OpenRouterTeam/typescript-sdk/blob/main/src/funcs/alphaDecisionsCreate.ts), [serveur de cette opération](https://github.com/OpenRouterTeam/typescript-sdk/blob/main/src/models/operations/createapialphadecisions.ts), [exemple officiel OpenRouter](https://openrouter.ai/labs/jev/compile).

Exemple de corps JSON, préparé à partir de la documentation, sans appel d'inférence effectué :

```json
{
  "model": "typesafe/jev-1.13",
  "state": "Mon compte est bloqué et je ne peux plus accéder à mes factures.",
  "questions": {
    "service": {
      "type": "choice",
      "instructions": "Quel service doit traiter la demande en priorité ?",
      "criteria": {
        "acces": "Connexion impossible ou compte bloqué.",
        "facturation": "Question sur un paiement sans problème d'accès.",
        "autre": "Aucune des catégories précédentes."
      }
    }
  }
}
```

## Accès direct TypeSafe

Créer une clé depuis la [console TypeSafe](https://console.typesafe.ai), puis appeler `POST https://api.typesafe.ai/v1/systemone` avec un jeton Bearer. Le modèle utilisé dans le quickstart est `jev-latest` (sans préfixe `typesafe/`). Le SDK Python s'installe via `pip install typesafe-sdk` et lit `TYPESAFE_API_KEY`.

Source : [Quickstart officiel](https://docs.typesafe.ai/introduction/quickstart).

Pour découvrir le comportement sans développer une intégration, utiliser le playground TypeSafe ou les [démos Jev Lab d'OpenRouter](https://openrouter.ai/labs/jev).

## État de validation

Recherche documentaire sur les sources officielles et lecture du code public du SDK OpenRouter. Aucun appel authentifié ou payant effectué. La compatibilité avec une configuration applicative précise reste à vérifier sur cette configuration.

## Jev comme évaluateur dans Langfuse

Vérification documentaire du 22 septembre 2026 : intégration possible via des scores externes. Aucun connecteur Jev natif identifié dans la documentation consultée.

La connexion LLM standard de Langfuse exige, pour une passerelle compatible OpenAI, le support du tool calling. Elle attend notamment un score et un raisonnement. L'API Decisions de Jev a un autre contrat ; sa présence sur OpenRouter ne suffit donc pas à le rendre interchangeable dans cette connexion.

Source : [Connexions LLM Langfuse](https://langfuse.com/docs/administration/llm-connection).

Architecture proposée : un processus d'évaluation externe récupère l'entrée, la réponse et les références nécessaires ; appelle Jev avec des critères atomiques ; puis transmet les résultats à Langfuse via son SDK/API en les rattachant à l'observation évaluée. Le déclenchement et les reprises sont gérés par ce processus.

Source : [Scores via API/SDK](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk).

Les code evaluators hébergés dans Langfuse ne sont pas un emplacement approprié pour cet appel : leur environnement bloque les sorties réseau.

Source : [Contraintes des code evaluators](https://langfuse.com/docs/evaluation/evaluation-methods/code-evaluators#runtime-constraints).

Correspondances proposées : Choice → score catégoriel ; Score → score numérique sur une échelle documentée ; Noul → score numérique de probabilité, éventuellement accompagné d'un booléen calculé par seuil. Conserver séparément la confiance disponible pour Choice/Score : elle ne représente pas la qualité de la réponse évaluée. Enregistrer modèle et version des critères pour comparer les résultats.

Candidats à tester : pertinence, ton, respect d'une consigne précise, appui sur un passage de référence. Conserver un juge génératif pour les justifications rédigées et les évaluations nécessitant un raisonnement complexe. Ce sont des recommandations d'architecture, pas des performances mesurées.

Avant substitution : faire tourner Jev et le juge actuel sur un même jeu annoté par des humains, mesurer les erreurs par critère, le coût et la latence ; régler les seuils sur ces données. Un mode hybride peut réserver le juge plus coûteux aux cas ambigus. Le typage ne valide pas la qualité du juge.
