# Open Bot Team: analysis of Grok Bot and feature specification for an open reimplementation

Status: draft v1, 2026-09-09
Scope: (1) what Grok Bot (xAI, beta since 2026-08-11) actually is, feature by feature, from official docs and the xAI design article; (2) the open-source landscape on GitHub and how close each project gets; (3) a feature specification to reimplement the product with pluggable model providers (Ollama local, OpenAI, Anthropic, Google via API keys, or CLI subscriptions such as Claude Code, Codex CLI and Gemini CLI).

Everything in part 1 is sourced. Every requirement in part 4 carries an ID (F-xx) so it can be turned into tickets. Part 5 describes an architecture that keeps the same invariants the original enforces (one voice per bot, visible transcript, gates that cannot be talked past).

---

## 1. What Grok Bot is

### 1.1 One-line definition

Grok Bot is a desktop and mobile app in which a non-coder "hires" named, persistent AI teammates called Bots. Each Bot has an identity (name, avatar, title, description), its own memory, its own routines, and a cloud computer (browser, filesystem, terminal) shared by all Bots of the account. The user messages a Bot like a colleague, puts several Bots into a group chat where they hand work to each other in front of the user, gives them standing responsibilities (routines), and approves risky actions inline. Model selection is hidden: xAI routes to its own models and does not expose a model picker.

The mental model the user proposed is correct: it is the "agent team" idea of Claude Code, but with (a) all bot-to-bot exchanges surfaced in the transcript, (b) a conversational bot-creation onboarding instead of a prompt file, and (c) the user talking to a coordinator that dispatches, or to any specialist directly by mention.

### 1.2 The five product objects (xAI "Designing Grok Bot", 2026-09-03)

| Object | Definition in the design article |
|---|---|
| Bots | "persistent agents with their own identity, memory, runtime, and tools" |
| Chats | conversations with one Bot, or a group chat with 2 to 6 Bots plus the user |
| Prompts | instructions: used once, saved as Skills, or scheduled as Routines |
| Tools | information and actions through software, APIs, connectors (plugins, MCP), shell, or computer use |
| Artifacts | durable outputs (documents, designs, code, data) the Bots create or modify |

Design rule that drives the whole information architecture: "capabilities can be shared broadly while context remains with the role that needs it". Tools and Skills are account-level. Memory and Routines are Bot-level.

### 1.3 Bot identity and the roster

- Sidebar roster: each Bot is listed like a contact or channel. Sections group Bots by project or business and sync across devices. A Bot can be hidden instead of deleted.
- Identity fields: name, title, description, avatar (shape and color picked at creation). The description is operational, not cosmetic: "when one agent needs help with a task outside its lane, it scans the descriptions of other agents in your fleet and routes the request to whichever one matches". Durable rules go in the description; task-specific instructions go in messages.
- Avatar doubles as status. Six presence states: idle, thinking, working, waiting, blocked, done. Hovering reveals the current action ("Searching the web", "Edited math.ts +14 -10", "Ran full suite 212 passed").
- Limits observed: about 50 Bots per account, 6 per group chat, 50 routines per Bot, 20 run records kept per routine.

### 1.4 Bot creation (the "onboarding conversation")

Official flow: New (Ctrl/Cmd+N) then "Create new agent", give name, shape, color, title, then describe the desired outcome in the chat. The Bot answers with suggestions and asks what it is "around for" (research, writing, task management) and which tools or data sources it needs. If a plugin is needed it shows a "Connect" card. A hidden `[first run]` cue tells the Bot to open the conversation itself.

Community templates (49 profiles in cobusgreyling/grok-bot-templates, HAEGONG/grok-bot-profiles) converge on a profile structure: name and title, job (one main responsibility), operating contract (decision boundaries, approval gates), skills used, routines, handoff rules, a never-list, and a first task. The docs say a good Bot has "a distinct goal or area of ownership, set of tools and sources, working style, approval boundary, recurring schedule".

### 1.5 Chat with a Bot

- Message contents: text, links, images, local files. `/` references a saved skill. `@` mentions a Bot, a group, a routine or a connector. Reply to a specific message, react, send new instructions while work is running.
- Transcript is heterogeneous: prose bubbles, inline cards and widgets (email draft with Send and Discard buttons, status card "6 messages with Kenny, Tyler and Jenny", "Created Routine: Morning Briefing"), events (bot-to-bot messages, routine runs, settings changes) that the user can open for inspection. Principle: "the form of a response is part of the answer".
- Threads exist for feedback on a specific result; the main transcript stays the home.
- Search across messages, files and routines.

### 1.6 Bot-to-bot messaging and group chats

