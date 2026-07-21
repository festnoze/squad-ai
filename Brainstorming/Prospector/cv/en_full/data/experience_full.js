// ============================================================
// DETAILED EXPERIENCE — exhaustive version (full resume)
// Merge: 2026 resume (STUDI AI) + detailed 11/2022 resume (history)
//
// Structure:
//   company     : string — company / client
//   title       : string — assignment title (accepts HTML)
//   period      : string — dates
//   synthese    : string — assignment summary (accepts HTML)
//   role        : string — role(s) held
//   realisations: array  — list of achievements (accepts HTML)
//   env         : string — environment / tech stack
// ============================================================
const EXPERIENCE_FULL = [
  {
    company: "STUDI",
    title: "Lead AI Engineer — APIs, AI Chatbots &amp; Callbot with RAG &amp; agents",
    period: "Mar. 2024 – Mar. 2026",
    synthese:
      "End-to-end design and development of the AI chatbots and callbot of France's " +
      "leading e-learning provider — production systems serving learners daily " +
      "(Python APIs, LLMs, RAG, agents, evaluation).",
    role: "Lead AI Engineer",
    realisations: [
      "Built the chatbots and callbot end to end (Python APIs, LLMs, RAG, agents, evals)",
      "RAG preparation and querying: ingestion &amp; inference pipelines, chunking, embeddings, hybrid search, reranking, HyDE",
      "Designed agents and workflows: patterns, graphs, tools, MCP, prompts (LangGraph &amp; Google ADK)",
      "LLM-as-a-judge evaluation of LLM chains, RAG and agents (Langfuse, RAGAs)",
      "AI-assisted development (Claude Code, Cursor)"
    ],
    env: "Python, FastAPI, LangChain, LangGraph, Google ADK, Langfuse, RAGAs, MCP, Qdrant, Pinecone, Redis, SQLAlchemy, Alembic, PostgreSQL, SQL, GitLab, Azure DevOps, Cursor, Claude Code"
  },
  {
    company: "STUDI",
    title: "Lead Fullstack Developer — E-learning platform (front &amp; back end)",
    period: "Jul. 2020 – Feb. 2024",
    synthese:
      "Architecture and development of the website of France's leading e-learning platform.",
    role: "Architect, developer (tech lead)",
    realisations: [
      "Architecture: DDD, Clean &amp; Hexagonal Architecture, SOLID, n-tier, CQRS, event sourcing",
      "Back-end (.NET Core) and front-end (Angular) development",
      "Coordination of offshore teams (Russia, Hungary)",
      "Specification: business analysis, Agile backlog breakdown in Jira (epics, user stories, tasks)",
      "Testing: unit (xUnit) and functional (Gherkin, SpecFlow)",
      "Deployment: Git, Octopus, Azure"
    ],
    env: "Visual Studio 2019/2022, C#, .NET Core, EF Core, MediatR, Polly, SQL Server, Angular, TypeScript, HTML, CSS, Scrum, Git, Jira, Octopus, Moq"
  },
  {
    company: "KALISYS",
    title: "Founder &amp; Managing Director — company management and client relations",
    period: "Jul. 2004 – Jul. 2020",
    synthese:
      "Founded and ran the KALISYS software company: proprietary product development, " +
      "consulting engagements at client sites, management and client relations.",
    role: "Managing director, project manager, designer/developer",
    realisations: [
      "Company management: sales, quoting, project tracking, invoicing",
      "Hiring and team management",
      "Client relations, project delivery, training and support"
    ],
    env: null
  },
  {
    company: "KALISYS",
    title: "Portfolio management and trading-strategy optimization tool",
    period: "Jan. 2019 – Jul. 2020",
    synthese:
      "Design and development of a solution for managing and optimizing " +
      "portfolios and trading strategies.",
    role: "Designer, developer",
    realisations: [
      "Design (UML)",
      "POCs",
      "Development",
      "Testing",
      "Deployment"
    ],
    env: "Visual Studio 2019, C#, SQL Server, UML, Angular, Git"
  },
  {
    company: "KALISYS",
    title: "Trading-strategy automation solution (NLP → MQL)",
    period: "May 2014 – Nov. 2018",
    synthese:
      "Built an open framework for modeling natural language (French, English, Spanish) " +
      "and a service translating trading strategies from natural language into MQL4/5 " +
      "(creation of automated trading robots).",
    role: "Designer, developer, delivery lead, partner relations",
    realisations: [
      "Technology watch on natural-language understanding",
      "Designed and built a language and framework for modeling and conceptualizing natural language",
      "Designed, built, tested and delivered the service creating automated trading robots from natural language",
      "Machine learning &amp; pattern recognition (TensorFlow)",
      "Managed the product-owner relationship"
    ],
    env: "Visual Studio 2015, C#, MQL 4 &amp; 5, TensorFlow, ML &amp; pattern recognition"
  },
  {
    company: "Schneider Electric (Lattes)",
    title: "Electrical substation modeling software",
    period: "Jan. 2011 – Jun. 2013",
    synthese:
      "In an agile, continuous-integration context with local and offshore teams: " +
      "developer, then tech lead of the local team, Scrum Master, and finally project " +
      "manager for the Indian team.",
    role: "Developer (6 months), Tech lead (1 year), then Scrum Master (1 year)",
    realisations: [
      "Built storage, services and UIs",
      "Application-wide optimization via the repository pattern",
      "Mentored the team's less experienced members",
      "Communication with developers, testers, partners and the product owner",
      "Scrum Master of the local team",
      "Steered the offshore team in India"
    ],
    env: "Scrum, C#, WPF, EF, SQL Server, Redmine, Tortoise SVN, BDD, NUnit, Moq"
  },
  {
    company: "KALISYS",
    title: "Rich web client portal (payments &amp; document management)",
    period: "Jul. – Dec. 2010",
    synthese:
      "Design and development of an ASP.NET web client portal with secure access " +
      "to personal records and documents.",
    role: "Designer, developer, delivery lead",
    realisations: [
      "UML design",
      "Development in an n-tier architecture",
      "Built the DAL, BLL, Facade, Contract and UI layers",
      "Analysis and testing in coordination with the business stakeholders"
    ],
    env: ".NET Framework 3.5, WebForms (ASP.NET), Visual Studio 2008, C#, MSDE"
  },
  {
    company: "ASF (Autoroutes du Sud de la France)",
    title: "Distributed cache layer",
    period: "Apr. – Jun. 2010",
    synthese:
      "Development and integration of a distributed-cache business layer " +
      "with Velocity (AppFabric caching).",
    role: "Developer",
    realisations: [
      "Built POCs",
      "Developed the distributed cache layer",
      "Application integration"
    ],
    env: "Velocity/AppFabric, UML, SOA, WPF, NUnit, SQL Server, Visual Studio 2008"
  },
  {
    company: "BALEA",
    title: "POCs for an embedded industrial weighing solution",
    period: "Sep. 2009 – Jan. 2010",
    synthese:
      "Design and delivery of POCs to test the technical feasibility of various " +
      "aspects of an embedded industrial weighing solution.",
    role: "Developer",
    realisations: [
      "Designed the POCs",
      "Built the POCs",
      "Presented the technical-feasibility results",
      "Integrated selected aspects into the existing solution"
    ],
    env: "Scrum, C#, Compact Framework .NET 3.5, WCF, WPF, SSIS, EntLibs, Silverlight, Entity Framework, LINQ, Visual Studio 2010"
  },
  {
    company: "Groupe SYNOX",
    title: "Extranet for managing M2M communicating devices",
    period: "Jun. – Aug. 2009",
    synthese:
      "Design and development of ASP.NET web interfaces for pairing, activating and " +
      "tracking the data consumption of GSM communicating devices. Multi-stakeholder extranet " +
      "(carriers, telecom distributors, sites, device suppliers, customers).",
    role: "Designer/Developer",
    realisations: [
      "Merise design",
      "Development in a 3-tier architecture",
      "Used the Entity Framework ORM and LINQ for the DAL"
    ],
    env: ".NET Framework 3.5, Entity Framework, LINQ, ASP.NET, Visual Studio 2008, C#, Rational XDE .NET, SQL Server"
  },
  {
    company: "KALISYS",
    title: "Complete e-commerce solution — online holiday booking",
    period: "Sep. 2008 – May 2009",
    synthese:
      "Design and development of ASP.NET web interfaces for booking holidays " +
      "with online payment and follow-up management.",
    role: "Designer/Developer, delivery lead",
    realisations: [
      "UML design",
      "Development in an n-tier architecture",
      "Built the DAL, BLL, Facade, Contract and UI layers",
      "Analysis and testing in coordination with the business stakeholders"
    ],
    env: ".NET Framework 3.5, WebForms (ASP.NET), Visual Studio 2008, C#, Rational XDE .NET, SQL Server"
  },
  {
    company: "VAL Solutions – BL Informatique",
    title: "Preventive-medicine web application",
    period: "Mar. – Jul. 2008",
    synthese:
      "Development work on a distributed web application for preventive-medicine management " +
      "for an IT-services client (n-tier, distributed architecture, remoting).",
    role: "Technical consultant, Designer/Developer",
    realisations: [
      "Advised on .NET technology choices",
      "Adapted UML class diagrams",
      "Created Oracle and SQL Server scripts",
      "Built the DAL, BLL and Facade layers",
      "Testing and coordination with the UI team"
    ],
    env: ".NET Framework 2.0, WebForms (ASP.NET), Visual Studio 2005, C#, Rational XDE .NET, SQL Server, Oracle"
  },
  {
    company: "KALISYS",
    title: "ERP systems for holiday and event booking management",
    period: "Jul. 2004 – 2009",
    synthese:
      "Design and delivery of several complete integrated-management applications for " +
      "holiday and event organizers (youth camps, leisure centers, event management) in a 3-tier architecture.",
    role: "Project manager, Designer/Developer, delivery lead",
    realisations: [
      "Wrote quotes, initiated and tracked projects with the client",
      "Wrote the functional specifications",
      "Detailed functional analyses, conceptual data models, technical architecture definition",
      "Development, integration and unit testing",
      "Application maintenance and documentation updates"
    ],
    env: ".NET Framework 1.1 and 2.0, WinForms, Visual Studio 2003-2005, C#, ASP.NET, MSDE, Access, Win Design"
  },
  {
    company: "AXILOG (France Télécom)",
    title: "ERP for medical practices",
    period: "May 2001 – Aug. 2002",
    synthese:
      "Design and delivery of management modules for medical practices.",
    role: "Designer/Developer",
    realisations: [
      "Detailed functional analyses and conceptual data models",
      "Built business modules",
      "Integration and unit testing",
      "Documentation updates"
    ],
    env: "C++ Builder (Borland), Delphi, Interbase, Power AMC"
  },
  {
    company: "Freelance",
    title: "Data-transmission application for medical laboratories",
    period: "Jul. 2000 – May 2001",
    synthese:
      "Design and delivery of medical capture-and-analysis software " +
      "with secure messaging for medical-analysis laboratories.",
    role: "Designer/Developer",
    realisations: [
      "Functional analyses and conceptual data models",
      "Built the software",
      "Documentation updates"
    ],
    env: "Visual C++, Access"
  }
];
