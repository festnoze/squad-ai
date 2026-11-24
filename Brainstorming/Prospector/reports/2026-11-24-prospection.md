# Prospection missions freelance IA - passe exploratoire du 24/11/2026

Profil : `config/profile.yaml` (Lead AI Engineer / Forward Deployed Engineer, dispo 01/2027, TJM cible 800 € exécution / 1 200 € conseil, plancher 600 €).
Périmètre demandé : US / UK / contexte anglo-saxon en full remote ; Paris en full remote ; Strasbourg (hybride accepté).
Nature : **prospection pure**. Aucune candidature, aucun mail, aucun brouillon envoyé.

Méthode :
- `scripts/fetch_boards.py` (RemoteOK, Remotive, WeWorkRemotely) : 103 offres insérées en base, quasi toutes hors sujet (voir §5).
- 3 recherches web en parallèle (UK, US/international, France) : environ 50 requêtes et 75 pages vérifiées chacune.
- Règle : rien n'est inventé. Un TJM, une date ou une URL vient de la page consultée. Sinon c'est noté "non précisé". Les offres vues seulement dans un extrait de moteur de recherche (page non rechargeable) sont marquées **[non vérifiée]**.

---

## 1. Synthèse en 30 secondes

| Zone | Ce qu'on trouve vraiment | Verdict |
|---|---|---|
| **Paris / IDF full remote** | 10 missions IA générative / agents, TJM 400-1 150 €, mais **toutes en "télétravail partiel"**. Aucune en 100 % remote confirmé. | Marché riche, remote rare. À négocier au cas par cas (dispo 01/2027 = levier). |
| **Strasbourg (hybride OK)** | **Zéro mission IA active** sur les boards publics. Une seule piste eMatiss, expirée. | Passer par la prospection directe (ESN alsaciennes, Malt avec connexion). |
| **UK** | Missions IA/LLM réelles, 350-540 £/j en full remote. Mais la plupart exigent **UK residency**, une clearance SC/DV ou de la présence à Londres. | Faible accessibilité depuis la France. |
| **US / international EN** | Les "contracts" US sont presque tous **US-only / W2**. Ce qui est ouvert à l'UE passe par des boutiques européennes (Gramian, Proxify, Llamazing, Netguru, A.Team). | **Meilleur gisement full remote** pour le profil. |

**Constat clé** : le full remote réellement ouvert à un freelance basé en France se trouve surtout chez des **intermédiaires européens anglophones** travaillant en fuseau CET. On ne le trouve ni chez les ESN parisiennes, ni chez les clients UK/US en direct.

---

## 2. Top 8 - à regarder en premier

| # | Mission | Zone / remote | TJM | Démarrage | Pourquoi |
|---|---|---|---|---|---|
| 1 | Senior Python Engineer for AI Applications (Llamazing, via freelancermap) | 100 % remote, chevauchement CET ≥ 4 h | à proposer (€/h) | Q1 2027 | Calendrier parfait, LLM + RAG citations + tests de régression |
| 2 | Senior AI Engineer Agentic AI / AWS (Gramian pour un Big4) | 100 % remote, "Europe-based, EU authorization" | non précisé | en cours, jusqu'à 07/2027 | Multi-agents en finance (AML/KYC, fraude), éligible France |
| 3 | AI Engineer IA générative & agentique (IDEMYS) | IDF, télétravail partiel | non précisé | **03/01/2027** | Stack identique au profil (MCP, Langfuse, LangGraph, multi-LLM) |
| 4 | Lead IA / Architecte IA agentique, assurance (NEOGIA) | Paris, télétravail partiel | **700-1 150 €** | ASAP, 6 mois renouvelables | Agents autonomes gestion de sinistres, TJM haut de gamme |
| 5 | AI & Data Architect Senior GenAI / Agentic (Nicholson) | Courbevoie, "télétravail possible avec déplacements ponctuels" | **850 €** | ASAP, jusqu'au 30/06/2027 | Formulation la plus proche du full remote côté Paris |
| 6 | Senior AI Engineer backend (Proxify) | Remote EMEA, CET ± 3 h | non précisé | non précisé | Agents Claude en prod, C# accepté |
| 7 | Senior Independent AI Engineer / Architect (A.Team) | Remote Americas / Europe / Israel | non précisé | réseau | Réseau sur invitation de freelances IA seniors, missions LLM/agents/évaluation |
| 8 | Senior AI Platform Engineer, Agent Framework Lead (RED Global) **[non vérifiée]** | long-term freelance, éligibilité à confirmer | non précisé | non précisé | LangGraph + évaluation LLM + gouvernance, cœur du profil |

