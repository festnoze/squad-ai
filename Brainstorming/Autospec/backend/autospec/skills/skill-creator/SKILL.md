---
name: skill-creator
description: |
  Scaffold a new bundled skill (or improve an existing one) for the Autospec factory's skill library,
  using the exact frontmatter format the factory expects. Use when the factory needs to grow a new
  capability: a reusable workflow, domain knowledge, or template set that dev agents should follow.

  Use when:
  - Creating a new skill folder + SKILL.md
  - Updating an existing skill's instructions or frontmatter
  - Splitting a long skill body into references/

  Triggers: "create skill", "new skill", "author skill", "add a skill", "update skill",
  "skill frontmatter", "scaffold skill"
---

# Skill Creator

Author a new skill so another (headless) Claude dev agent can follow it. A skill is a folder with a
required `SKILL.md` and optional `references/` (and `assets/`) subfolders. No scripts, no activation
hook, no extra docs.

## Frontmatter — use EXACTLY this format

Only these two fields. `name` MUST equal the folder name (kebab-case).

```yaml
---
name: <kebab-case-name-matching-the-folder>
description: <one paragraph: what it does + "Use when:" bullets + "Triggers:" comma list>
---
```

The `description` is the only thing the factory reads to decide when to load the skill, so it must
state both what the skill does and the concrete situations/keywords that should trigger it. Mirror
the style of the sibling skills (`db-entity-change`, `repo-search-or-create`, ...).

## Folder layout

```
<skill-name>/
├── SKILL.md            (required: frontmatter + body)
└── references/         (optional: long templates / detailed guides, one level deep)
```

Do NOT create README.md, CHANGELOG.md, INSTALLATION.md, QUICK_REFERENCE.md, scripts, or activation
config. A skill contains only what an agent needs to do the job.

## Procedure

1. **Pin down concrete examples.** What requests should trigger this skill? What does success look
   like? List 2-3 example invocations before writing anything.
2. **Decide reusable contents.** If agents would otherwise re-derive the same templates/schemas every
   time, capture them in `references/`. If the body stays under ~120 lines, inline everything.
3. **Create `<skill-name>/SKILL.md`.** Write the frontmatter (above), then a lean, action-oriented
   body: a procedure the agent follows + one short template/example.
4. **Apply progressive disclosure.** Keep the body to the core workflow + selection guidance. Push
   long templates, per-variant details, and exhaustive examples into `references/*.md`, linked from
   the body with a clear "see X when Y" pointer. Keep references one level deep.
5. **Self-check** against the checklist below.

## Body writing guidelines

- Imperative/infinitive voice ("Create the entity file", not "You should create...").
- Assume the reader is a capable agent: add only non-obvious, project-specific knowledge. Skip
  generic Python/FastAPI explanations.
- Prefer concise examples over prose. Show the pattern; don't narrate it.
- Put ALL "when to use" information in the `description` — the body loads only after the skill
  triggers, so a "When to use" section in the body is wasted.
- For a `references/` file longer than ~100 lines, start it with a short table of contents.
- Information lives in either SKILL.md or a reference file, never duplicated in both.

## Checklist

- [ ] Folder name is kebab-case and `name:` matches it exactly.
- [ ] Frontmatter has ONLY `name` and `description`.
- [ ] `description` includes what-it-does + "Use when:" bullets + "Triggers:" comma list.
- [ ] Body is a concise procedure + a short template (≈ 40-120 lines).
- [ ] Long/variant content moved to `references/`, linked from the body, one level deep.
- [ ] No README/scripts/auxiliary docs added.
