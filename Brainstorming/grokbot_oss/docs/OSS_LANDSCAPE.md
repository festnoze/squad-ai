# Open-source landscape for a Grok Bot reimplementation (2026-09-09)

Companion to `SPEC.md`. Two questions: which open-source projects already reproduce Grok Bot, and which frameworks are the right building blocks if we build our own. Star counts are approximate GitHub values read on 2026-09-09.

Feature columns used in the tables:
1 guided no-code bot creation with generated prompt, 2 persistent per-bot memory, 3 inter-bot messages visible to the user, 4 group chat with several bots and the user, 5 lead or coordinator dispatching or user addressing one bot, 6 routines (cron, triggers), 7 skills or teach-a-task, 8 approvals, 9 sandbox computer (browser, files, shell), 10 GUI for non-coders. Y yes, P partial, N no.

## 1. Explicit Grok Bot clones and alternatives

| Project | Stars | Stack | License | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Rakazo https://github.com/elie222/rakazo | 2.1k | TS, React 19, Vite, Hono, oRPC, Postgres, Prisma, Electron, Expo, Docker or E2B or Daytona | Apache-2.0 | Y | Y | P | N | P | Y | P | Y | Y | Y |
| OpenMausBot https://github.com/milind-soni/OpenMausBot | 2.3k | TS, React, Electron | Apache-2.0 (enterprise dir source-available) | P | P | P | Y | P | Y | N | Y | Y | Y |
| gawkbot https://github.com/najmuzzaman-mohammad/gawkbot | 1.3k | Go, TS React, Bun | Sustainable Use License (not OSI) | Y | Y | Y | N | P | Y | P | Y | Y | Y |
| OpenGrokBot https://github.com/wolfqing/OpenGrokBot | 15 | Node TS, Docker | MIT | P | Y | Y | Y | Y | Y | N | Y | Y | P |
| Orkas https://github.com/Orkas-AI/Orkas | 1.8k | Electron, Python | MIT | Y | Y | Y | P | Y | N | Y | Y | P | Y |
| TinyAGI (ex TinyClaw) https://github.com/TinyAGI/tinyagi | 3.6k | TS Node, Next.js | MIT | P | Y | Y | Y | Y | P | P | P | P | Y |
| guaca https://github.com/madebywelch/guaca | 33 | Rust Tauri, TS | AGPL-3.0 | N | Y | Y | P | P | N | N | Y | P | Y |
| akeru-bot https://github.com/opencoredev/akeru-bot | 68 | TS Electron (fork of T3 Code) | MIT | ? | Y | ? | ? | ? | ? | ? | ? | ? | Y |

### Rakazo (closest single match)

Tagline: "Open-source Grok Bot alternative. Choose your own model and sandbox." Author Elie Steinbock (Inbox Zero). v0.1.0-beta late August 2026, about 800 commits, active.

- Bot creation: "Start a new bot and it interviews you. A few questions about the work, how you write, and where it lives." This is the onboarding conversation of the original.
- Persistence: "Persistent bots with their own conversations, memory, routines, and history."
- Computers: "Shared Team Computers and isolated Private computers", browser, terminal, files and graphical desktop; backends Docker, E2B, Daytona, Box, local Docker. Same shape as the shared VM with private screens.
- Routines: readable Markdown routines on schedules ("Morning sweep, weekdays 6am").
- Teaching: "Show a bot a workflow once and it saves a routine as plain Markdown you can read, edit, and commit." Not browser recording.
- Approvals: "Set what a bot may do alone and what it must ask about. Every action lands in an audit log you own."
- Delegation: "Bots that can delegate to peer bots or short-lived subagents"; a Chief of Staff template hands off to other bots.
- Models: bring your own credentials through the Pi harness (Claude, GPT, Grok, local models), OpenRouter key; Ollama is covered by the local model path but not named in the README.
- Integrations: Composio, Pipedream Connect, remote MCP, OpenAPI tools. Clients: web, Electron, Expo mobile, 9 UI languages.
- Gap versus Grok Bot: no 2 to 6 bot group chat with a shared transcript; each bot has its own thread and handoffs are peer messages. Also very young.
- Repo layout: `apps/` (web, api, worker, desktop, mobile), `packages/` (domain, contracts, persistence, adapters, ui, testing), `infra/`, `docs/`.

### OpenMausBot

