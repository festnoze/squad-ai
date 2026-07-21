// ============================================================
// EXPÉRIENCES PROFESSIONNELLES — format groupé par entreprise
//
// Structure :
//   company : string — nom de l'entreprise (affiché en header de groupe)
//   positions : array — liste des postes au sein de cette entreprise
//     └─ period      : string — période (affiché en italique)
//        title       : string — intitulé du poste (accepte HTML)
//        description : string — texte libre, accepte du HTML
//        techs       : string | null — stack technique
//
// Quand la mission est chez un client tiers, inclure le nom du client
// directement dans le titre (ex: "chez ASF — ...").
// ============================================================
const EXPERIENCE = [
  {
    company: "STUDI",
    positions: [
      {
        period: "Mars 2024 – Mars 2026",
        title: "Lead AI Engineer — API, Chatbots &amp; Callbot IA avec RAG &amp; agents",
        description:
          "• Conception et développement de bout en bout des chatbots et du callbot du leader français du e-learning — systèmes en production au service des apprenants (API Python, LLM, RAG, agents, évals).<br>"
        + "• Préparation et requêtage RAG (pipe Inference & Ingestion, chunking, embedding, hybrid search, reranking, HydE).<br>"
        + "• Conception d'agents et de workflows (patterns, graphs, tools, MCP, prompts — LangGraph &amp; ADK).<br>"
        + "• Évaluations LLM-as-a-judge de chaînes LLM, de RAG, d'agents (Langfuse, RAGAs).",
        techs: "API, RAG, Agents, Python, Cursor, Claude code, Langchain, LangGraph, Langfuse, RAGAs, SQLAlchemy, Alembic, PostgreSQL, MCP, Google ADK, GitLab, Azure DevOps, SQL, QDrant, Pinecone, Cache Redis."
      },
      {
        period: "Juil. 2020 – Fev. 2024",
        title: "Lead developpeur fullstack — Solution de e-learning (Front et Backend)",
        description:
          "• Direction technique de la plateforme e-learning : architecture DDD, Clean &amp; Hexagonale, CQRS, Event sourcing.<br>"
        + "• Développement Back (.NET Core) et Front (Angular).<br>"
        + "• Encadrement d'équipes offshore (Russie, Hongrie) ; AMOA et découpage du backlog Agile sur Jira (epics, US, tâches).<br>"
        + "• Tests unitaires (Xunit) et fonctionnels (Gherkin, Specflow) ; déploiement Git, Octopus, Azure.",
        techs: "C#, .NET Core, EF, DDD, BDD, CQRS, Mediatr, Polly, Xunit, SQL Server, Angular, Typescript, HTML, CSS, Git, Jira, Octopus, Scrum, Gherkin, Specflow, Moq."
      }
    ]
  },
  {
    company: "KALISYS",
    positions: [
      {
        period: "Juil. 2004 – Juil. 2020",
        title: "Gérance SARL, management et relation client",
        description:
          "• Création et gérance de la société pendant 16 ans : commercial, devis, suivi de projets, facturation.<br>"
        + "• Recrutement et encadrement ; relation client, MOE, formation et support.",
        techs: null
      },
      {
        period: "Jan. 2019 – Juil. 2020",
        title: "Développement applicatif gestion de portefeuilles et de stratégies de trading",
        description:
          "• Conception (UML) et développement d'une solution de gestion et d'optimisation de portefeuilles et de stratégies de trading.<br>"
        + "• POCs, développement, tests et déploiement.",
        techs: "VS 2019, C#, SQL Server, UML, Angular, Git."
      },
      {
        period: "Mai 2014 – Nov. 2018",
        title: "Développement applicatif création de stratégies de trading automatisées",
        description:
          "• Conception et réalisation d'un framework de modélisation du langage naturel et d'un service de traduction de stratégies de trading vers MQL4/5 (robots de trading automatisés).<br>"
        + "• Machine learning &amp; reconnaissance de patterns (TensorFlow).",
        techs: "VS 2015, C#, MQL 4&5, TensorFlow, ML & patterns recognition."
      }
    ]
  },
  {
    company: "Schneider Electric",
    positions: [
      {
        period: "Jan. 2011 – Juin 2013",
        title: "Lead tech & Scrum master — application de modélisation de sous-stations électriques",
        description:
          "• Développeur, puis tech lead et Scrum Master de l'équipe locale, en contexte agile et intégration continue.<br>"
        + "• Pilotage de l'équipe offshore (Inde) et mentorat des membres les moins expérimentés de l'équipe.<br>"
        + "• Développement du stockage, de services et d'IHMs ; optimisation globale via le pattern repository.",
        techs: "SCRUM, C#, WPF, EF, Redmine, Tortoise SVN, BDD, Nunit, Moq, SQL Server."
      }
    ]
  },
  {
    company: "KALISYS",
    positions: [
      {
        period: "Juil. 2004 – Déc. 2010",
        title: "Multiples projets clients &amp; solutions propriétaires — conception &amp; développement .NET",
        description:
          "• Missions en régie : ASF (cache distribué Velocity/AppFabric), BALEA (pesage industriel), SYNOX (extranet M2M), VAL Solutions (médecine préventive).<br>"
        + "• Solutions propriétaires : PGIs de gestion de séjours et d'événements, espace client web riche (GED), réservation de séjours en ligne.",
        techs: "C#, ASP.NET, .NET 1.1–3.5, WinForm, WCF, WPF, SilverLight, Entity Framework, SSIS, SQL Server, Nunit, UML."
      }
    ]
  },
  {
    company: "AXILOG (France Télécom)",
    positions: [
      {
        period: "Mai 2001 – Août 2002",
        title: "Développement PGI de gestion de cabinet médical (C++ Builder, Delphi, Interbase)"
        // Entrée compressée en une ligne (audit R4) — pas de description ni stack détaillée.
      }
    ]
  }
];