---

## 3. Détail des missions

### 3.A International anglophone, full remote ouvert à l'UE (candidature en anglais)

#### A1. Senior Python Engineer for AI Applications
- **Client / intermédiaire** : Llamazing Digital Engineering GmbH (contact affiché : Björn Froese), via freelancermap.com
- **Remote** : "100% remote", candidatures internationales bienvenues, **au moins 4 h/jour de chevauchement avec CET**
- **Engagement** : freelance, facturation en EUR, 4-6 mois typiquement, prolongeable ; démarrage "à partir du Q1 2027 selon le projet"
- **Tarif** : non précisé, le candidat indique son taux horaire en EUR
- **Projet** : applications LLM connectées aux données et systèmes de l'entreprise : sorties typées/structurées, traçabilité des sources, protections contre l'injection de prompt, cas de test QA/régression, intégration cloud IA (GCP/Azure/AWS). Documentation versionnée.
- **Stack** : Python (5 ans et plus, dont 2 en applications LLM), LLM en prod ou en pilote, tests automatisés ; bonus : LangChain, RAG avec citations, TypeScript, allemand
- **Publiée** : modifiée le 06/11/2026
- **URL** : https://www.freelancermap.com/project/senior-ai-engineer-llm-agents-tool-calling-evals-vertex-ai-agentic-ai-remote
- **Adéquation** : la meilleure trouvée. Le démarrage colle à la dispo, la culture test/évaluation est un différenciateur direct, le fuseau CET est natif. Proposer ~100-110 €/h (≈ 800-880 €/j).