Shipped the day after the Grok Bot launch. Channels with their own transcript, shared instructions, working folder, responder rules and an editable bot roster (group chat, yes). Permission broker with inline Allow and Deny cards. Cron routines (5 to 1440 minutes, weekday selection) and webhook triggers. Cloud desktop through the Box API with live screen preview, or control of the local machine. Drives `claude`, `codex`, `grok` CLIs, any ACP CLI or OpenAI-compatible endpoint, so it runs on subscriptions rather than API keys. No onboarding interview, no long-term memory store, and bot-to-bot tagging was reported broken in early beta.

### gawkbot

Describe a workflow and a live streaming build assembles a screen, routine and tools. Memory in local files with knowledge pages and citations. Visible consultations ("filer consulted 2 bots"). Per-action approval on every send, commit, purchase, delete. Each bot is a local worker with shell, browser and working directory. Backends: Claude Code, Codex CLI, Opencode, Ollama, MLX-LM, Hermes, OpenClaw gateway. Web UI on port 7891, Composio integrations. License is Sustainable Use, so not reusable in a commercial product without care. No group chat.

### OpenGrokBot

Tiny but the most literal paper copy: hire from the sidebar with a name and one line of job description, MEMORY.md per agent, group threads where each teammate answers for its own patch, chief-of-staff dispatch table, allowlisted peer handoffs with a two-hop relay cap, cron in plain English, draft-and-hold approvals, takeover login for credential sites, headed Chromium and shell in containers, any OpenAI-compatible endpoint including Ollama. Teach-a-task on the roadmap. Worth reading for its dispatch table and relay cap, not for forking.

### Orkas and TinyAGI

Orkas: commander plus specialists in one visible chat, agents created through conversation, private skills and memory per agent with reflection after each task, human approvals and runaway guards, many providers including Ollama and LM Studio, plus Claude Code, Codex, OpenCode and Cline as coding backends. No cron, no browser VM, commander-centered rather than free group chat.

TinyAGI: `@agent_id` routing and `[#team_id: message]` posts in persistent team chat rooms visible to everyone, chains and fan-out by multiple mentions, TinyOffice dashboard (chat console, agents and teams, kanban, org chart), Discord, WhatsApp, Telegram. Runs Claude Code CLI, Codex CLI or OpenAI and Anthropic compatible endpoints. Heartbeat only, no cron; only workspace directories, no sandbox. Smallest codebase that already has "several agents plus the user in one persistent room".

### Adjacent, not clones

- grokbot-shim https://github.com/codeaashu/grokbot-shim and grokrouter https://github.com/promptadvisers/grokrouter make the official desktop app run on other models with a local Docker desktop.
- grokbot-sdk https://github.com/adam91holt/grokbot-sdk is a TypeScript client of the official app's local HTTP gateway (roster, prompts, memory, `sendAsAgent`).
- learn-grok-bot https://github.com/yuanyijie/learn-grok-bot is a 16-lesson reconstruction of the desktop harness (processes, wakes, transcript, gates); teaching material, not a runtime.
- Topic page https://github.com/topics/grok-bot, lists https://github.com/RongleCat/awesome-grok-bot and https://github.com/kydlikebtc/awesome-grokbot.

## 2. General agent platforms that cover part of the shape

| Project | Stars | Stack | License | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OpenClaw https://github.com/openclaw/openclaw | 389k | TS Node | MIT | P | Y | P | P | Y | Y | Y | Y | Y | P |
| Hermes Agent https://github.com/NousResearch/hermes-agent | 243k | Python | MIT | P | Y | N | N | P | Y | Y | Y | Y | P |
| Paperclip https://github.com/paperclipai/paperclip | 80k | Node TS, React, Postgres | MIT | P | Y | Y | P | Y | Y | P | Y | P | Y |
| Multica https://github.com/multica-ai/multica | 49k | Go, Next.js, Electron, Expo | Apache-2.0 plus conditions | Y | Y | Y | P | Y | Y | P | Y | P | Y |
| nanobot https://github.com/HKUDS/nanobot | 48k | Python | MIT | P | Y | P | N | P | Y | Y | P | P | Y |
| Buzz (Block) https://github.com/block/buzz | 32k | Rust, React, Tauri, Flutter | Apache-2.0 | N | Y | Y | Y | P | P | P | P | P | Y |
| Kortix Suna https://github.com/kortix-ai/suna | 20k | TS monorepo | Apache-2.0 | P | Y | P | N | P | Y | Y | Y | Y | Y |
| Agent Zero https://github.com/agent0ai/agent-zero | 19k | Python, JS | MIT | P | Y | P | N | Y | Y | Y | Y | Y | Y |
| Eigent (CAMEL) https://github.com/eigent-ai/eigent | 15k | Python, Electron | Apache-2.0 | P | P | P | N | Y | Y | P | P | Y | Y |
| Letta Code https://github.com/letta-ai/letta-code | 3.2k | TS Bun | Apache-2.0 | P | Y | P | N | P | Y | Y | Y | P | Y |

