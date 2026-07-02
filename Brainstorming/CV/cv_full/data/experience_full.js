// ============================================================
// EXPÉRIENCES DÉTAILLÉES — version exhaustive (cv_full)
// Fusion : CV 2026 (STUDI IA) + CV détaillé 11/2022 (historique)
//
// Structure :
//   company     : string — entreprise / client
//   title       : string — intitulé de la mission (accepte HTML)
//   period      : string — période
//   synthese    : string — résumé de la mission (accepte HTML)
//   role        : string — rôle(s) tenu(s)
//   realisations: array  — liste de réalisations (accepte HTML)
//   env         : string — environnement / stack technique
// ============================================================
const EXPERIENCE_FULL = [
  {
    company: "STUDI",
    title: "Lead AI Engineer — API, Chatbots &amp; Callbot IA avec RAG &amp; agents",
    period: "Mars 2024 – Mars 2026",
    synthese:
      "Conception et développement de bout en bout des chatbots et du callbot IA " +
      "du leader français du e-learning (API Python, LLM, RAG, agents, évaluations).",
    role: "Lead AI Engineer",
    realisations: [
      "Développement complet chatbots et callbot (API Python, LLM, RAG, agents, évals)",
      "Préparation et requêtage RAG : pipelines d'ingestion &amp; d'inférence, chunking, embedding, hybrid search, reranking, HydE",
      "Conception d'agents et de workflows : patterns, graphs, tools, MCP, prompts (LangGraph &amp; Google ADK)",
      "Évaluations LLM-as-a-judge de chaînes LLM, de RAG et d'agents (Langfuse, RAGAs)",
      "Développement assisté par IA (Claude Code, Cursor)"
    ],
    env: "Python, FastAPI, Langchain, LangGraph, Google ADK, Langfuse, RAGAs, MCP, QDrant, Pinecone, Redis, SQLAlchemy, Alembic, PostgreSQL, SQL, GitLab, Azure DevOps, Cursor, Claude Code"
  },
  {
    company: "STUDI",
    title: "Lead développeur fullstack — Solution de e-learning (Front &amp; Backend)",
    period: "Juil. 2020 – Fév. 2024",
    synthese:
      "Architecture et développement du site web de e-learning leader en France.",
    role: "Architecte, développeur (lead tech)",
    realisations: [
      "Architecture : DDD, Clean &amp; Hexagonal Architecture, SOLID, n-tiers, CQRS, Event sourcing",
      "Développement Back (.NET Core) et Front (Angular)",
      "Encadrement de projet offshore (Russie, Hongrie)",
      "Spécification : AMOA, découpage backlog Agile sur Jira (epics, US, tâches)",
      "Tests : unitaires (Xunit) et fonctionnels (Gherkin, Specflow)",
      "Déploiement : Git, Octopus, Azure"
    ],
    env: "Visual Studio 2019/2022, C#, .NET Core, EF Core, Mediatr, Polly, SQL Server, Angular, Typescript, HTML, CSS, Scrum, Git, Jira, Octopus, Moq"
  },
  {
    company: "KALISYS",
    title: "Gérance SARL, management et relation client",
    period: "Juil. 2004 – Juil. 2020",
    synthese:
      "Création et gérance de la société KALISYS : développement de solutions propriétaires, " +
      "missions en régie chez des clients, management et relation client.",
    role: "Gérant, chef de projet, concepteur/développeur",
    realisations: [
      "Gestion de la société : commercial, devis, suivi de projets, facturation",
      "Recrutement et encadrement",
      "Relation client, MOE, formation et support"
    ],
    env: null
  },
  {
    company: "KALISYS",
    title: "Outil de gestion de portefeuilles et d'optimisation de stratégies de trading",
    period: "Jan. 2019 – Juil. 2020",
    synthese:
      "Conception et développement d'une solution de gestion et d'optimisation " +
      "de portefeuilles et de stratégies de trading.",
    role: "Concepteur, développeur",
    realisations: [
      "Conception (UML)",
      "POCs",
      "Développement",
      "Tests",
      "Déploiement"
    ],
    env: "Visual Studio 2019, C#, SQL Server, UML, Angular, Git"
  },
  {
    company: "KALISYS",
    title: "Solution d'automatisation de stratégies de trading (NLP → MQL)",
    period: "Mai 2014 – Nov. 2018",
    synthese:
      "Réalisation d'un framework ouvert de modélisation du langage naturel (français, anglais, espagnol) " +
      "et d'un service de traduction de stratégies de trading du langage naturel vers MQL4/5 " +
      "(création de robots de trading automatisés).",
    role: "Concepteur, développeur, MOE, relation partenaire",
    realisations: [
      "Veille technologique autour de la reconnaissance du langage naturel",
      "Conception et réalisation d'un langage et d'un framework de modélisation et de conceptualisation du langage naturel",
      "Conception, réalisation, tests et MOE du service de création de robots de trading automatique depuis le langage naturel",
      "Machine learning &amp; reconnaissance de patterns (TensorFlow)",
      "Gestion de la relation product owner"
    ],
    env: "Visual Studio 2015, C#, MQL 4 &amp; 5, TensorFlow, ML &amp; patterns recognition"
  },
  {
    company: "Schneider Electric (Lattes)",
    title: "Logiciel de modélisation de sous-stations électriques",
    period: "Jan. 2011 – Juin 2013",
    synthese:
      "Dans un contexte agile en intégration continue, avec une équipe locale et offshore : " +
      "développeur, puis tech lead de l'équipe locale, scrum master, et enfin chef de projet " +
      "côté équipe indienne.",
    role: "Développeur (6 mois), Tech lead (1 an), puis Scrum Master (1 an)",
    realisations: [
      "Développement du stockage, de services et d'IHMs",
      "Optimisation globale de l'applicatif via le pattern repository",
      "Mentorat des membres les moins expérimentés de l'équipe",
      "Communication avec les développeurs, testeurs, partenaires et product owner",
      "Scrum Master de l'équipe locale",
      "Pilotage de l'équipe offshore en Inde"
    ],
    env: "SCRUM, C#, WPF, EF, SQL Server, Redmine, Tortoise SVN, BDD, Nunit, Moq"
  },
  {
    company: "KALISYS",
    title: "Espace client web riche (règlements &amp; GED)",
    period: "Juil. – Déc. 2010",
    synthese:
      "Conception et développement d'un espace client web en ASP.NET avec accès sécurisé " +
      "au dossier et aux documents personnels.",
    role: "Concepteur, développeur, MOE",
    realisations: [
      "Conception UML",
      "Développement en architecture n-tiers",
      "Réalisation des couches DAL, BLL, Façade, Contrat, IHM",
      "Analyse et tests en coordination avec la MOA"
    ],
    env: "Framework .NET 3.5, WebForm (ASP.NET), Visual Studio 2008, C#, MSDE"
  },
  {
    company: "ASF (Autoroutes du Sud de la France)",
    title: "Couche de cache distribuée",
    period: "Avril – Juin 2010",
    synthese:
      "Développement et intégration d'une couche business de cache distribuée " +
      "avec Velocity (AppFabric caching).",
    role: "Développeur",
    realisations: [
      "Développement de POCs",
      "Développement de la couche de cache distribuée",
      "Intégration applicative"
    ],
    env: "Velocity/AppFabric, UML, SOA, WPF, Nunit, SQL Server, Visual Studio 2008"
  },
  {
    company: "BALEA",
    title: "POCs pour une solution de pesage industriel embarquée",
    period: "Sept. 2009 – Jan. 2010",
    synthese:
      "Conception et réalisation de POCs visant à tester la faisabilité technique de différents " +
      "aspects au sein d'une solution de pesage industriel embarquée.",
    role: "Développeur",
    realisations: [
      "Conception des POCs",
      "Réalisation des POCs",
      "Présentation des résultats de faisabilité technique",
      "Intégration de certains aspects à la solution existante"
    ],
    env: "SCRUM, C#, Compact Framework .NET 3.5, WCF, WPF, SSIS, EntLibs, SilverLight, Entity Framework, Linq, Visual Studio 2010"
  },
  {
    company: "Groupe SYNOX",
    title: "Extranet de gestion de boîtiers communicants M2M",
    period: "Juin – Août 2009",
    synthese:
      "Conception et développement d'interfaces web ASP.NET pour la gestion d'appairage, " +
      "d'activation et de suivi de consommation de boîtiers communicants GSM. Extranet multi-acteurs " +
      "(opérateurs, distributeurs télécom, sites, fournisseurs de boîtiers, clients).",
    role: "Concepteur/Développeur",
    realisations: [
      "Conception Merise",
      "Développement en architecture 3-tiers",
      "Utilisation de l'ORM Entity Framework et Linq pour la DAL"
    ],
    env: "Framework .NET 3.5, Entity Framework, Linq, ASP.NET, Visual Studio 2008, C#, Rational XDE .NET, SQL Server"
  },
  {
    company: "KALISYS",
    title: "Solution complète d'e-commerce — réservation de séjours en ligne",
    period: "Sept. 2008 – Mai 2009",
    synthese:
      "Conception et développement d'interfaces web ASP.NET pour la réservation de séjours " +
      "avec paiement en ligne et gestion du suivi.",
    role: "Concepteur/Développeur, MOE",
    realisations: [
      "Conception UML",
      "Développement en architecture n-tiers",
      "Réalisation des couches DAL, BLL, Façade, Contrat, IHM",
      "Analyse et tests en coordination avec la MOA"
    ],
    env: "Framework .NET 3.5, WebForm (ASP.NET), Visual Studio 2008, C#, Rational XDE .NET, SQL Server"
  },
  {
    company: "VAL Solutions – BL Informatique",
    title: "Application web de médecine préventive",
    period: "Mars – Juil. 2008",
    synthese:
      "Développements pour une application web distribuée de gestion en médecine préventive " +
      "pour un client SSII (architecture n-tiers, distribuée, remoting).",
    role: "Consultant technique, Concepteur/Développeur",
    realisations: [
      "Conseil sur les choix technologiques .NET",
      "Adaptation de diagrammes de classes UML",
      "Création de scripts Oracle et SQL Server",
      "Réalisation des couches DAL, BLL, Façade",
      "Tests et coordination avec le pôle IHM"
    ],
    env: "Framework .NET 2.0, WebForm (ASP.NET), Visual Studio 2005, C#, Rational XDE .NET, SQL Server, Oracle"
  },
  {
    company: "KALISYS",
    title: "PGIs de gestion de séjours et de réservations événementielles",
    period: "Juil. 2004 – 2009",
    synthese:
      "Conception et réalisation de plusieurs applications complètes de gestion intégrée pour les " +
      "organisateurs de séjours et d'événements (CVL, CLSH, événementiel) en architecture 3-tiers.",
    role: "Chef de projet, Concepteur/Développeur, MOE",
    realisations: [
      "Rédaction de devis, initialisation et suivi de projet avec le client",
      "Réalisation du cahier des charges",
      "Analyses fonctionnelles détaillées, modèles conceptuels de données, définition de l'architecture technique",
      "Développement, intégration et tests unitaires",
      "Maintenance applicative et mise à jour de la documentation"
    ],
    env: "Framework .NET 1.1 et 2.0, WinForm, Visual Studio 2003-2005, C#, ASP.NET, MSDE, Access, Win Design"
  },
  {
    company: "AXILOG (France Télécom)",
    title: "PGI de gestion de cabinets médicaux",
    period: "Mai 2001 – Août 2002",
    synthese:
      "Conception et réalisation de modules de gestion de cabinet médical.",
    role: "Concepteur/Développeur",
    realisations: [
      "Analyses fonctionnelles détaillées et modèles conceptuels de données",
      "Réalisation de modules métier",
      "Intégration et tests unitaires",
      "Mise à jour de la documentation"
    ],
    env: "C++ Builder (Borland), Delphi, Interbase, Power AMC"
  },
  {
    company: "Indépendant",
    title: "Application de télétransmission pour laboratoires médicaux",
    period: "Juil. 2000 – Mai 2001",
    synthese:
      "Conception et réalisation d'un logiciel de capture et d'analyse médicale " +
      "et de messagerie sécurisée pour laboratoires d'analyse.",
    role: "Concepteur/Développeur",
    realisations: [
      "Analyses fonctionnelles et modèles conceptuels de données",
      "Réalisation du logiciel",
      "Mise à jour de la documentation"
    ],
    env: "Visual C++, Access"
  }
];