#### A2. Senior AI Engineer (Agentic AI / AWS)
- **Client / intermédiaire** : Gramian Consulting Group, pour un client Big4
- **Remote** : "REMOTE 100%, Europe-based and EU authorization required"
- **Engagement** : contract plein temps, "October 2026 - July 2027", prolongation possible (avec "retainer rate")
- **Tarif** : non précisé
- **Projet** : agents autonomes et systèmes multi-agents pour institutions financières (détection de fraude, modernisation AML/KYC, plateformes IA d'entreprise)
- **Stack** : Python, LLM, orchestration d'agents (LangChain, AutoGen, CrewAI), AWS, MLOps/AIOps
- **Publiée** : non précisé
- **URL** : https://jobs.workable.com/jobs/1ec3d1dc-8d07-4f9e-af10-b24ab3a8364d
- **Adéquation** : bon fit et éligible. Le contrat a démarré en octobre : vérifier que le poste est encore ouvert (backfill probable vu la durée). L'expérience AWS n'est pas dans le profil, c'est GCP/Azure : le dire honnêtement.

#### A3. Senior AI Engineer (Backend-Focused)
- **Client / intermédiaire** : Proxify (réseau de freelances)
- **Remote** : remote EMEA, restreint à "CET (+/- 3 hours)"
- **Engagement** : freelance/contract, durée non précisée
- **Tarif** : non précisé
- **Projet** : workflows agentiques et systèmes de code autonomes autour de Claude, intégrés en production ; conception d'outils pour LLM, multi-agents
- **Stack** : Python, C# ou JS/Node ; LangChain, bases vectorielles, observabilité en bonus ; anglais intermédiaire-avancé
- **Publiée** : "il y a 2 semaines" (≈ début novembre 2026)
- **URL** : https://www.workingnomads.com/jobs/senior-ai-engineer-backend-focused-proxify
- **Adéquation** : bon fit (C#/.NET et Python valorisés, usage intensif de Claude Code). Proxify est un réseau : on y entre par un processus de vetting.

#### A4. Senior Independent AI Engineer / Architect
- **Client / intermédiaire** : A.Team (réseau sur invitation, sièges NYC et Tel Aviv)
- **Remote** : "Remote | Americas, Europe, or Israel"
- **Engagement** : missions freelance via le réseau
- **Tarif** : non précisé
- **Projet** : petites équipes sur des systèmes IA en production : produits LLM, architectures et orchestration d'agents, infrastructure de retrieval, d'évaluation et de fiabilité, déploiements IA en entreprise. Le pitch insiste : "Not demos. Not another chatbot wrapper."
- **Publiée** : présente sur WeWorkRemotely au 24/11/2026 (stockée en base, id 97)
- **URL** : https://weworkremotely.com/remote-jobs/a-team-senior-independent-ai-engineer-architect (redirige vers a.team/ai-jobs)
- **Adéquation** : le message "production, pas des POC" recoupe mot pour mot le différenciateur du profil. C'est une candidature au réseau, pas à une mission.

#### A5. Senior AI Platform Engineer (Agent Framework Lead) **[non vérifiée]**
- **Client / intermédiaire** : RED Global (client : "major AI transformation programme")
- **Remote / éligibilité** : long-term freelance ; pays éligibles **non confirmés** (pages Arc.dev et WeAreDevelopers en 403)
- **Projet** : plateforme d'entreprise de développement d'agents : orchestration, déploiement, évaluation, observabilité, gouvernance, sur AWS Bedrock/AgentCore
- **Stack** : LangGraph et/ou Strands Agents, frameworks d'évaluation LLM, 5 ans et plus en Python/plateforme IA
- **Publiée** : "il y a 10 heures" selon l'extrait (≈ 24/11/2026)
- **URL** : https://arc.dev/remote-jobs/j/red-global-ai-engineer-pfuabkaq34
- **Adéquation** : très forte sur le papier. À ouvrir à la main pour vérifier l'éligibilité.

#### A6. Senior AI Engineer, LLMs & Knowledge Graphs **[non vérifiée]**
- **Client / intermédiaire** : Jimmy Technologies (client final : Fortune 50)
- **Remote** : "remote (99%) in Europe", chevauchement 14 h-18 h CET
- **Tarif** : **38-43 €/h** selon l'extrait (≈ 300-345 €/j), **sous le plancher**
- **Projet** : LLM et graphes de connaissances, forte composante observabilité/évaluation (Ragas, DeepEval, Langfuse)
- **URL** : https://startup.jobs/senior-ai-engineer-llms-knowledge-graphs-homepage-347-7946773
- **Adéquation** : stack quasi parfaite, mais le tarif est disqualifiant. À garder comme signal marché.

#### A7. Secure Privacy, Senior Full-Stack (.NET/C#/Angular), AI-first, RGPD
- **Client** : Secure Privacy (Danemark), via WeWorkRemotely (base, id 95)
- **Remote** : "Anywhere in the World", collaboration "primarily during European business hours"
- **Engagement / tarif** : non précisé (probablement un poste salarié, à confirmer)
- **Projet** : backend C#/.NET et frontend Angular/Redux d'une plateforme de conformité vie privée ; usage quotidien de Cursor/Claude Code exigé, avec un rôle de diffusion de ces pratiques dans l'équipe
- **URL** : https://weworkremotely.com/remote-jobs/secure-privacy-senior-full-stack-web-developer-net-c-mongodb-angular-redux-ai-first-with-gdpr-experience
- **Adéquation** : piste de repli (profil fullstack .NET plus IA dans la chaîne de dev, RGPD). Intéressant seulement si l'entreprise accepte un contrat.

#### Signaux marché (non actionnables aujourd'hui)
- **Netguru** : contrats B2B UE de 6 mois, multi-agents / LLM conversationnels, **60-65 $/h** (annonce expirée, rôles régulièrement republiés) : https://apply.workable.com/netguru/
- **Gramian, "Forward Deployed AI Engineer"** : stack idéale mais pays autorisés Turquie, Croatie, Tchéquie, Estonie, Géorgie, Pologne, Roumanie. **France exclue.**
- **Toptal** : flux régulier de missions agents/RAG ouvertes à l'Europe ; s'inscrire au vivier plutôt que viser une annonce.
- **Upwork** : des annonces "LLM Engineer - EU based only" existent, mais elles sont illisibles sans connexion.
- **Vertican** (Senior Applied AI Engineer, Document Intelligence, US/NJ, "Anywhere") et **Wemolo** (Munich, profil FDE) : probablement des CDI, hors cible.

### 3.B UK (candidature en anglais)

Note : "Outside IR35" = vraie prestation B2B (compatible avec une structure française). "Inside IR35" = passage par une umbrella company, peu adapté à un non-résident.

| # | Mission | Intermédiaire | Remote | IR35 / contraintes | TJM | Durée | Statut |
|---|---|---|---|---|---|---|---|
| U1 | AI Engineer (Contract), Marketing Demand Gen | Houseful / Alto (groupe Zoopla) | Remote, **"Must work from the UK"** | Outside IR35, **UK residency** | non précisé | 6 mois | vérifiée |
| U2 | Senior ML Engineer, Python GenAI/RAG | RecOps | "fully remote contract" | **Inside IR35** | 500 £/j | non précisé | publiée le 24/11/2026 (vue sur itjobboard.co.uk) |
| U3 | AI/LLM Engineer (Contract), RAG Implementation | Robson Bale | London "Mostly Remote" | Outside IR35 | 400-525 £/j | 6-12 mois, démarrage janvier | [non vérifiée] |
| U4 | AI Engineer (LLM), LLM on-prem | Understanding Solutions | "Fully Remote (**UK candidates only**)" | Outside IR35 | 450-500 £/j | 6 mois | [non vérifiée] |
| U5 | AI Engineer, EdTech start-up | Transparent Technology | Remote | Outside IR35 | 350-375 £/j | 3 mois rolling | [non vérifiée] |
| U6 | Senior Full Stack Developer & AI Engineer | Harnham | "Fully remote" | Outside IR35 | 440-540 £/j | 4-6 semaines | [non vérifiée] |
| U7 | 5x AI Engineers (LangGraph, LlamaIndex, OpenAI AgentSDK) | FewFar | Remote (UK) | **Clearance SC/DV/EDV** | ~500-600 £/j | 6 mois | [non vérifiée], bloquant |
| U8 | Contract Forward Deployed Engineer | YLD | UK remote (certains rôles YLD : "EU or Brazil") | B2B | non précisé | 6 mois | **absente de la page carrières YLD** : pourvue |

Détails utiles :
- **U1** (https://apply.workable.com/alto/jobs/view/9AC4AF73BC) : automatisations LLM sur HubSpot/Salesforce, RAG, AWS Bedrock, Inngest ; Claude/Cursor en outils de dev. Bon fit technique, résidence UK bloquante.
- **U2** : LLM, RAG, recherche vectorielle, workflows agentiques sur Azure, Docker/K8s. Le seul full remote UK sans clause de résidence explicite, mais Inside IR35 et tarif bas. Le même cabinet propose un "Lead ML Engineer" jusqu'à 700 £/j, avec 1 jour/semaine à Londres.
- **U5** : EdTech, secteur cohérent avec Studi, mais le tarif correspond à un profil mid-level.
- **U8** : rôle FDE agentique pile dans la cible. À surveiller sur la page carrières YLD (Greenhouse) pour une republication.

Exclues car hybrides (pour mémoire) : *AI Engineer* chez Project Blackbook (Londres, 3-4 j/sem sur site, LangGraph/CrewAI) ; *AI Evaluation Engineer* (700-750 £/j, Inside IR35, 2 j/sem sur site à Londres/Bristol/Manchester, SC préférée). Cette dernière est le meilleur match "évaluation LLM" vu, dommage.

### 3.C France, Paris / IDF (candidature en français)

**Aucune mission en 100 % télétravail confirmé.** Toutes affichent "télétravail partiel", rarement chiffré. Toutes viennent de Free-Work, la seule source publique riche avec TJM affiché.

| # | Mission | Intermédiaire (client) | Télétravail | TJM | Durée / démarrage | Publiée |
|---|---|---|---|---|---|---|
| F1 | Lead IA / Architecte IA agentique, assurance | NEOGIA | partiel | **700-1 150 €** | 6 mois renouvelables, ASAP | 06/11 |
| F2 | AI & Data Architect Senior GenAI / Agentic | Nicholson | "possible avec déplacements ponctuels" | **850 €** | 8 mois (→ 30/06/2027), ASAP | 12/11 |
| F3 | AI Engineer IA générative & agentique | IDEMYS | partiel | non précisé | 6 mois renouvelables, **03/01/2027** | 23/11 |
| F4 | Senior AI Engineer | AVELSEN (groupe du luxe) | partiel | 600-780 € | 9 mois renouvelables, ASAP | 26/10 |
| F5 | Architecte IA / GenAI Solution Architect | ISUPPLIER | non précisé | 460-950 € | 1 an renouvelable, ASAP | 27/10 |
| F6 | Consultant Lead AI, Architecte Solutions IA | ISUPPLIER | non précisé | 400-850 € | 1 an renouvelable, ASAP | 27/10 |
| F7 | Architecte IA générative & agentique, LLMOps | CAT-AMANIA (grande banque) | partiel | 520-620 € | 1 an renouvelable, ASAP | 20/10 |
| F8 | AI Engineer IA générative & LLM | Signe + (grande banque) | partiel | 400-550 € | 24 mois, ASAP | 23/11 |
| F9 | Développeur IA / GenAI, expert Mistral AI | Keypeople Consulting | partiel | 450-510 € | 3 mois renouvelables, 31/01/2027 | 17/11 |
| F10 | Ingénieur IA / LLMOps | Sapiens Group (média) | partiel | 450-500 € | 12 mois renouvelables, ASAP | 20/10 |

Détails :

**F1. Lead IA / Architecte IA agentique, secteur assurance (NEOGIA)**
Agents IA autonomes orchestrés pour automatiser la gestion de sinistres de bout en bout, avec points de validation humaine. Stack : Python, FastAPI, LangChain/LangGraph/CrewAI/AutoGen, pgvector/FAISS/Pinecone/Weaviate, Azure/AWS/GCP, Docker/K8s, MLflow.
https://www.free-work.com/fr/tech-it/job-mission/architecte-de-base-de-donnees/lead-ia-architecte-ia-agentique-secteur-assurance
*Adéquation* : excellente (LangGraph, multi-agents, FastAPI) et TJM au niveau conseil. Le rythme de télétravail est à négocier.

**F2. AI & Data Architect Senior GenAI / Agentic AI (Nicholson SAS)**
Architecture de solutions IA générative et agentiques : transformer des besoins métier en plateformes IA industrialisées à l'échelle du groupe. 10 ans d'expérience et plus exigés.
https://www.free-work.com/fr/tech-it/job-mission/directeur-de-la-data-cdo/463-ai-data-architect-senior-genai-agentic-ai
*Adéquation* : très bonne (posture lead/archi), TJM 850 €. "Déplacements ponctuels" est compatible avec l'exception TGV du profil. Démarrage ASAP alors que la dispo est en 01/2027 : à vérifier.

**F3. AI Engineer IA générative & agentique (IDEMYS)**
Agents, pipelines RAG, orchestration multi-agents, intégration API/BDD, évaluation qualité, gouvernance des données, industrialisation avec le DevOps. Stack : Python/FastAPI, Claude/Mistral/GPT/open source, LangChain/LangGraph/CrewAI/LlamaIndex, **MCP**, pgvector/Qdrant/Pinecone, Bedrock/Azure AI Foundry/Vertex AI, **Langfuse**/MLflow.
https://www.free-work.com/fr/tech-it/job-mission/data-engineer/ai-engineer-ia-generative-agentique-h-f-1
*Adéquation* : la stack la plus proche du CV de toute la passe, et le démarrage au 03/01/2027 colle à la dispo. TJM à fixer (viser 750-800 €).

**F4. Senior AI Engineer (AVELSEN, groupe du luxe)**
Internalisation d'agents IA jusque-là développés en externe : traitement d'avis consommateurs avec ticketing, assistants de rédaction d'emails multilingues, agents de recommandation CRM. Stack : Python, LangChain, LangGraph, RAG, Docker, K8s, GitLab CI, Azure.
https://www.free-work.com/fr/tech-it/job-mission/data-engineer/senior-ai-engineer-8

**F5 / F6. Architecte IA GenAI / Consultant Lead AI (ISUPPLIER, Montreuil)**
F5 : référentiel et standards Agentic AI du groupe ("Agentic AI Blueprint", patterns ReAct / Plan-and-Execute / multi-agents / Agentic RAG, choix des frameworks et des bases vectorielles). F6 : solutions IA de référence, standardisation des pipelines, accompagnement à la mise en production. Probablement le même client : ne postuler qu'à un des deux.
https://www.free-work.com/fr/tech-it/job-mission/architecte-de-base-de-donnees/fbo-architecte-ia-genai-solution-architect
https://www.free-work.com/fr/tech-it/job-mission/architecte-solutions/fbo-consultant-lead-ai-architecte-solutions-ia

**F7. Architecte IA générative & agentique, plateforme IA (CAT-AMANIA, grande banque)**
Architectures de référence (assistants, RAG, agents), plateforme IA du groupe, sécurité/conformité, évaluation des modèles, GitOps sur OpenShift. Stack : Python/FastAPI, Java/Quarkus/LangChain4j, LangGraph/LlamaIndex/CrewAI, vLLM/KServe/OpenShift AI, ArgoCD, pgvector/Milvus/Qdrant, **Langfuse**/OpenTelemetry/MLflow.
https://www.free-work.com/fr/tech-it/job-mission/architecte-cloud/architecte-ia-generative-agentique-plateforme-ia-rag-agents-et-llmops-sur-cloud-prive
*Adéquation* : excellente sur le fond (évaluation, Langfuse, conformité). Le plafond de 620 € est juste au-dessus du plancher.

**F8. AI Engineer IA générative & LLM (Signe +, grande banque)**
Extraction IA et optimisation de pipelines pour deux projets de gestion des risques (reporting contrôles internes, automatisation de conformité "Risk Eye Check") : agentique, consensus multi-pipelines, documents non structurés (Word/PDF/PPT/CSV), VLM apprécié.
https://www.free-work.com/fr/tech-it/job-mission/data-engineer/ai-engineer-ia-generative-llm-h-f
*Adéquation* : correcte, TJM sous le plancher.

**F9 / F10** (TJM sous le plancher, pour mémoire) :
https://www.free-work.com/fr/tech-it/job-mission/developpeur-autre-langage-cobol-perl-vba-ruby-shell/un-e-developpeur-se-ia-genai-expert-e-mistral-ai
https://www.free-work.com/fr/tech-it/job-mission/ingenieur-apres-vente/ingenieur-ia-llmops

### 3.D Strasbourg / Alsace (hybride accepté)

**Marché ouvert à sec.** Free-Work filtré sur Strasbourg (Agent IA, Machine Learning, IA générative, Python, .NET, Lead Developer) ne remonte aucune mission IA ou dev lead pertinente. Seules apparaissent de la production applicative et de l'infra (200-309 €/j).

- **Piste expirée, à surveiller** : *Platform Engineer IA générative / Agentic AI* (eMatiss, Strasbourg). Télétravail majoritaire, 3 premiers jours sur site, puis ateliers trimestriels. Projet : plateforme commune pour industrialiser les outils GenAI et standardiser le développement d'agents. Publiée le 30/07/2026, page aujourd'hui "supprimée ou expirée". Exactement le type de rôle visé : surveiller une republication par eMatiss.
  https://www.free-work.com/fr/tech-it/job-mission/data-engineer/platform-engineer-ia-generative-agentic-ai
- Le reste à Strasbourg, ce sont des CDI (par ex. SFEIR "AI Engineer") ou des profils freelances sur Malt (offre de service, pas des missions).

---

## 4. Lecture du marché

**TJM observés**
- France, IA générative : confirmé 400-550 € ; senior/lead 550-780 € ; architecte GenAI/agentique 700-950 €, jusqu'à 1 150 € (NEOGIA). Le 800 € cible est réaliste pour du lead/archi ; 1 200 € reste réservé au conseil très senior.
- UK full remote : 350-650 £/j en pratique, alors qu'itjobswatch donne une médiane GenAI de 750-850 £/j. Les tarifs hauts se concentrent sur l'hybride, l'Inside IR35 ou les postes avec clearance.
- Intermédiaires UE anglophones : 38-65 $/€ de l'heure chez les ESN offshore-friendly (Netguru, Jimmy), sous la cible. Les boutiques haut de gamme (Proxify, A.Team, Toptal, Gramian) ne publient pas leurs tarifs : c'est là que se négocie la cible de 900-1 300 $/j.

**Full remote**
- Paris : la norme est 2-3 j/sem sur site. Le full remote ne figure pas dans les annonces ; il se négocie (séniorité, démarrage en janvier, mission longue).
- UK : "remote" veut souvent dire "remote depuis le UK".
- US : les contrats US sont W2/US-only dans leur immense majorité.

**Plateformes productives** : Free-Work (France), freelancermap et les boards Workable (UE anglophone). Les annonces expirent en quelques jours à quelques semaines : refaire une passe toutes les 1-2 semaines.

**Sources bloquées sans connexion** : Malt (missions invisibles), Comet, LinkedIn Jobs, Upwork (403), Arc.dev et WeAreDevelopers (403), Indeed et Adzuna (403), itjobswatch et ContractorUK (archives : pages 404/410). Les agents `scout-platforms` et `scout-linkedin` (Playwright avec profil connecté) combleraient ce trou, après `scripts/login_setup.py`.

---

## 5. Note sur `fetch_boards.py`

103 offres insérées (RemoteOK 75, Remotive 10, WeWorkRemotely 18), **dont environ 3 pertinentes** (A.Team, Secure Privacy, Vertican). Le reste : commerciaux, RH, US-only, Customer Success...
Cause : le mot-clé `ai` matche en sous-chaîne (Det**ai**l, Ret**ai**l, M**ai**ntain...) et `python` est trop large. À corriger plus tard : matcher par mot entier et sur le titre plutôt que la description, exclure les "US Only". Ces 103 lignes sont au statut `new` dans `data/prospector.db` ; le scorer les éliminera, ou on peut les passer en `ignored`.

---

## 6. Suggestions pour la suite (rien n'a été fait)

1. **Profil** : `config/profile.yaml` contient la coquille "Srtasbourg". De plus, `geo_rules` rend l'hybride éliminatoire, sans exception pour Strasbourg. Si l'hybride strasbourgeois est voulu, ajouter l'exception, sinon le scorer tuera ces missions.
2. **Inscriptions réseau** (sans engagement) : A.Team, Proxify, Toptal. Ce sont les canaux les plus solides pour du full remote anglophone.
3. **Missions à creuser en priorité** : A1 Llamazing, A2 Gramian, F3 IDEMYS, F1 NEOGIA, F2 Nicholson. Ensuite, si tu valides, passage par le pipeline normal (scorer, writer, /review).
4. **Strasbourg** : prospection directe via `scout-direct` (ESN et éditeurs alsaciens) plutôt que les boards.