- Direct messaging: a Bot sends an asynchronous message to another Bot; "the receiving Bot wakes, handles the request, and can reply later". The handoff appears in the user's conversation. Bot-to-group handoff messages are text only (send an image directly to a Bot if it must see it).
- Routing: a Bot that is out of its lane looks at the descriptions of the other Bots and routes to the best match. Plugin connections are shared across the whole fleet.
- Group chat: 2 to 6 Bots, created from New chat, auto-named, membership editable, people can be added. Shared context is the group history; each Bot keeps its own specialized memory. The user writes naturally and Bots self-organize, or uses `@BotName` to assign ownership, or mentions several Bots. `@everyone` is for group-wide updates. Guidance: one owner per stage to avoid duplicate work.
- Runtime detail (Flavio Copes deep dive): "the group host still wakes each member in turn behind the scenes. Every Bot may spend time considering a message even when only one produces the useful answer". Known pain point: long multi-Bot discussions get noisy.
- Coordination philosophy: no assignment board, no explicit handoff controls; "coordinating Bots handle routine routing and bring the user in when a decision requires judgment".
- Popular pattern: a Chief of Staff Bot as single entry point that decides which Bot does what and reports back; or one project = one group channel with a PM Bot that watches and specialist Bots that mark themselves Blocked and ping the user.

### 1.7 Memory and context lifetime

- Per Bot: "stable working preferences, important facts, and summaries from its work". The conversation with the user is continuous across devices. Deleting a Bot removes profile, conversation and routines.
- Caveat in the docs: memory "is not a substitute for an authoritative source"; changing facts belong in the source system or in a file under `/workspace` on the shared computer.
- Shared between Bots: files, browser sessions and cookies, command-line credentials, group history, direct handoffs. Not shared: conversation memory and learned context.
- No user-facing memory editor is documented (only editing the description).

### 1.8 Skills

- "A reusable set of instructions for how to do a task". Created four ways: teach by demonstration (up to 10 minutes of recorded browser interaction turned into a draft skill), written instructions in chat ("save this as a skill named X"), marketplace install (Settings, Plugins), manual authoring.
- A good skill states when to use it, required inputs and access, sequence of work, how to validate the result, return format, approval requirements.
- Skills are account-level, invoked with `/name` in the composer, enabled per Bot in Settings, Plugins, Yours. Community format: `skills/<name>/SKILL.md` with YAML frontmatter (name, description, license) and a playbook body; installed by copying to `~/.grok/skills/` or via a plugin marketplace source.

### 1.9 Routines

- A routine tells one Bot when to run a workflow: on a schedule or after an event. Created conversationally ("every weekday at 8:00, read /workspace/learner-profile.md, produce X, never purchase, stop and report if the source is missing"), confirmed inline ("Done, your Morning Briefing will be here at 9:00 every day"), editable under View conversation details, Routines (schedule, instructions, enable or pause, test run, delete, run history with next run time).
- Schedule triggers: every day at, weekdays at, monthly on, every N minutes; time zone in settings.
- Event triggers: GitHub (PR opened, merged, closed, issue created or status changed, checks fail, comment with keyword, label added), Slack (new message, reaction, channel created), Jira and project tools (status change, cycle end), webhooks (POST).
- Silent routines are allowed: a run that sends no message is a success. Spend guard observed in the harness: after 3 idle days with 15 or more unread routine outputs, a nudge widget; three more unanswered days pause every routine.

### 1.10 Approvals and human gates

- Three answers: Allow once, Deny, Always allow (creates a matching rule). Settings, General, Auto-review holds Require approval rules (always stop) and Always allow rules (pass when automated review finds no issue). Recommended boundaries: sending messages or invitations, publishing, purchases and transfers, deleting or overwriting data, permission changes, production changes, accepting legal terms.
- The approval card "shows the proposed operation and its inputs"; the user reviews target, scope and values. One card per action fingerprint; denial or expiry ends the flow; the Bot must not rephrase its way past a block.
- Secret requests: passwords, passkeys, 2FA codes, CAPTCHAs, payment confirmations are entered in a masked field or done by the user taking over the computer; "the value is masked, excluded from the transcript, and not shown to the model".
- Local computer access: Settings, General, Agent, Execution on local computer: always ask (default), always allow, never.

### 1.11 The computer

- One persistent cloud VM per account, shared by all Bots, each Bot with its own screen. Browser (shared cookies and sessions), filesystem (`/workspace` durable, temp and manually installed packages replaceable), terminal (shared credentials). Update, Recover, Reset preserve the workspace.
- Three levels of visibility: Status (title bar icon turns purple), Preview (pinned side panel), Takeover (full screen, user completes the blocked step then hands back).
- Tool preference ladder taught to the Bot: memory and local files, then service connector (MCP or plugin), then public web, then signed-in browser, then desktop GUI, then hand back to the user. "Skipping a rung is a product error".
- Warning in the docs: separate Bots are not separate security boundaries on the shared computer.

### 1.12 Plugins, connectors, MCP, marketplace

Settings, Plugins, Marketplace: connectors (Gmail, Google Calendar, Slack, Google Drive, GitHub, ClickUp, Notion, Jira, Composio 1000+ apps), MCP servers, packaged skills, Bot templates (public marketplace, 9 categories). Connections are authorized once and shared by the fleet. Credentials go in secure fields, never in transcripts.

