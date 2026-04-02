const quizData = {
  step_01: {
    title: "Step 1 - Agent basique + 1 Tool",
    questions: [
      {
        question: "Quel nom de variable ADK cherche-t-il dans agent.py ?",
        options: ["main_agent", "root_agent", "agent", "my_agent"],
        correct: 1,
        explanation: "ADK cherche toujours la variable `root_agent` dans agent.py. C'est une convention obligatoire."
      },
      {
        question: "Qu'est-ce que le LLM lit pour comprendre quand utiliser un tool ?",
        options: ["Le nom du fichier", "La docstring de la fonction", "Le type de retour", "Le nombre de parametres"],
        correct: 1,
        explanation: "La docstring est envoyee au LLM comme description du tool. C'est son guide pour savoir quand l'appeler."
      },
      {
        question: "Quel format de retour est recommande pour un tool ADK ?",
        options: ["Une string", "Un tuple", "Un dict avec une cle 'status'", "Un entier"],
        correct: 2,
        explanation: "ADK recommande de retourner un dict avec \"status\": \"success\" ou \"error\". Les retours non-dict sont auto-wrappes en {\"result\": valeur}."
      },
      {
        question: "Que contient le fichier __init__.py d'un agent ADK ?",
        options: ["La definition de l'agent", "from . import agent", "import google.adk", "Rien, il est vide"],
        correct: 1,
        explanation: "__init__.py contient exactement `from . import agent` pour qu'ADK puisse charger le module."
      },
      {
        question: "Pourquoi un tool MOCK ne doit PAS pretendre generer du contenu dynamique ?",
        options: [
          "Parce qu'ADK l'interdit",
          "Parce qu'un mock retourne toujours la meme chose, le LLM voit l'incoherence et s'excuse",
          "Parce qu'un tool ne peut jamais generer de contenu",
          "Parce que les tools ne peuvent pas retourner de strings"
        ],
        correct: 1,
        explanation: "Un tool MOCK qui pretend generer du contenu mais retourne toujours la meme chose confond le LLM. En revanche, en production, un tool peut tout a fait generer du contenu reel (appel API, autre LLM, AgentTool, base de donnees, etc.)."
      }
    ]
  },
  step_02: {
    title: "Step 2 - Plusieurs Tools",
    questions: [
      {
        question: "Comment le LLM choisit-il quel tool appeler ?",
        options: [
          "Il appelle toujours le premier de la liste",
          "Il lit le schema de tous les tools (nom + docstring + params) et choisit le plus pertinent",
          "Il les appelle tous et garde le meilleur resultat",
          "L'utilisateur doit specifier le tool a utiliser"
        ],
        correct: 1,
        explanation: "Le LLM recoit le schema de TOUS les tools et decide lequel est le plus pertinent pour la requete de l'utilisateur."
      },
      {
        question: "Un tool sans parametre (ex: list_templates()) est-il valide ?",
        options: ["Non, il faut au moins 1 parametre", "Oui, c'est parfaitement valide", "Oui mais seulement si il retourne un dict", "Non, ADK refuse les fonctions sans argument"],
        correct: 1,
        explanation: "Une fonction sans parametre est un tool valide. Le LLM l'appellera quand c'est pertinent."
      },
      {
        question: "Que se passe-t-il si deux tools ont des docstrings tres similaires ?",
        options: [
          "ADK leve une erreur",
          "Le LLM risque de confondre les deux et choisir le mauvais",
          "Le premier dans la liste est toujours prefere",
          "Les deux sont appeles en parallele"
        ],
        correct: 1,
        explanation: "Des docstrings trop similaires rendent le routing ambigu pour le LLM. Il faut des descriptions distinctes et specifiques."
      },
      {
        question: "Les type hints (ex: `city: str`) servent a :",
        options: [
          "Rien, c'est juste du style Python",
          "Generer le schema JSON que le LLM voit pour chaque parametre",
          "Valider les inputs a runtime",
          "Documenter le code pour les developpeurs"
        ],
        correct: 1,
        explanation: "ADK utilise les type hints pour generer le schema JSON du tool. Le LLM voit ce schema pour savoir quels parametres passer et de quel type."
      }
    ]
  },
  step_03: {
    title: "Step 3 - Runtime, Config & Donnees avancees",
    questions: [
      {
        question: "A quoi sert generate_content_config sur un Agent ?",
        options: [
          "A choisir le modele LLM",
          "A configurer le comportement du LLM (temperature, max_tokens, safety)",
          "A definir le format de sortie",
          "A configurer les tools"
        ],
        correct: 1,
        explanation: "generate_content_config permet de regler temperature (creativite), max_output_tokens (longueur), et safety_settings du LLM."
      },
      {
        question: "Quelle est la difference entre State et Artifacts ?",
        options: [
          "State est plus rapide",
          "State = key-value texte, Artifacts = fichiers binaires versionnes (images, PDF)",
          "Artifacts ne persistent pas",
          "State ne fonctionne qu'avec InMemorySessionService"
        ],
        correct: 1,
        explanation: "State stocke des valeurs simples (strings, nombres). Artifacts stockent des fichiers binaires avec versioning automatique."
      },
      {
        question: "Quelle est la difference entre State et Memory ?",
        options: [
          "Memory est plus rapide",
          "State = memoire de session, Memory = memoire cross-sessions (long terme, recherche semantique)",
          "State ne persiste jamais",
          "Memory remplace State en production"
        ],
        correct: 1,
        explanation: "State vit dans une session. Memory (MemoryService) est un archive searchable qui couvre plusieurs sessions passees."
      },
      {
        question: "Comment executer un agent depuis du code Python (sans adk web) ?",
        options: [
          "agent.run()",
          "Runner(agent=...).run_async() qui retourne un generateur async d'events",
          "exec(agent)",
          "Agent.execute()"
        ],
        correct: 1,
        explanation: "En production, on utilise Runner.run_async() avec un SessionService. C'est le passage de 'demo adk web' a 'application reelle'."
      },
      {
        question: "Que fait output_schema sur un Agent ?",
        options: [
          "Definit le format des tools",
          "Force le LLM a retourner du JSON conforme a un schema Pydantic",
          "Valide les inputs de l'utilisateur",
          "Configure le format de la base de donnees"
        ],
        correct: 1,
        explanation: "output_schema prend un BaseModel Pydantic et force le LLM a retourner du JSON structure. Attention : avec tools, seulement fiable sur Gemini 3.0+."
      }
    ]
  },
  step_04: {
    title: "Step 4 - Session State & ToolContext",
    questions: [
      {
        question: "Comment un tool accede-t-il au state de la session ?",
        options: [
          "Via une variable globale",
          "En ajoutant `tool_context: ToolContext` comme parametre",
          "En lisant un fichier .state",
          "Via l'instruction de l'agent"
        ],
        correct: 1,
        explanation: "Ajouter `tool_context: ToolContext` comme parametre permet d'acceder a tool_context.state. ADK l'injecte automatiquement, le LLM ne le voit pas."
      },
      {
        question: "Quelle est la portee d'une cle avec le prefixe `temp:` ?",
        options: [
          "Toute la session",
          "Toutes les sessions de l'utilisateur",
          "L'invocation courante uniquement (perdue apres)",
          "Toutes les sessions de l'application"
        ],
        correct: 2,
        explanation: "Le prefixe `temp:` limite la portee a l'invocation courante. La valeur disparait apres."
      },
      {
        question: "Que fait `output_key=\"last_response\"` sur un Agent ?",
        options: [
          "Stocke le dernier message de l'utilisateur",
          "Sauvegarde automatiquement la reponse texte de l'agent dans state[\"last_response\"]",
          "Definit le nom du fichier de sortie",
          "Limite la taille de la reponse"
        ],
        correct: 1,
        explanation: "output_key sauvegarde automatiquement la reponse texte finale de l'agent dans le state a la cle specifiee."
      },
      {
        question: "Que fait `{current_spec}` dans une instruction d'agent ?",
        options: [
          "C'est un commentaire ignore",
          "Ca remplace la valeur par state[\"current_spec\"] au runtime",
          "Ca cree une variable current_spec",
          "Ca appelle un tool nomme current_spec"
        ],
        correct: 1,
        explanation: "Les {cles} dans l'instruction sont remplacees par les valeurs du state au moment de l'execution. Si state[\"current_spec\"] = \"tri\", le LLM recoit \"tri\"."
      },
      {
        question: "Pourquoi ne faut-il JAMAIS modifier le state directement sur un objet session recupere ?",
        options: [
          "Ca leve une exception",
          "Ca bypasse l'historique des events, n'est pas persistant, et n'est pas thread-safe",
          "Le state est en lecture seule",
          "Ca n'a aucun effet"
        ],
        correct: 1,
        explanation: "Modifier session.state directement bypasse le systeme d'events d'ADK, ce qui casse la persistance, l'audit, et la thread-safety. Toujours passer par ToolContext.state ou CallbackContext.state."
      }
    ]
  },
  step_05: {
    title: "Step 5 - Delegation Multi-Agent",
    questions: [
      {
        question: "Sur quoi le coordinateur se base-t-il pour deleguer a un sub-agent ?",
        options: [
          "Le nom du sub-agent",
          "Le champ `description` de chaque sub-agent",
          "L'ordre dans la liste sub_agents",
          "Les tools du sub-agent"
        ],
        correct: 1,
        explanation: "Le LLM du coordinateur lit le `description` de chaque sub-agent pour decider a qui deleguer. Des descriptions claires et specifiques sont essentielles."
      },
      {
        question: "Un coordinateur peut-il avoir des tools ET des sub_agents ?",
        options: [
          "Non, c'est l'un ou l'autre",
          "Oui, il peut combiner sub_agents (delegation) et tools comme AgentTool (appel sans transfert de controle)",
          "Oui, mais les tools sont ignores si sub_agents est defini",
          "Non, ADK leve une erreur"
        ],
        correct: 1,
        explanation: "Un agent peut combiner sub_agents et tools. Avec sub_agents, le controle est transfere. Avec AgentTool dans tools, le parent garde le controle et recoit le resultat comme un appel de tool classique."
      },
      {
        question: "Quelle est la difference entre sub_agents et AgentTool ?",
        options: [
          "sub_agents est plus rapide",
          "sub_agents transfere le controle, AgentTool garde le parent en controle (comme un appel de fonction)",
          "AgentTool ne peut pas utiliser de LLM",
          "Il n'y a pas de difference"
        ],
        correct: 1,
        explanation: "Avec sub_agents, le parent transfere le controle au sub-agent qui repond directement a l'utilisateur. Avec AgentTool, le parent appelle l'agent comme un tool, recoit le resultat, et reste en controle pour reformuler la reponse."
      },
      {
        question: "Comment le LLM declenche-t-il la delegation a un sub-agent ?",
        options: [
          "En retournant le nom de l'agent",
          "En generant un appel transfer_to_agent(agent_name='...') automatiquement",
          "En ecrivant dans le state",
          "Le developpeur doit coder le routing manuellement"
        ],
        correct: 1,
        explanation: "ADK expose automatiquement une fonction transfer_to_agent que le LLM peut appeler pour deleguer a un sub-agent nomme."
      }
    ]
  },
  step_06: {
    title: "Step 6 - SequentialAgent",
    questions: [
      {
        question: "Quelle est la difference cle entre SequentialAgent et la delegation (Step 4) ?",
        options: [
          "SequentialAgent est plus rapide",
          "SequentialAgent est deterministe (ordre fixe), la delegation est decidee par le LLM",
          "SequentialAgent utilise un seul LLM",
          "Il n'y a pas de difference"
        ],
        correct: 1,
        explanation: "SequentialAgent execute toujours ses sub-agents dans le meme ordre. La delegation LLM (Step 4) laisse le LLM choisir dynamiquement."
      },
      {
        question: "Un SequentialAgent a-t-il un `model` et une `instruction` ?",
        options: [
          "Oui, comme tout agent",
          "Non, c'est un orchestrateur pur sans LLM",
          "Seulement un model, pas d'instruction",
          "Seulement une instruction, pas de model"
        ],
        correct: 1,
        explanation: "SequentialAgent n'a PAS de model ni d'instruction. C'est un orchestrateur deterministe qui execute ses sub-agents en sequence."
      },
      {
        question: "Comment les donnees circulent-elles entre les agents d'un SequentialAgent ?",
        options: [
          "Via des variables globales",
          "Via output_key (ecriture) et {state_var} (lecture dans l'instruction)",
          "Via des appels de fonction directs",
          "Via des fichiers temporaires"
        ],
        correct: 1,
        explanation: "L'agent N ecrit dans le state via output_key, et l'agent N+1 lit cette valeur via {cle} dans son instruction."
      }
    ]
  },
  step_07: {
    title: "Step 7 - ParallelAgent",
    questions: [
      {
        question: "Les agents dans un ParallelAgent partagent-ils le state pendant l'execution ?",
        options: [
          "Oui, en temps reel",
          "Non, chaque branche est isolee pendant l'execution",
          "Oui, mais seulement les cles temp:",
          "Ca depend de la configuration"
        ],
        correct: 1,
        explanation: "Pendant l'execution parallele, les branches ne voient PAS les modifications de state des autres. Chaque branche lit le state tel qu'il etait au demarrage. Les output_key sont merges apres."
      },
      {
        question: "Quel est le pattern classique pour utiliser ParallelAgent ?",
        options: [
          "ParallelAgent seul",
          "SequentialAgent(writer, ParallelAgent(...), synthesizer)",
          "LoopAgent(ParallelAgent(...))",
          "ParallelAgent dans un ParallelAgent"
        ],
        correct: 1,
        explanation: "Le pattern classique : un agent ecrit en amont, le ParallelAgent traite en parallele, puis un synthesizer combine les resultats. Le tout dans un SequentialAgent."
      },
      {
        question: "L'ordre des sub-agents dans un ParallelAgent a-t-il de l'importance ?",
        options: [
          "Oui, le premier est execute en priorite",
          "Non, ils demarrent tous en meme temps",
          "Oui, ca determine l'ordre des resultats",
          "Non, mais le premier recoit plus de ressources"
        ],
        correct: 1,
        explanation: "Dans un ParallelAgent, l'ordre dans la liste est irrelevant. Tous les agents demarrent en meme temps et s'executent independamment."
      }
    ]
  },
  step_08: {
    title: "Step 8 - LoopAgent",
    questions: [
      {
        question: "Comment sortir d'un LoopAgent avant max_iterations ?",
        options: [
          "return False dans un tool",
          "tool_context.actions.escalate = True",
          "raise StopIteration",
          "tool_context.stop_loop()"
        ],
        correct: 1,
        explanation: "Mettre tool_context.actions.escalate = True dans un tool signale a ADK d'arreter la boucle apres le sub-agent courant."
      },
      {
        question: "Le state persiste-t-il entre les iterations d'un LoopAgent ?",
        options: [
          "Non, le state est reinitialise a chaque iteration",
          "Oui, le state persiste entre les iterations",
          "Seulement les cles user:",
          "Seulement les cles temp:"
        ],
        correct: 1,
        explanation: "Le state persiste entre les iterations. C'est ce qui permet la boucle de retroaction : le feedback de l'iteration N est visible en N+1."
      },
      {
        question: "Quand le signal `escalate` arrete-t-il la boucle ?",
        options: [
          "Immediatement, en plein milieu du sub-agent courant",
          "Apres que le sub-agent courant a fini son execution",
          "Au debut de l'iteration suivante",
          "Apres un delai configurable"
        ],
        correct: 1,
        explanation: "Le signal escalate arrete la boucle APRES que le sub-agent courant a termine. Il ne l'interrompt pas en plein milieu."
      },
      {
        question: "Quel agent devrait appeler `escalate` dans une boucle creation/critique ?",
        options: [
          "Le createur (writer)",
          "Le critique (reviewer) - car c'est lui qui evalue la qualite",
          "Le LoopAgent lui-meme",
          "Un agent externe"
        ],
        correct: 1,
        explanation: "C'est le reviewer qui decide si la qualite est suffisante. C'est donc lui qui appelle escalate pour sortir de la boucle."
      }
    ]
  },
  step_09: {
    title: "Step 9 - Callbacks",
    questions: [
      {
        question: "Quelle est la signature de before_model_callback ?",
        options: [
          "(request) -> response",
          "(context: Context, llm_request: LlmRequest) -> Optional[LlmResponse]",
          "(agent, request) -> response",
          "(callback_context, request, response) -> None"
        ],
        correct: 1,
        explanation: "La signature est (Context, LlmRequest) -> Optional[LlmResponse]. Retourner None laisse passer, retourner un LlmResponse bloque le LLM."
      },
      {
        question: "Que se passe-t-il quand before_model_callback retourne `None` ?",
        options: [
          "La requete est bloquee",
          "La requete est envoyee normalement au LLM",
          "Une erreur est levee",
          "Le callback suivant est appele"
        ],
        correct: 1,
        explanation: "Retourner None = laisser passer. La requete continue normalement vers le LLM."
      },
      {
        question: "Quelle est la signature de before_tool_callback ?",
        options: [
          "(tool, args) -> dict",
          "(context, tool, args) -> dict",
          "(tool: BaseTool, args: dict, context: Context) -> Optional[dict]",
          "(tool_name: str, args: dict) -> Optional[dict]"
        ],
        correct: 2,
        explanation: "La signature est (BaseTool, dict, Context) -> Optional[dict]. Retourner un dict = skip le tool, retourner None = executer le tool."
      },
      {
        question: "Pourquoi utiliser un callback plutot qu'un if/else dans le tool ?",
        options: [
          "Les callbacks sont plus rapides",
          "Les callbacks sont transversaux : ils s'appliquent a tous les tools/requetes sans modifier le code de chaque tool",
          "Les if/else ne fonctionnent pas dans ADK",
          "Les callbacks utilisent moins de memoire"
        ],
        correct: 1,
        explanation: "Les callbacks sont des guardrails transversaux : un seul callback protege tous les tools ou toutes les requetes, sans dupliquer la logique de validation."
      }
    ]
  },
  step_10: {
    title: "Step 10 - Code Forge Complet",
    questions: [
      {
        question: "Quelle est la profondeur d'imbrication maximale dans Code Forge ?",
        options: [
          "1 niveau",
          "2 niveaux",
          "SequentialAgent > LoopAgent > SequentialAgent > ParallelAgent = 4 niveaux",
          "3 niveaux"
        ],
        correct: 2,
        explanation: "code_forge (Sequential) > refinement_loop (Loop) > review_cycle (Sequential) > parallel_reviewers (Parallel) = 4 niveaux d'imbrication."
      },
      {
        question: "Qui declenche l'escalation pour sortir du LoopAgent dans Code Forge ?",
        options: [
          "Le code_writer",
          "Le synthesizer via evaluate_and_decide quand le score >= 8",
          "Le ParallelAgent quand tous les reviewers ont fini",
          "Le test_writer"
        ],
        correct: 1,
        explanation: "Le synthesizer appelle evaluate_and_decide qui met escalate = True quand le score global est >= 8."
      },
      {
        question: "Pourquoi le test_writer est-il EN DEHORS du LoopAgent ?",
        options: [
          "Pour des raisons de performance",
          "Parce qu'on ne genere les tests qu'une fois, sur le code final approuve",
          "Parce qu'il n'a pas besoin de ToolContext",
          "Parce qu'il utilise un model different"
        ],
        correct: 1,
        explanation: "Les tests ne sont generes qu'une seule fois, sur le code final qui a passe toutes les reviews. Il serait inutile de les regenerer a chaque iteration."
      },
      {
        question: "Combien de concepts differents sont combines dans Step 9 ?",
        options: ["3", "5", "7", "Tous les 8 concepts des steps precedents"],
        correct: 3,
        explanation: "Step 10 combine : Agent + tools (1-2), config/artifacts (3), ToolContext + state (4), sub_agents (5), SequentialAgent (6), ParallelAgent (7), LoopAgent (8), Callbacks (9)."
      }
    ]
  },
  step_11: {
    title: "Step 11 - Concepts avances",
    questions: [
      {
        question: "Quand utiliser BaseAgent plutot que les workflow agents (Sequential, Parallel, Loop) ?",
        options: [
          "Quand on veut un agent plus rapide",
          "Quand on a besoin de logique conditionnelle, routing dynamique, ou patterns d'orchestration non-standard",
          "Quand on n'a pas besoin de tools",
          "Quand on utilise un modele autre que Gemini"
        ],
        correct: 1,
        explanation: "BaseAgent permet d'implementer n'importe quelle logique (if/else, API calls, routing dynamique) en surchargeant _run_async_impl. Les workflow agents couvrent les patterns standards."
      },
      {
        question: "Que retourne un LongRunningFunctionTool quand il est en attente ?",
        options: [
          "Il bloque indefiniment",
          "Il retourne {\"status\": \"pending\"} et l'agent pause en attendant la reponse",
          "Il lance un thread en arriere-plan",
          "Il timeout apres 30 secondes"
        ],
        correct: 1,
        explanation: "Un LongRunningFunctionTool retourne 'pending' et pause l'agent. Le client peut ensuite envoyer la reponse d'approbation pour reprendre l'execution."
      },
      {
        question: "Quelle est la difference entre Plugins de securite et Callbacks ?",
        options: [
          "Les plugins sont plus lents",
          "Les plugins sont transversaux (protegent tout le systeme), les callbacks sont par-agent",
          "Les callbacks sont plus securises",
          "Il n'y a pas de difference"
        ],
        correct: 1,
        explanation: "Un plugin (ex: Gemini-as-Judge, PII Redaction) s'applique a tous les agents du systeme. Un callback est attache a un agent specifique."
      },
      {
        question: "Comment tester systematiquement un agent avec des cas de test ?",
        options: [
          "Manuellement dans adk web",
          "adk eval my_agent eval_set.evalset.json avec un fichier JSON de cas de test",
          "pytest avec des mocks",
          "adk test --auto"
        ],
        correct: 1,
        explanation: "adk eval execute l'agent contre un fichier JSON contenant des paires query/expected_response pour valider le comportement systematiquement."
      }
    ]
  }
};