Notes
- OpenClaw: per-agent workspace and SOUL.md, bindings route channels to agents, `sessions_send` agent-to-agent is backend-only (users do not see it), true shared-context group chat is still an open issue (#34999, #71432), cron and heartbeat, exec approvals, Docker sandbox, all providers. Configuration-heavy for a non-coder.
- Hermes: the best self-improving skill loop (autonomous skill creation after complex tasks), cron, approvals, seven terminal backends, 20+ messaging platforms; single agent, not a roster.
- Paperclip: "If OpenClaw is an employee, Paperclip is the company." Org chart, CEO and managers delegating, budgets with hard stops, board approvals, heartbeat plus cron, immutable audit log, agents run through adapters (Claude Code, Codex, OpenClaw, Cursor, HTTP, bash). Best reference for governance UI.
- Buzz: agents as first-class members of channels, threads and DMs with humans, six months of history; creation, orchestration and approval gates still being wired.
- Agent Zero: superior and subordinate agents nested in the UI, Dockerized Linux desktop with browser, scheduler, MCP, LiteLLM providers; subordinates are ephemeral.

## 3. Frameworks as building blocks (if we build rather than fork)

| Framework | Persistent named agents | Orchestrator to specialists | Live inter-agent transcript in GUI | Routines | Approvals | Ollama, OpenAI, Anthropic, Gemini |
|---|---|---|---|---|---|---|
| Agno AgentOS https://github.com/agno-agi/agno (42k, Apache-2.0, Python) | sessions and memory in your DB | Teams route, coordinate, broadcast; member events streamable | partial (agent-ui is single thread) | cron schedules | confirmation and admin-blocked tools | 25+ native |
| Microsoft Agent Framework https://github.com/microsoft/agent-framework (13k, MIT, Python and .NET, v1.0 LTS) | code or YAML | group chat, handoff, magentic workflows, checkpoints | DevUI dev console | none | function approval events | all four native |
| Letta server https://docs.letta.com/guides/selfhosting/ (Apache-2.0) | yes, memory blocks, archival, sleep-time | supervisor and dynamic groups, subagents | ADE is closed source | cron in letta-code | permission modes | all four via env |
| OpenAI Agents SDK https://github.com/openai/openai-agents-python (29k, MIT) plus Agency Swarm https://github.com/VRSEN/agency-swarm | sessions | handoffs, agency chart with directional flows | CopilotKit demo | none | needs_approval with serializable RunState | OpenAI native, compat, LiteLLM |
| Google ADK https://github.com/google/adk-python (21k, Apache-2.0) plus adk-web | session services | transfer_to_agent, workflow agents | Events tab | none | tool confirmation | Gemini native, others via LiteLLM |
| LangGraph https://github.com/langchain-ai/langgraph (41k, MIT) plus langgraph-swarm | checkpointer and Store | supervisor and swarm handoffs | Studio is closed | Platform only (paid) | interrupt() | init_chat_model |
| AutoGen Studio https://github.com/microsoft/autogen (61k, MIT) | JSON team specs | selector, swarm, magentic | yes, streamed playground | none | UserProxy | OpenAI, Azure, Anthropic, Ollama, Gemini via compat |
| CrewAI https://github.com/crewAIInc/crewAI (58k, MIT) | JSON or YAML | hierarchical manager | events only | Enterprise | console | native plus LiteLLM |
| CAMEL https://github.com/camel-ai/camel (18k, Apache-2.0) | workers | Workforce coordinator | Eigent shows it | Eigent | HumanToolkit | ModelFactory, all four |

Set aside: AutoGen is in maintenance mode, open-agent-platform is archived, Flowise archived, kyegomez/swarms for maintainer reputation, MetaGPT and ChatDev are workflow or SOP engines without persistent personas, LangGraph Platform for the serving layer because Studio and self-hosted deployment sit behind paid tiers (the library is fine).

Model-provider layer, evidence:
- LiteLLM https://github.com/BerriAI/litellm: 100+ providers behind `provider/model` strings, fallbacks, budgets; heavy, and every framework that started on it later added native paths for the big four.
- OpenAI-compatible endpoints: Ollama `/v1`, Gemini `generativelanguage.googleapis.com/v1beta/openai/` (beta), Anthropic compat layer is documented as "not a long-term or production-ready solution" (no prompt caching, strict tools ignored, thinking not returned). Fine for a first cut, loses features.
- Native SDKs behind a small interface: what Agno, MAF, CAMEL and Letta do. Four adapters to maintain, best fidelity.
- Vercel AI SDK https://github.com/vercel/ai: TypeScript only, first-party OpenAI, Anthropic, Google; the natural choice if the backend is TypeScript (Rakazo uses the Pi harness instead).

UI pieces worth lifting
- agno-agi/agent-ui https://github.com/agno-agi/agent-ui (MIT, Next.js, shadcn): streaming chat shell speaking the AgentOS protocol.
- AutoGen Studio playground: agent-labelled live stream plus transition graph over WebSocket, and its JSON team schema.
- Paperclip: org chart, approvals inbox, routines list, activity feed.
- AG-UI protocol and CopilotKit https://github.com/ag-ui-protocol/ag-ui: HITL `renderAndWaitForResponse`, shared state, adapters for Agno, MAF, ADK, CrewAI, LangGraph.
- Eigent: React Flow canvas of a workforce working in parallel.

## 4. What nobody ships today

- Teach-a-task as browser recording to skill (Rakazo turns a demonstrated workflow into a Markdown routine; gawkbot claims screen-share teaching; OpenGrokBot has it on the roadmap).
- Description-based automatic handoff (the original reads the other Bots' descriptions to route). Mature projects route by explicit mention, channel bindings or a fixed commander.
- The full triad in one non-coder desktop app: visible bot-to-bot handoff transcript, 2 to 6 bot group chat with the user, per-bot private screen on a shared computer. Rakazo has computers and handoffs without group chat; OpenMausBot and TinyAGI have group chat without the shared-computer model; Buzz has rooms without computers; OpenClaw has everything for a technical operator but hides agent-to-agent messages.
- Fleet-wide connector sharing as a first-class concept exists only in OpenClaw (gateway), Paperclip (Skill Studio) and Multica.

## 5. Decision: fork or build

Option A, fork Rakazo (recommended if the goal is a working product soon)
- Pros: Apache-2.0, already the Grok Bot shape (interview onboarding, roster, memory, routines, approvals with audit log, team and private computers, peer handoffs, three clients), clean monorepo with domain, contracts, adapters packages, Postgres, worker queue.
- Work to add from `SPEC.md`: group chats with owner and should-I-speak scheduling (F-32 to F-37), visible handoff events in both transcripts (F-31), routing by descriptions (F-04, F-41), a provider settings screen that exposes Ollama, OpenAI, Anthropic, Google and CLI subscriptions explicitly (F-100 to F-104), event-triggered routines (F-74), memory panel (F-53).
- Risks: TypeScript stack (the team's other projects are Python), Pi harness as model layer (check its provider list and tool-call fidelity), beta churn.

Option B, build in Python on Agno AgentOS with a React shell forked from agent-ui
- Pros: Python, 25+ native providers, Teams, sessions and memory in SQLite or Postgres, cron schedules, confirmation gates, FastAPI plus WebSocket, MIT UI shell. Matches the process model in `SPEC.md` section 5.
- Work: everything user-facing (roster, wizard, group room, cards and widgets, approvals UI, routines UI), the box accessor (Docker, Playwright), SKILL.md loader, CLI subscription providers.
- Risks: more to build; Agno's control plane is commercial (the runtime and agent-ui are open).

Option C, TinyAGI or OpenMausBot as the group-room core plus Rakazo ideas: smaller codebases but weaker foundations (no sandbox in TinyAGI, no memory in OpenMausBot).

Recommendation: prototype the group-chat scheduler (owner, should-I-speak, loop guard) and the provider layer as a standalone Python module first, because those two parts are the ones nothing open-source gets right and they are stack-neutral; then decide A or B on the basis of how much of Rakazo's TypeScript the team is willing to own.

## Sources

All URLs are inline above. Additional reading used by the survey: https://www.eesel.ai/blog/grok-bot-review, https://openalternative.co/alternatives/grok-bot, https://www.marblism.com/blog/grok-bot-alternatives, https://www.vellum.ai/blog/best-grok-bot-alternatives, https://docs.openclaw.ai/concepts/multi-agent, https://team400.ai/blog/2026-04-openclaw-group-messages-ai-agents, https://news.ycombinator.com/item?id=49531991, https://deepwiki.com/elie222/rakazo, https://docs.agno.com/agent-os/introduction, https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/, https://openai.github.io/openai-agents-python/human_in_the_loop/, https://docs.letta.com/tutorials/multi-agent/, https://platform.claude.com/docs/en/api/openai-sdk, https://ai.google.dev/gemini-api/docs/openai.