### 1.13 Platforms, pricing, limits

macOS, Windows, iOS at launch, Linux and Android later. Bundled in SuperGrok Plus and Heavy, Cursor Pro+, Ultra, Teams; enterprise with SSO, network and audit controls (2026-09-03). Usage is metered separately with weekly limits that can stall a group mid-run.

### 1.14 Runtime architecture observed in the desktop harness (learn-grok-bot reconstruction of build 0.18)

This unofficial course rebuilt the shape of the Electron harness. The parts worth copying as invariants:

- Six processes: renderer (untrusted UI, paints only), preload (typed RPC allowlist), main (Electron kernel, privileged windows), coordinator (fans transcript events to windows, forwards MCP, pushes roster status, never executes tools or calls the model), host (the employee kernel: roster, wake classification, system prompt, tool registry, SendMessage gate, auto-review, settlement), box (execution sandbox, remote or Docker).
- The voice: plain model text is an inner monologue and is never painted. The only chat bubble is an explicit `SendMessage` tool call. Message types: text (with images), attachment, widget (1 to 6 options, ends the turn), secret-request (ends the turn), cursor-agent card, channel-targeted text (`slack:C12345`).
- Wake classification: user text (must reply first), `[first run]` (must open), `[routine]` (may stay silent), `[inbound]` from a channel (untrusted, reply must target the channel), teammate `SendToAgent` (queued ahead of automations, `priority: true` interrupts), background revival.
- Transcript: append-only event log; entry kinds `send-message`, `message`, `user-attachment`, `notice`, `event`. Approval cards mutate their status in place instead of adding bubbles.
- Delegation: subagents (task, computer-use, cloud coding agent) have no `SendMessage`; the parent delivers results. "Giving the child a mouth destroys SendMessage: the user now has two employees talking at once".
- Enforcement in three tiers: system prompt (educates), middleware reminders (nudges), hard gates (tool permissions, preload denial, auto-review). Only the third tier is trusted.
- Storage: one folder per routine with `automation.json` and `runs.json`; profile files on `/home/box`; `/workspace` as scratch and durable project space.

### 1.15 Comparison with Claude Code agent teams

| Aspect | Claude Code agent team | Grok Bot |
|---|---|---|
| Agent definition | Markdown file with frontmatter, written by the developer | Conversational onboarding, description is the routing key, editable in a profile panel |
| Inter-agent messages | Mostly hidden inside the lead's tool results | Every handoff is a transcript event the user can open |
| User input | Goes to the lead; direct addressing of a teammate is indirect | Goes to the coordinator or to any Bot by `@name`, in a DM or a group |
| Persistence | Per session, memory files opt-in | Bot is a roster entry with memory, routines, and standing computer sessions |
| Scheduling | External (cron, loops) | Routines with schedule and event triggers, run history |
| Approvals | Permission modes per tool | Inline approval cards, Allow once, Always allow rules, secret requests |
| Model choice | Explicit per agent | Hidden router |

---

## 2. Open-source landscape (GitHub)

Full survey with tables and URLs in the companion file `OSS_LANDSCAPE.md`. Summary as of 2026-09-09:

