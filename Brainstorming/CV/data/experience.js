// ============================================================
// EXPÉRIENCES PROFESSIONNELLES — format groupé par entreprise
//
// Structure :
//   company : string — nom de l'entreprise (affiché en header de groupe)
//   positions : array — liste des postes au sein de cette entreprise
//     └─ period      : string — période (affiché en italique)
//        title       : string — intitulé du poste (accepte HTML)
//        description : string | null — texte libre, accepte du HTML
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
          "• Développement complet chatbots et callbot (API Python, LLM, RAG, agents, évals).<br>"
        + "• Préparation et requêtage RAG (pipe Inference & Ingestion, chunking, embedding, hybrid search, reranking, HydE).<br>"
        + "• Conception d'agents et de workflows (patterns, graphs, tools, MCP, prompts — LangGraph &amp; ADK).<br>"
        + "• Évaluations LLM-as-a-judge de chaînes LLM, de RAG, d'agents (Langfuse, RAGAs).",
        techs: "API, RAG, Agents, Python, Cursor, Claude code, Langchain, LangGraph, Langfuse, RAGAs, SQLAlchemy, Alembic, PostgreSQL, MCP, Google ADK, GitLab, Azure DevOps, SQL, QDrant, Pinecone, Cache Redis."
      },
      {
        period: "Juil. 2020 – Fev. 2024",
        title: "Lead developpeur fullstack — Solution de e-learning (Front et Backend)",
        description: null,
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
        description: null,
        techs: null
      },
      {
        period: "Jan. 2019 – Juil. 2020",
        title: "Développement applicatif gestion de portefeuilles et de stratégies de trading",
        description: null,
        techs: "VS 2019, C#, SQL Server, UML, Angular, Git."
      },
      {
        period: "Mai 2014 – Nov. 2018",
        title: "Développement applicatif création de stratégies de trading automatisées",
        description: "Conception et développement solution de création des stratégies en MQL5. Analyse du langage naturel pour définition de stratégies",
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
        description: null,
        techs: "SCRUM, C#, WPF, EF, Redmine, Tortoise SVN, BDD, Nunit, Moq, SQL Server."
      }
    ]
  },
  {
    company: "KALISYS",
    positions: [
      {
        period: "Mars 2008 – Déc. 2010",
        title: "Missions en régie — conception &amp; développement .NET multi-clients",
        description:
          "• ASF : couche de cache distribuée (Velocity/AppFabric, SOA, WPF).<br>"
        + "• BALEA : POCs et solution de pesage industriel (WCF, WPF, SilverLight, SSIS).<br>"
        + "• SYNOX : extranet de gestion de boitiers M2M.<br>"
        + "• VAL Solutions : application web de médecine préventive.<br>"
        + "• Projets internes : site web riche (espace client, GED), réservation de séjours en ligne.",
        techs: "C#, ASP.NET, .NET 2.0–3.5, WCF, WPF, SilverLight, Entity Framework, SSIS, SQL Server, Nunit, UML."
      },
      {
        period: "Juil. 2004 – Jan. 2009",
        title: "Conception, réalisation et maintenance de PGIs de gestion de séjours et d'événements",
        description: null,
        techs: "WinForm (C#), Framework .NET 2.0, Visual Studio 2005, n-tiers. Relation client, MOE, formation et support."
      }
    ]
  },
  {
    company: "AXILOG (France Télécom)",
    positions: [
      {
        period: "Mai 2001 – Août 2002",
        title: "Développement PGI de gestion de cabinet médical",
        description: null,
        techs: "C++ Builder, Delphi, Interbase."
      }
    ]
  }
];
