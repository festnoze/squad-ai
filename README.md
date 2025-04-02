# Liste des POCs du Repository "squad AI"

## Chatbot-Studi.com

Chatbot basé sur un système RAG permettant aux utilisateurs de poser des questions sur les formations et les données spécifiques à Studi.

**Back-office (pipeline d’ingestion)** :  
Récupération des données via API JSON Drupal et scraping web, suivi des étapes classiques d’un pipeline RAG : chunking, embedding, et insertion dans une base vectorielle.

**Front-office (pipeline d’inférence + UI )** :  
API de requêtage alimentée par la base vectorielle. Deux interfaces front-end sont disponibles : l’une en Streamlit, l’autre en Blazor.

---

## CodeDoc

Outil d’analyse de code C# backend utilisant Roslyn et un LLM. Il propose deux fonctionnalités principales :

**Génération de documentation** :  
Analyse du code source pour générer automatiquement des `summary` de méthode injectables dans les fichiers via un LLM.

**Exploration du code via RAG** :  
Construction d’un index RAG à partir des descriptions de méthode, permettant à un chatbot d’interroger le code existant et de retrouver des méthodes similaires, pour encourager la réutilisation et éviter la duplication (`Don't Repeat Yourself`).

---

## Fulfill Form with Audio & AI

POCs explorant différentes approches pour faciliter le remplissage dynamique de formulaires structurés.

**FulfillFormWithAudio** :  
Intégration de la voix comme modalité d’entrée, permettant à l’utilisateur de remplir un formulaire en interagissant oralement avec. L’outil convertit les réponses audio en données exploitables pour alimenter les champs (output parsing  sur modèle JSON, modèle full-speech, écoute en continue, basé sur Sementic Kernel plutôt que Langchain), UI en blazor.

**FulfillFormWithAI** :  
Autre approche pour le remplissage d'un formulaire (ou d'une structure d'input pour appeler un endpoint). 

- Création d'une structure générique de description d'un formulaire, composé de groupes et de champs, avec différentes méthodes de validation, tel que :  type de la valeur, valeur min/max, taille min/max, regex, liste de valeurs autorisés, ou via une fonction de validation externe.

- Chatbot conversationnel capable d'interogger l'utilisateur afin de remplir tous les champs (question groupée, demande de correction en cas d'échec de validation)
  
  
  
  Utilisation d’un workflow agentique basé sur LangGraph (et LangGraph Studio Web) pour piloter le remplissage progressif du formulaire, via plusieurs agents ou étapes conditionnelles.

---

## PoAssistant

Outil complet d’assistance à la rédaction d’EPICs et de User Stories pour les Product Owners.

Il utilise un LLM avec une approche de "socratic questioning" pour guider l’utilisateur dans la formalisation explicite et détaillée du besoin. 

Génèration automatiquement les User Stories associées, avec description et critères d’acceptance. 

Pour chaque critère d’acceptance, des scénarios de tests BDD sont générés automatiquement en Gherkin. Puis les squelettes des tests via Specflow.

---

## SlackAPI

Passerelle permettant la communication entre une application Slack et une API cible (motorisée par un LLM). Elle intercepte les événements en provenance de Slack (comme les messages directs) et peut être interfacée avec n'importe quelle API responsable de traiter la requête et de fournir une réponse (avec ou sans streaming).

---

## Autres projets

Les projets suivants ne nécessitent pas de description détaillée à ce stade :

- CrewAITest  
- DependencyAnalyser  
- GeneratedCrewAiSamples  
- LangChainUseCases  
- LangGraphApp  
- LlmCallGenericApp  
- MergeRequestTest  