- Explicit clones exist. Rakazo (https://github.com/elie222/rakazo, Apache-2.0, TypeScript, 2.1k stars, beta since late August 2026) is the closest single match: interview-style bot onboarding, roster of persistent bots with memory, routines and history, shared Team Computers and Private computers, Markdown routines, ask-first permissions with an audit log, peer-bot handoffs and subagents, Composio, Pipedream and MCP integrations, web, Electron and mobile clients, bring-your-own model through the Pi harness. Its gap is the 2 to 6 bot group chat: bots live in separate threads.
- OpenMausBot (Apache-2.0) has channels with an editable bot roster, permission cards, cron and webhook routines and a cloud or local desktop, but runs on `claude`, `codex` and `grok` CLIs, has no onboarding interview and no memory store. gawkbot has strict per-action approvals and visible consultations but a non-OSI license. OpenGrokBot (15 stars, MIT) is a literal paper copy with a chief-of-staff dispatch table and a two-hop relay cap on handoffs. Orkas and TinyAGI have the visible commander-plus-specialists chat or persistent team rooms with `@agent` routing, without sandbox or routines.
- Large platforms cover parts: OpenClaw (389k stars) has roster, cron, approvals and sandbox but hides agent-to-agent messages and lacks shared-context group chat; Paperclip (80k) is the best reference for org chart, budgets, approvals and routines UI; Hermes Agent has the best self-created skills loop; Buzz has agents as first-class members of channels with humans.
- Nothing open-source ships browser-recording teach-a-task, routing by reading other bots' descriptions, or the triad "visible handoff transcript, group chat, private screen on a shared computer" in one non-coder app.
- As building blocks for a fresh Python build, Agno AgentOS (Apache-2.0: Teams, sessions and memory, cron, confirmation gates, 25+ native providers, FastAPI and WebSocket) plus the MIT agent-ui shell is the recommended base; Microsoft Agent Framework is the runner-up. Provider layer: native SDKs behind a small interface (Anthropic documents its OpenAI-compat layer as not production-ready), LiteLLM only for the long tail.
- Decision framed in `OSS_LANDSCAPE.md` section 5: fork Rakazo and add group chats, description routing and an explicit provider screen, or build on Agno; in both cases prototype the group scheduler and the provider layer first as a stack-neutral module.

---

## 3. Product principles for the reimplementation

1. Coworker metaphor, not console. The roster, not the chat session, is the unit of persistence.
2. One voice per Bot. Model tokens are never shown; a Bot speaks only through an explicit send. Subagents have no voice.
3. Everything between Bots is visible. Bot-to-bot messages, handoffs, routine runs and approvals are first-class transcript events, collapsible but never hidden.
4. Gates are hard. Approval and secret handling are enforced by the runtime, not by the prompt.
5. Bring your own model. Every Bot has a model binding (provider, model, parameters) chosen from configured providers: Ollama, OpenAI, Anthropic, Google, OpenAI-compatible endpoints, and CLI subscriptions. Defaults are set once at the account level; a Bot can override.
6. Local first, cloud optional. The "computer" is a local sandbox (Docker or a plain workspace folder) by default; a remote VM is an adapter.
7. Ask less of the person. Fewer screens, more inline cards. "Did this help someone delegate, or did it give them one more thing to manage?"

---

## 4. Feature specification

Priority: P0 = MVP, P1 = second release, P2 = later. Each ID is testable.

### 4.1 Roster and Bot profile

| ID | P | Requirement |
|---|---|---|
| F-01 | P0 | Sidebar roster lists every Bot with avatar, name, title and presence state. Sections group Bots; drag to reorder; hide instead of delete. |
| F-02 | P0 | Presence states per Bot: idle, thinking, working, waiting, blocked, done, rendered on the avatar. Hover or tap shows the current action string emitted by the runtime. |
| F-03 | P0 | Bot profile: id, name, title, description (operational rules), avatar (shape, color or emoji), model binding, enabled skills, enabled connectors, approval rules, sections. Editable in a right-hand profile panel. |
| F-04 | P0 | Description is used for routing: the coordinator and any Bot can list the roster with descriptions to decide who owns an out-of-lane request. |
| F-05 | P1 | Duplicate a Bot, export and import a Bot profile as a portable folder (`bot.json`, `PROFILE.md`, `memory/`, `routines/`). |
| F-06 | P1 | Public templates gallery: install a Bot from a template repository (same folder format). |
| F-07 | P2 | Soft limits configurable: max Bots, max Bots per group, max routines per Bot. |

### 4.2 Guided Bot creation (the wizard)

| ID | P | Requirement |
|---|---|---|
| F-10 | P0 | New Bot starts with name, avatar shape and color, title. Nothing else is mandatory. |
| F-11 | P0 | A hidden `[first run]` wake makes the new Bot open the conversation and interview the user: what it is around for, expected outputs, tools and sources it needs, what must always be approved, whether it should run on a schedule. Two to six questions, one at a time, with suggested answers as widget options. |
| F-12 | P0 | From the interview the Bot drafts its own description (goal, ownership, working style, approval boundary, never-list, handoff rules) and shows it as an editable card; the user accepts or edits. The draft is stored as the profile description. |
| F-13 | P1 | The interview can also propose skills (as SKILL.md drafts) and a first routine, each shown as a card the user can accept, edit or discard. |
| F-14 | P1 | Templates: the wizard offers to start from a template (Chief of Staff, Researcher, PR Reviewer, Inbox Triage) and adapts it through the same interview. |
| F-15 | P1 | Connector prompts: when the interview identifies a needed connector that is not configured, an inline Connect card opens the connector setup. |

### 4.3 Chat and transcript

| ID | P | Requirement |
|---|---|---|
| F-20 | P0 | One continuous conversation per Bot, persisted, searchable, synced across clients. |
| F-21 | P0 | Composer accepts text, images, files; `/` lists skills; `@` mentions Bots, groups, routines, connectors. |
| F-22 | P0 | Transcript is an append-only event log with kinds: `send-message` (Bot bubble), `message` (user or teammate text), `attachment`, `notice`, `event` (background), `approval`, `secret-request`, `widget`. Model tokens are never a transcript entry. |
| F-23 | P0 | Streaming status: while a Bot works, the avatar state and a live action string update; the bubble appears only when the Bot sends. |
| F-24 | P0 | Inline widgets: option widget (1 to 6 choices, ends the turn), confirmation card, draft card (email or message with Send and Discard), routine-created card, handoff card, status card. Widgets are rendered from a typed schema, not from HTML produced by the model. |
| F-25 | P1 | Reply to a message, react, and open a thread on a message for focused feedback; the main transcript stays primary. |
| F-26 | P1 | Reference an artifact (file in the workspace) inline with preview and open action. |
| F-27 | P0 | User can send new instructions during a run; they are queued as a user wake with priority over automations. A Stop control cancels the current turn. |
| F-28 | P1 | Transcript export (Markdown, JSON). |

### 4.4 Bot-to-bot messaging and group chats

| ID | P | Requirement |
|---|---|---|
| F-30 | P0 | Tool `send_to_bot(bot_id, text, priority=false)`: asynchronous message to a teammate. The recipient wakes with a `[teammate]` cue and may reply later. `priority=true` interrupts non-user work; default queues ahead of routines. Group handoffs are text only; images go to a Bot directly. |
| F-31 | P0 | Every bot-to-bot message appears as a handoff event in the sender's conversation and in the recipient's conversation, and in the group transcript when sent in a group. The user can expand it to read the full text. |
| F-32 | P0 | Group chat with 2 to N Bots (default max 6) plus one or more users. Created from New chat, auto-named, membership editable later. |
| F-33 | P0 | Addressing in a group: plain text lets Bots self-organize; `@Bot` assigns ownership to that Bot only; multiple mentions wake each mentioned Bot; `@everyone` wakes all. |
| F-34 | P0 | Group host: a scheduler that wakes members in turn (or in parallel when explicitly mentioned), gives each the shared group history plus its private memory, and enforces one owner per stage: a Bot that is not mentioned and not the owner is asked a cheap "should I speak" decision before a full turn. |
| F-35 | P0 | Ownership: `claim_ownership(task)` and `pass_ownership(bot_id, task, summary)` tools; the current owner is displayed on the group header; the coordinator or the user can reassign. |
| F-36 | P1 | Noise control: per-group setting for verbosity (every message, owner only, summaries), automatic summary card when more than N bot-to-bot messages happen without user input ("6 messages between A, B and C", expandable). |
| F-37 | P1 | Bots can mark themselves blocked in a group; the group header shows blocked members and the reason; the user gets a notification. |
| F-38 | P2 | People in a group: multiple human users with roles (owner, member, viewer). |

### 4.5 Coordinator and dispatch

| ID | P | Requirement |
|---|---|---|
| F-40 | P0 | Any Bot can act as coordinator; a "Chief of Staff" template is provided: single entry point, decomposes goals, routes by roster descriptions, tracks who owns what, reports back, escalates only decisions. |
| F-41 | P0 | Routing tool `list_roster()` returns id, name, title, description, presence, enabled connectors of every Bot the caller may message. |
| F-42 | P0 | Subagents: `spawn_subagent(task, tools, model?)` runs a voiceless child with a fresh context that returns plain text to its parent; the parent decides what to send. Child activity appears as a collapsed event under the parent's turn. |
| F-43 | P1 | Coordinator may propose to create a new Bot when nothing on the roster fits; creation always requires user confirmation. |
| F-44 | P1 | Task board derived from ownership events (not a separate UI to maintain): per group, list of tasks with owner and state, filled by `claim_ownership`, `pass_ownership`, `mark_blocked`, `mark_done`. |

### 4.6 Memory and context lifetime

| ID | P | Requirement |
|---|---|---|
| F-50 | P0 | Per-Bot memory store: stable preferences, important facts, summaries of past work, as editable Markdown files under the Bot's folder. Injected in the system prompt with a size cap; older material is summarized. |
| F-51 | P0 | Conversation context policy per Bot: sliding window with automatic summarization once the context exceeds the model's budget; the summary is stored in memory and marked in the transcript as a notice. |
| F-52 | P0 | Memory scope rules: conversation and learned context are private to the Bot; files in the shared workspace, group history and handoffs are shared. Skills and connectors are account-level. |
| F-53 | P1 | Memory panel: view, edit, delete memory entries; "forget this" from a message; reset memory without deleting the Bot. |
| F-54 | P1 | Context lifetime settings per Bot: keep everything, summarize after N messages, or reset every day or every run (for routine-only Bots). |
| F-55 | P2 | Optional vector index over memory and workspace files for retrieval, provider-agnostic embeddings (Ollama or API). |

### 4.7 Skills

| ID | P | Requirement |
|---|---|---|
| F-60 | P0 | Skill = folder `skills/<name>/SKILL.md` with frontmatter (name, description, inputs, requires connectors, approval) and a playbook body (when to use, inputs and access, steps, validation, return format, approval requirements). Compatible with the community Grok Bot and Claude Code SKILL.md shape. |
| F-61 | P0 | Skills are account-level, enabled per Bot, invoked by `/name` in the composer or chosen by the Bot from descriptions. |
| F-62 | P0 | Save from chat: "save this as a skill named X" produces a SKILL.md draft card the user accepts or edits. |
| F-63 | P1 | Install skills from a Git repository or marketplace folder; update and remove. |
| F-64 | P2 | Teach by demonstration: record a browser session in the sandbox (actions and screenshots, up to 10 minutes) and convert it to a draft skill. |

### 4.8 Routines

| ID | P | Requirement |
|---|---|---|
| F-70 | P0 | Routine = one folder per routine with `routine.json` (owner bot, name, instructions or skill reference, inputs, schedule or trigger, approval boundary, error policy, enabled) and `runs.json` (last 20 runs: start, end, status, summary, transcript pointer). |
| F-71 | P0 | Schedules: every day at, weekdays at, weekly on, monthly on, every N minutes, cron expression; account time zone. |
| F-72 | P0 | Created conversationally: the Bot proposes a routine card with all fields; user confirms; confirmation appears inline. Also editable in a Routines panel (schedule, instructions, enable or pause, run now, delete, run history, next run). |
| F-73 | P0 | A `[routine]` wake may stay silent; sending nothing is a success. Output messages are grouped in the Bot's conversation with a run header. |
| F-74 | P1 | Event triggers via webhooks (POST with secret), file changes in the workspace, incoming channel messages (Slack, Telegram, Discord, email through connectors), GitHub events. Inbound content is marked untrusted in the prompt. |
| F-75 | P1 | Spend guard: pause routines after N unread runs plus M idle days, with a nudge widget first. Per-routine token and run-time budget. |
| F-76 | P2 | Routine templates in the marketplace (Morning briefing, Inbox cleanup, Weekly team update). |

### 4.9 Approvals, secrets and gates

| ID | P | Requirement |
|---|---|---|
| F-80 | P0 | Approval card with Allow once, Deny, Always allow; shows the operation, target, scope and input values. One card per action fingerprint; deny or timeout ends the flow; the runtime refuses a rephrased identical action while a card is pending or denied. |
| F-81 | P0 | Auto-review rules: Require approval rules (always stop) and Always allow rules (pass) per account and per Bot, matched on tool name and argument patterns (for example `shell` with `rm`, `send_email` any, `http` to a production host). |
| F-82 | P0 | Default require-approval set: sending messages or invitations, publishing, purchases and transfers, deleting or overwriting outside the workspace, permission changes, production changes, accepting legal terms, any local computer execution. |
| F-83 | P0 | Secret request: a masked input widget; the value is stored in the secret store, never in the transcript, never given to the model; tools receive a reference the runtime resolves. |
| F-84 | P0 | Gates are enforced by the runtime layer between the model and the tool, never by prompt alone. The renderer cannot call tools. |
| F-85 | P1 | Takeover: for browser actions, the user can take control of the sandboxed browser to complete a login, 2FA or CAPTCHA, then hand back. |
| F-86 | P1 | Audit log: every tool call, approval decision and secret use is logged with bot, time, and rule matched; exportable. |

### 4.10 The computer (sandbox and tools)

| ID | P | Requirement |
|---|---|---|
| F-90 | P0 | Workspace: a durable folder per account (`workspace/`) shared by all Bots, plus a private folder per Bot (`bots/<id>/home`). Tools: read, write, list, search. |
| F-91 | P0 | Shell tool in a sandbox: Docker container by default (image configurable), plain subprocess in a restricted folder as fallback; time and output limits. |
| F-92 | P0 | Web tools: search (configurable engine: SearXNG local, Brave, Tavily, Google) and fetch to Markdown. |
| F-93 | P1 | Browser tool: headless Chromium (Playwright) in the sandbox with a persistent profile per account (shared cookies and sessions across Bots), screenshots to the transcript, Preview panel with live view, Takeover mode. |
| F-94 | P1 | Computer preview levels: status icon, pinned side panel, full-screen takeover. |
| F-95 | P0 | MCP client: connect stdio and HTTP MCP servers at account level; expose their tools to enabled Bots; OAuth handled by the runtime, tokens stored in the secret store. |
| F-96 | P1 | Built-in connectors as MCP servers: Gmail, Google Calendar, Google Drive, Slack, GitHub, Notion, Telegram, Discord, generic IMAP and SMTP. |
| F-97 | P1 | Local computer access (user's machine, outside the sandbox): separate tools `local_read`, `local_shell`, gated by the three-way setting always ask, always allow, never. |
| F-98 | P0 | Tool preference ladder written into the base system prompt: memory and files, connector, public web, signed-in browser, GUI, hand back to the user. |
| F-99 | P2 | Remote computer adapter: run the box on a VPS or cloud VM through the same accessor interface. |

### 4.11 Model providers and bindings

| ID | P | Requirement |
|---|---|---|
| F-100 | P0 | Providers configured at account level in Settings, Models: Ollama (base URL), OpenAI (API key, base URL), Anthropic (API key), Google Gemini (API key), any OpenAI-compatible endpoint (base URL, key), OpenRouter. Keys live in the secret store. |
| F-101 | P0 | Subscription providers through local CLIs, for users who pay a plan rather than per token: Claude Code (`claude -p` headless with JSON streaming), OpenAI Codex CLI, Gemini CLI. Each is wrapped as a provider with the same chat and tool-call interface; tool calls are executed by our runtime when the CLI supports MCP or hooks, otherwise the CLI runs with its own tools inside the sandbox. |
| F-102 | P0 | Model binding per Bot: provider, model, temperature, max output tokens, context budget, optional reasoning effort; plus a cheap "utility" binding used for routing, should-I-speak decisions and summaries. Account defaults apply when a Bot has none. |
| F-103 | P0 | Provider abstraction exposes: streamed chat with system prompt, tool definitions and parallel tool calls, images in, token usage, cancellation. Capability flags (tools, vision, json mode, reasoning) decide what the runtime offers to a Bot. |
| F-104 | P0 | Model list is fetched from each provider where possible (Ollama tags, OpenAI models, Anthropic models list, Gemini models list) and cached; manual entry allowed. |
| F-105 | P1 | Per-Bot and per-account usage view: tokens, cost estimate from a price table, runs, by day. |
| F-106 | P1 | Fallback chain per binding: if the primary provider fails or rate-limits, try the next; the switch is shown as a notice in the transcript. |
| F-107 | P2 | Router mode: an optional policy that picks a model per turn (cheap for routing and chit-chat, strong for planning and code), mimicking the hidden router of the original but with the decision visible in the transcript event. |

### 4.12 Settings, notifications, multi-device

| ID | P | Requirement |
|---|---|---|
| F-110 | P0 | Settings: General (time zone, language, local execution policy), Models, Plugins (connectors, MCP servers, skills, marketplace sources), Auto-review rules, Secrets, Storage (workspace path, backups). |
| F-111 | P0 | Notifications: desktop notifications for blocked Bots, approvals pending, routine failures, group mentions; grouping per Bot. |
| F-112 | P1 | Clients: web UI served by the local server (primary), desktop wrapper (Tauri or Electron), mobile web layout; the same account and transcripts on every client. |
| F-113 | P2 | Multi-user account (team): several people, shared roster, per-person approvals. |

---

## 5. Architecture

### 5.1 Processes

Same separation as the original, reduced to four processes to stay simple:

```
+------------------+    typed events (WS)     +---------------------+
|  Renderer (UI)   | <----------------------> |  Coordinator (API)  |
|  React, no tools |    commands (HTTP)       |  fan-out, auth,     |
+------------------+                          |  roster status,     |
                                              |  MCP proxy          |
                                              +----------+----------+
                                                         | in-process queue
                                              +----------v----------+
                                              |  Host (kernel)      |
                                              |  wake classifier,   |
                                              |  turn runner,       |
                                              |  SendMessage gate,  |
                                              |  auto-review,       |
                                              |  scheduler          |
                                              +----------+----------+
                                                         | accessor interface
                                              +----------v----------+
                                              |  Box (sandbox)      |
                                              |  Docker or folder,  |
                                              |  browser, shell     |
                                              +---------------------+
```

- Renderer never executes anything and never sees secrets or model tokens.
- Coordinator owns the transcript event contract and the WebSocket fan-out; it never calls the model or runs a tool. A blocked shell must never freeze the chat.
- Host owns Bots: one runner per Bot with a queue of wakes; a group host schedules member turns.
- Box is behind an accessor interface with two implementations (Docker, local folder) and room for a remote one.

Recommended stack: Python 3.12 with FastAPI for coordinator and host (async, WebSocket, APScheduler, Playwright, MCP Python SDK, LiteLLM or a thin native adapter layer), React and Vite for the renderer, SQLite for transcripts and indexes, plain files for Bot folders (git-friendly). Tauri wrapper for the desktop build.

### 5.2 Turn lifecycle (per Bot)

1. A wake arrives: user message, `[first run]`, `[routine]`, `[inbound]`, `[teammate]`, or revival. The classifier sets `must_reply_first`, `silence_allowed`, `trusted`.
2. Build the system prompt: base rules (voice, ladder, gates), Bot profile, memory digest, roster digest (names, titles, descriptions), enabled skills index, group context if any.
3. Assemble tools from the Bot's enabled surfaces; add `send_message` only for a top-level Bot, never for a subagent.
4. Stream the model. Model text is stored as hidden monologue (debug view only). Tool calls go through the gate layer: auto-review rules, pending approval fingerprints, secret resolution.
5. `send_message` creates a transcript bubble; a widget or secret request sets `awaiting_user` and ends the turn.
6. Settle: persist state, update presence to done or waiting, write memory updates the Bot requested through `remember(fact)`, emit usage.

### 5.3 Group host

- Group transcript is one event log; each member turn sees the group history plus its private memory.
- On a user message: mentioned Bots wake in parallel; with no mention the current owner wakes first, other members get a utility-model "should I speak" check limited to one short call, and only those that answer yes get a full turn. This is the fix for the noise pain point of the original.
- Bot-to-bot messages in the group are transcript events with `from`, `to`, `text`; the recipient wakes with a `[teammate]` cue. Loop guard: a Bot may not send to the same recipient more than K times without a user message or an ownership change.
- Ownership state lives in the group document and is shown in the header.

### 5.4 Data model (files first)

```
account/
  settings.json                  time zone, policies, default bindings
  providers.json                 providers (keys referenced from the secret store)
  secrets.db                     encrypted secret store (OS keychain when available)
  workspace/                     shared durable files (artifacts)
  skills/<name>/SKILL.md
  connectors/<name>.json         MCP or connector config
  bots/<bot_id>/
    bot.json                     id, name, title, avatar, model binding, enabled skills and connectors, approval rules, section
    PROFILE.md                   description written with the wizard
    memory/*.md                  facts, preferences, summaries
    routines/<routine_id>/routine.json, runs.json
    home/                        private files
  groups/<group_id>/group.json   members, name, owner state, verbosity
  transcripts.db                 SQLite: events(id, scope, kind, from, to, ts, payload_json, reply_to)
  audit.db                       tool calls, approvals, secret uses
```

### 5.5 Provider layer

- Interface: `chat(messages, tools, stream, params) -> events(text_delta, tool_call, usage, done)` plus `list_models()` and `capabilities()`.
- API providers: native SDKs behind small adapters, or LiteLLM for breadth; both must normalize tool calls and streaming.
- CLI subscription providers: spawn the CLI in the sandbox with the Bot's home as cwd, stream its JSON events, map them to the same event types. Approvals for CLI-run tools use the CLI's own permission hooks when available (Claude Code hooks call back into our gate API), otherwise run in restricted mode and surface actions as events after the fact with a warning in the profile panel.
- Utility binding: a small, cheap model (local Ollama by default) for routing, should-I-speak and summaries.

### 5.6 Security invariants

- Secrets never enter prompts, transcripts or the renderer.
- Tools run in the box; local machine tools are separate and default to always ask.
- Inbound channel content is marked untrusted and cannot trigger Always allow rules.
- One approval card per fingerprint; the gate ignores prompt-level attempts to bypass.
- Bots on one account share the workspace and browser profile; the UI states that Bots are not security boundaries, as the original does.

---

## 6. Roadmap

- MVP (P0): roster, wizard, single-Bot chat with tools in a Docker box, memory, skills as SKILL.md, routines with schedules, approvals and secrets, bot-to-bot messages and group chat with owner and should-I-speak, providers Ollama, OpenAI, Anthropic, Google, OpenAI-compatible, Claude Code CLI. Web UI served locally.
- Release 2 (P1): browser tool with preview and takeover, MCP connectors, event triggers, threads, memory panel, usage and costs, fallback chains, templates and marketplace sources, desktop wrapper.
- Release 3 (P2): teach by demonstration, remote box, router mode, multi-user accounts, vector memory.

---

## 7. Sources

Official
- Introducing Grok Bot: https://x.ai/news/introducing-grok-bot
- Designing Grok Bot (2026-09-03): https://x.ai/news/designing-grok-bot
- Docs overview: https://docs.x.ai/grok-bot/overview
- Create and manage Bots: https://docs.x.ai/grok-bot/bots
- Chat and collaboration: https://docs.x.ai/grok-bot/chat-and-collaboration
- Skills and routines: https://docs.x.ai/grok-bot/skills-routines-and-automations
- Approvals, security and privacy: https://docs.x.ai/grok-bot/approvals-security-and-privacy
- Computer and apps: https://docs.x.ai/grok-bot/computer-and-apps
- Cursor help, getting started: https://cursor.com/help/grok-bot/getting-started
- Guide, running multiple teams of Bots: https://x.ai/bot/guides/how-i-run-multiple-teams-of-grok-bots
- Release notes: https://releasebot.io/updates/xai

Analyses and tutorials
- Composio guide: https://composio.dev/content/guide-to-frok-bot
- MindStudio setup guide: https://www.mindstudio.ai/blog/grok-bot-setup-guide
- MindStudio fleet article: https://www.mindstudio.ai/blog/grok-bot-ai-agent-fleet
- MindStudio vs OpenClaw vs ChatGPT: https://www.mindstudio.ai/blog/grok-bot-vs-openclaw-chatgpt
- VentureBeat: https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month
- Flavio Copes deep dive: https://flaviocopes.com/grok-bot/
- DataCamp tutorial: https://www.datacamp.com/tutorial/grok-bot-tutorial
- Vellum, alternatives: https://www.vellum.ai/blog/best-grok-bot-alternatives

Community repositories used for formats and patterns
- awesome-grok-bot: https://github.com/RongleCat/awesome-grok-bot
- learn-grok-bot (harness reconstruction course, 16 lessons): https://github.com/yuanyijie/learn-grok-bot
- grokbot-sdk (TypeScript client of the local host gateway): https://github.com/adam91holt/grokbot-sdk
- Bot profile templates: https://github.com/cobusgreyling/grok-bot-templates and https://github.com/HAEGONG/grok-bot-profiles
- SKILL.md catalog: https://github.com/jaskirat1616/grok-skills
- Observable multi-agent org demo: https://github.com/monokernn/Grok_Bot_Architecture
