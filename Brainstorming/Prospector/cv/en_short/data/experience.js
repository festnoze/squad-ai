// ============================================================
// PROFESSIONAL EXPERIENCE — grouped by company
//
// Structure:
//   company : string — company name (displayed as group header)
//   positions : array — list of roles within that company
//     └─ period      : string — dates (displayed in italics)
//        title       : string — role title (accepts HTML)
//        description : string — free text, accepts HTML
//        techs       : string | null — tech stack
//
// When the assignment was for a third-party client, include the
// client name directly in the title (e.g. "for ASF — ...").
// ============================================================
const EXPERIENCE = [
  {
    company: "STUDI",
    positions: [
      {
        period: "Mar. 2024 – Mar. 2026",
        title: "Lead AI Engineer — APIs, AI Chatbots &amp; Callbot with RAG &amp; agents",
        description:
          "• Designed and built end-to-end the chatbots and callbot of France's leading e-learning provider — production systems serving learners daily (Python APIs, LLMs, RAG, agents, evals).<br>"
        + "• Built full RAG ingestion &amp; inference pipelines: chunking, embeddings, hybrid search, reranking, HyDE.<br>"
        + "• Designed agents and workflows: patterns, graphs, tools, MCP, prompts (LangGraph &amp; Google ADK).<br>"
        + "• Implemented LLM-as-a-judge evaluation of LLM chains, RAG and agents (Langfuse, RAGAs).",
        techs: "APIs, RAG, agents, Python, Cursor, Claude Code, LangChain, LangGraph, Langfuse, RAGAs, SQLAlchemy, Alembic, PostgreSQL, MCP, Google ADK, GitLab, Azure DevOps, SQL, Qdrant, Pinecone, Redis cache."
      },
      {
        period: "Jul. 2020 – Feb. 2024",
        title: "Lead Fullstack Developer — E-learning platform (front &amp; back end)",
        description:
          "• Technical direction of the e-learning platform: DDD, Clean &amp; Hexagonal architecture, CQRS, event sourcing.<br>"
        + "• Back-end (.NET Core) and front-end (Angular) development.<br>"
        + "• Coordinated offshore teams (Russia, Hungary); business analysis and Agile backlog management in Jira (epics, user stories, tasks).<br>"
        + "• Unit testing (xUnit) and functional testing (Gherkin, SpecFlow); deployment with Git, Octopus and Azure.",
        techs: "C#, .NET Core, EF, DDD, BDD, CQRS, MediatR, Polly, xUnit, SQL Server, Angular, TypeScript, HTML, CSS, Git, Jira, Octopus, Scrum, Gherkin, SpecFlow, Moq."
      }
    ]
  },
  {
    company: "KALISYS",
    positions: [
      {
        period: "Jul. 2004 – Jul. 2020",
        title: "Founder &amp; Managing Director — company management and client relations",
        description:
          "• Founded and ran the software company for 16 years: sales, quoting, project tracking, invoicing.<br>"
        + "• Hiring and team management; client relations, project delivery, training and support.",
        techs: null
      },
      {
        period: "Jan. 2019 – Jul. 2020",
        title: "Portfolio management and trading-strategy optimization application",
        description:
          "• Designed (UML) and developed a solution for managing and optimizing portfolios and trading strategies.<br>"
        + "• POCs, development, testing and deployment.",
        techs: "VS 2019, C#, SQL Server, UML, Angular, Git."
      },
      {
        period: "May 2014 – Nov. 2018",
        title: "Automated trading-strategy creation platform (NLP → MQL)",
        description:
          "• Designed and built a natural-language modeling framework and a service translating trading strategies from natural language into MQL4/5 (automated trading robots).<br>"
        + "• Machine learning &amp; pattern recognition (TensorFlow).",
        techs: "VS 2015, C#, MQL 4&5, TensorFlow, ML & pattern recognition."
      }
    ]
  },
  {
    company: "Schneider Electric",
    positions: [
      {
        period: "Jan. 2011 – Jun. 2013",
        title: "Tech Lead &amp; Scrum Master — electrical substation modeling application",
        description:
          "• Developer, then tech lead and Scrum Master of the local team, in an agile, continuous-integration environment.<br>"
        + "• Steered the offshore team in India and mentored the team's junior members.<br>"
        + "• Built storage, services and UIs; application-wide optimization via the repository pattern.",
        techs: "Scrum, C#, WPF, EF, Redmine, Tortoise SVN, BDD, NUnit, Moq, SQL Server."
      }
    ]
  },
  {
    company: "KALISYS",
    positions: [
      {
        period: "Jul. 2004 – Dec. 2010",
        title: "Multiple client projects &amp; in-house products — .NET design &amp; development",
        description:
          "• Consulting engagements: ASF (distributed cache, Velocity/AppFabric), BALEA (industrial weighing), SYNOX (M2M extranet), VAL Solutions (preventive-medicine web app).<br>"
        + "• In-house products: ERP systems for holiday and event management, rich web client portal (document management), online booking platform.",
        techs: "C#, ASP.NET, .NET 1.1–3.5, WinForms, WCF, WPF, Silverlight, Entity Framework, SSIS, SQL Server, NUnit, UML."
      }
    ]
  },
  {
    company: "AXILOG (France Télécom)",
    positions: [
      {
        period: "May 2001 – Aug. 2002",
        title: "ERP development for medical practices (C++ Builder, Delphi, Interbase)"
        // Compressed one-line entry (audit R4) — no description or detailed stack.
      }
    ]
  }
];
