# Domain 3: Claude Code Configuration & Workflows – engineering standard

**Exam weight:** 20% (stated on the guide's exam overview page; not stated on the Domain 3 pages themselves).
**Modules:** 3.1 CLAUDE.md Hierarchy, Scoping, and Modular Organisation · 3.2 Custom Slash Commands and Skills · 3.3 Path-Specific Rules for Conditional Convention Loading · 3.4 Plan Mode vs Direct Execution · 3.5 Iterative Refinement Techniques · 3.6 CI/CD Integration.
**Sources (claudecertificationguide.com):** the six Domain 3 module pages (tagged [3.1] to [3.6]), the Domain 3 quick reference [QR], glossary [GL] and exercises page [EX].
**Status of claims:** Technical claims checked against Anthropic's Claude Code docs on 2026-10-14; corrections applied inline. Evidence: `references/verification.md`.

---

## 3.1 CLAUDE.md hierarchy, scoping and modular organisation

**Rules**
1. Put every team-wide convention (naming, error handling, testing requirements, architecture decisions, review checklist) in project-level memory: root `CLAUDE.md` or `.claude/CLAUDE.md`. These are two possible places for the same project level, not two levels; both are version-controlled. The levels, in load order, are managed policy, user (`~/.claude/CLAUDE.md`), project, then local (`./CLAUDE.local.md`). [3.1]
2. Keep `~/.claude/CLAUDE.md` for strictly personal preferences (verbosity, output style, own shortcuts). Never rely on it for anything a teammate or CI run needs, because it never travels through git. [3.1]
3. Use a subdirectory `CLAUDE.md` only for conventions specific to that package or directory (for example `packages/api/CLAUDE.md` for REST rules). [3.1]
4. Use `CLAUDE.local.md` beside a `CLAUDE.md` for personal, repo-specific notes, and add it to `.gitignore` yourself: it is not ignored automatically (unless `/init` with `CLAUDE_CODE_NEW_INIT=1` set adds it when you choose the personal option). Within each directory it is appended after `CLAUDE.md`. If a note in it is really a team rule, move it to `CLAUDE.md`. [3.1]
5. Treat CLAUDE.md as guidance, not enforcement. All applicable files are concatenated; none overrides another; on a contradiction "Claude may pick one arbitrarily". Fix contradictions at the source rather than relying on scope order. [3.1][QR]
6. When a rule must hold on every run (blocked tool, required formatter, permission policy), encode it in `settings.json` or a hook, not in CLAUDE.md. Settings precedence for single-value keys runs: managed settings, then `--settings` on the command line, then `.claude/settings.local.json`, then `.claude/settings.json`, then `~/.claude/settings.json`. List keys such as `permissions.allow` combine across files instead of overriding, and permission rules are evaluated deny, then ask, then allow, so a deny in any scope beats an allow. MCP servers are not a settings key (there is no `mcpServers` in `settings.json`): team servers go in `.mcp.json` at the project root; local-scope (the default) and user-scope servers go in `~/.claude.json`. [3.1][QR][GL]
7. Split a long CLAUDE.md with `@path` imports (`@` followed by a path, which works anywhere in the file, not only on its own line; there is no `@import` keyword). A relative path resolves from the file containing the import, not the working directory; imports nest at most four hops; a space in a path needs a backslash before it; an `@path` inside a code span or fenced code block is ignored. Let each package import only the standards it needs instead of copying them. [3.1]
8. Do not split with `@` imports to save context: imports are inlined eagerly, so total context is unchanged. To cut per-session context, use `.claude/rules/` with `paths:` frontmatter. [3.1]
9. Use `.claude/rules/<topic>.md` files (e.g. `testing.md`, `api-conventions.md`, `deployment.md`) as the alternative to one monolithic CLAUDE.md. A rules file without a `paths` field loads in every session. [3.1]
10. When behaviour differs between sessions or developers, check what actually loaded before changing anything. `/context` lists the CLAUDE.md and rules files loaded at launch under "Memory files"; a subdirectory `CLAUDE.md` loads on demand, never appears there, and shows instead as a `Loaded` line in the terminal when it loads. `/memory` lists memory file locations and opens them; selecting one that does not exist yet creates it. (Guide/exam answer: `/memory`; current: `/context` is the documented check.) [3.1]
11. Do not keep standing instructions only in conversation. After `/compact`, project-root `CLAUDE.md`, unscoped rules and auto memory are re-injected from disk, but nested `CLAUDE.md` files and path-scoped rules return only when a matching file is next touched, and conversation-only instructions may be summarised away. [3.1]
12. When "a new team member gets inconsistent results on the same repo and branch", look first for conventions living in someone's `~/.claude/CLAUDE.md` and move them to project level. [3.1]

**Anti-patterns to catch in review**
- Team conventions documented only in a developer's `~/.claude/CLAUDE.md`, or a README telling people to copy them there.
- A project with no root `CLAUDE.md` and no `.claude/CLAUDE.md`.
- `CLAUDE.local.md` committed, or missing from `.gitignore`; likewise `.claude/worktrees/`, and a hand-made `.claude/settings.local.json` (Claude Code keeps `settings.local.json` out of git only when it creates the file itself).
- `mcpServers` written into `settings.json` (not a settings key; use `.mcp.json` or `~/.claude.json`).
- One CLAUDE.md of several hundred lines with no `@` imports or `.claude/rules/` split.
- The same conventions duplicated across several directory-level `CLAUDE.md` files instead of one shared `@` import or one rules file.
- Contradictory instructions between user, project and directory files (relying on "the more specific one wins").
- "MUST/NEVER" safety rules (no `rm`, always run formatter, never touch prod) stated only in CLAUDE.md with no matching `permissions` rule or hook.
- `@import` written as a keyword, or an `@path` import placed inside backticks or a code fence (it is ignored there).

**Exam answer vs current practice**
- Seeing which memory files loaded: (Guide/exam answer, guide v1.0: `/memory`; current: `/context` shows the files loaded at launch under "Memory files", while `/memory` lists locations, including entries for files that do not exist yet, and opens or creates them.) [3.1]
- Levels: (Guide/QR: three levels in load order, `~/.claude/CLAUDE.md`, then `.claude/CLAUDE.md`, then `CLAUDE.md`; current: managed policy, user, project, local, where `./CLAUDE.md` and `./.claude/CLAUDE.md` are two places for the one project level.) [QR]
- Precedence: the guide says distractors "more specific scope wins" and "user-level overrides project-level" are wrong; CLAUDE.md is a load order, not a precedence chain. The quick reference nonetheless uses "priority" wording for rules; the docs do too, saying unscoped rules load "with the same priority as `.claude/CLAUDE.md`". [3.1][QR]

## 3.2 Custom slash commands and skills

**Rules**
1. Create new reusable workflows as skills: a directory with a `SKILL.md` entrypoint, `.claude/skills/<name>/SKILL.md`, which creates `/<name>`. Treat `.claude/commands/<name>.md` (flat file) as the older format, which still works. [3.2]
2. Never drop a flat `.md` file directly into `.claude/skills/`; it creates no command. (Inferred: the docs describe only the `<name>/SKILL.md` directory layout and never mention flat files there.) [3.2]
3. Put team workflows (`/team-review`, `/deploy-check`, `/lint`, `/migration-guide`) in project scope (`.claude/skills/` or `.claude/commands/`) so every clone gets them. Avoid names of built-in commands and their aliases (for example `/review` is an alias of the bundled `/code-review`), so it is always clear which one runs. Put personal workflows in `~/.claude/skills/` (or `~/.claude/commands/`). [3.2]
4. Give a personal variant of a team skill a different name (e.g. `/deep-analyse` beside team `/analyse`) so it neither overrides nor conflicts. [3.2]
5. Always write a specific `description` in skill frontmatter; without one Claude falls back to the first non-empty line of the body. [3.2]
6. Set `context: fork` on any skill that produces verbose, exploratory output (codebase analysis, brainstorming) so the output stays in an isolated subagent and only the subagent's result returns. The forked subagent does not see the conversation. Since v2.1.218 it runs in the background by default, with the narrower background tool set; set `background: false` to wait for the result and keep the full tool set. `-p` runs always wait. [3.2]
7. Use `allowed-tools` to pre-approve the tools a trusted workflow needs. It does not restrict anything: every tool remains callable, and the grant clears when the user sends their next message. `disallowed-tools` removes tools, but also only until the user's next message, so it is not a lasting restriction either. For a lasting restriction use permission `deny` rules, or run the work in a subagent limited by its `tools`/`disallowedTools`. A read-only analysis skill should pre-approve only read tools: Read, plus Grep and Glob where they exist (on macOS, Linux and WSL they are absent by default and searches run as Bash `find`/`grep`). [3.2][QR][GL]
8. Use `argument-hint` to show expected arguments at autocomplete; it is only a hint and does not prompt for missing arguments. [3.2]
9. Set `disable-model-invocation: true` on skills that must only run when a user types them. Without it, Claude can load a skill automatically when it judges it relevant. [3.2]
10. Keep task-specific procedures out of CLAUDE.md and always-on reference material out of skills. Conventions every edit must follow go in CLAUDE.md or `.claude/rules/`. [3.2]
11. Apply least privilege: each skill or agent gets only the tools it needs. [QR]

**Anti-patterns to catch in review**
- `.claude/skills/*.md` flat files (dead commands; inferred, see rule 2).
- Skills with no `description`, or a vague one.
- Verbose analysis or brainstorming skills without `context: fork`.
- Read-only skills whose `allowed-tools` include Write or Edit, or Bash beyond read-only search commands (on macOS, Linux and WSL, Grep and Glob are absent by default and searches run as Bash `find`/`grep`), or that rely on `allowed-tools` or `disallowed-tools` as a security boundary (both clear at the user's next message) with no permission deny rules or subagent `tools` limit.
- Team commands kept only in `~/.claude/commands/` or `~/.claude/skills/`.
- Multi-step procedures (review routine, release checklist) pasted into CLAUDE.md.
- Always-needed conventions hidden inside a skill.
- A skill and command with the same name (the skill wins).

**Exam answer vs current practice**
- `allowed-tools`: (Guide/exam answer: "restricts the skill's tool access"; current: pre-approves the listed tools for one turn, "The grant clears when you send your next message", and "does not restrict which tools are available".) [3.2][QR]
- `argument-hint`: (Guide/exam answer: "prompts developers for required parameters when invoked without arguments"; current: "Hint shown during autocomplete to indicate expected arguments.") [3.2]
- Frontmatter scope: exam names three fields (`context: fork`, `allowed-tools`, `argument-hint`); current docs also list `description` (Recommended), `disallowed-tools`, `disable-model-invocation`, `model`, `effort`, `when_to_use`, `paths`, `name`, `arguments`, `user-invocable`, `agent`, `background`, `hooks`, `shell`, `metadata`, `license` and `compatibility`. `allowed-tools` accepts a space- or comma-separated string or a YAML list. [3.2]
- Invocation: (Guide Concept Check: skills "must be explicitly invoked"; current: "Claude uses skills when relevant, or you can invoke one directly with `/skill-name`"; only `disable-model-invocation: true` stops automatic use. The lesson body agrees with current practice.) [3.2]

## 3.3 Path-specific rules

**Rules**
1. When a convention applies to one file type spread across many directories (co-located tests, Terraform, route handlers), write one `.claude/rules/<topic>.md` with `paths:` glob frontmatter. Choose this over a CLAUDE.md in every directory (duplication, drift) and over root CLAUDE.md (wasted tokens on unrelated work). [3.3]
2. Write globs that match wherever the files sit, as a YAML block list: `paths:` and then one `  - "glob"` line each for `**/*.test.ts`, `**/*.test.tsx`, `**/*.spec.ts` and `**/*.spec.tsx`. A comma-separated string also works. Do not rely on the inline `[...]` form, which no doc example uses. If the YAML fails to parse, Claude Code ignores the frontmatter and the rule silently loads in every session. [3.3]
3. Keep root `CLAUDE.md` for universal standards; directory `CLAUDE.md` for one package; path rules for file types; skills for on-demand workflows. [3.3]
4. Choose path rules over a `paths`-scoped skill for conventions that must shape every edit, because rules stay in context as background guidance while skills load as task-style workflows. [3.3]
5. Verify scoping by reading or editing a matching and a non-matching file and checking what loaded. `/context` lists only files loaded at launch. When a path-scoped rule (or an on-demand subdirectory `CLAUDE.md`) loads, the terminal shows a one-line `Loaded <path>` notice, but not the rule content. To log loads, use an `InstructionsLoaded` hook, which fires with `load_reason` `path_glob_match` for a path-scoped rule. [3.3]

**Anti-patterns to catch in review**
- Test, IaC or API conventions in root CLAUDE.md.
- Identical `CLAUDE.md` copies in many directories.
- Rules files intended to be scoped but with no `paths:` frontmatter, or with `paths:` YAML that fails to parse (either way they load every session).
- Conventions packaged as a skill that developers must remember to run before editing.

**Exam answer vs current practice**
- `paths` format: (Guide: an inline array, `paths: ["terraform/**/*"]` [3.3], and a YAML list [QR]; current: the docs accept "a YAML list or a comma-separated string", and every doc example uses the block list. The inline `[...]` form is YAML flow syntax and should parse, but no doc shows it, so use the block list.)

## 3.4 Plan mode vs direct execution

**Rules**
1. Choose the mode by ambiguity, not difficulty. [3.4]
2. Use plan mode up front for large-scale or architectural change, multiple valid approaches, multi-file changes (e.g. a migration across 30 or 45+ files; the Concept Check notes say 10+ files with multiple valid approaches) or necessary codebase exploration. When the requirements already state the complexity, do not start direct and switch later. [3.4]
3. Use direct execution when the problem, location and fix are known: a single-file bug with a clear stack trace, one validation check, a config value. [3.4]
4. For migrations and refactors, plan then execute: plan to map files, API differences and edge cases; then implement file by file to the agreed pattern. [3.4]
5. Enter plan mode with a real mechanism: Shift+Tab, a `/plan` prefix, `claude --permission-mode plan`, or `"permissions": {"defaultMode": "plan"}` in settings. Writing "in plan mode" in a prompt does not switch the mode (guide wording). [3.4]
6. Delegate verbose discovery to the Explore subagent so only summaries reach the main context. The built-in Explore and Plan subagents start without CLAUDE.md (a subdirectory CLAUDE.md and matching path-scoped rules still load on demand when they work with files there). Subagents are spawned with the Agent tool. (Guide glossary: "the Task tool"; current: renamed to Agent in v2.1.63. `Task(...)` still works as an alias in settings and agent definitions; write `Agent(...)` in new permission rules.) [3.4][GL]

**Anti-patterns to catch in review**
- Session logs or runbooks that jump straight into multi-file architectural edits with no plan.
- Planning ceremony for one-line fixes.
- Prompts that say "in plan mode" as text.
- Large exploration dumps pasted into the main conversation.

**Exam answer vs current practice**
- None stated. Practice answer: plan mode for monolith restructure and 30-file logging migration; direct for a null-pointer fix with a stack trace. [3.4]

## 3.5 Iterative refinement

**Rules**
1. When Claude interprets a prose instruction inconsistently, give a few concrete input/output examples (the guide says 2–3: a standard case plus a key edge case; Anthropic's few-shot guidance is 3–5) before rewriting the prose. [3.5]
2. For complex transformations with many edge cases, write tests first (happy path, edge cases, performance if relevant) and feed back the failing output ("Expected X, got Y"). [3.5]
3. In an unfamiliar domain, ask Claude to question you about requirements, edge cases and constraints before implementing (interview pattern). Do not use it to fix inconsistent interpretation. [3.5]
4. Send interacting fixes in one message; send independent fixes one at a time. [3.5]
5. After switching to examples, test on a new case to confirm the pattern generalises. [3.5]
6. Calibrate review severity with examples of critical issues versus style nits. [QR]

**Anti-patterns to catch in review**
- Repeated prose re-wording in prompts or skill bodies where examples would settle it.
- Complex transformation skills with no example pairs or tests.
- Feedback bundles mixing unrelated issues; or interdependent fixes split across turns.

**Exam answer vs current practice**
- None stated. Practice answer: examples first; tests are "heavier than necessary as a first step". [3.5]

## 3.6 CI/CD integration

**Rules**
1. Always run Claude Code in CI with `-p` / `--print`. Without it the job starts an interactive session (guide: it hangs waiting for input). `CLAUDE_HEADLESS=true` and `--batch` do not exist; redirecting stdin is not the fix. [3.6]
2. When output feeds automation, use `--output-format json` with `--json-schema`, and read results from the envelope's `structured_output` field (`jq '.structured_output'`). [3.6]
3. Review generated code in a separate invocation with no shared session context; never in the session that wrote it. [3.6][QR]
4. On repeat reviews, pass prior findings and ask only for new or still-unaddressed issues, excluding ones the developer reviewed and chose not to act on. [3.6]
5. Put CI-relevant context in CLAUDE.md: testing standards, fixtures and their paths, review severity criteria, existing coverage. Include existing tests in context for test generation. [3.6]
6. To add rules but keep Claude Code's default behaviour, use `--append-system-prompt` (or `-file`); use `--system-prompt` only when you will own everything the task needs. [3.6]
7. Scope tools and permissions explicitly in unattended runs. Always pass `--permission-mode`: a `-p` run with no mode set can start in `auto` (Claude Code v2.1.285 or later, in sessions that don't fetch feature flags, for example with a third-party provider or telemetry off). The documented CI pattern is `claude -p "..." --permission-mode dontAsk --allowedTools "..."`. In a `-p` run with no permission host, anything that would prompt is denied, not prompted; `dontAsk` denies every call that would otherwise prompt. An allowlist (`--allowedTools` or `permissions.allow`) is the tighter default; use `--disallowedTools`/`--tools` to remove tools; cap with `--max-turns`. [3.6][GL]
8. Use `--bare` for fast, predictable scripted runs that do not need project config; do not use it when CLAUDE.md, hooks or skills must apply. It skips auto-discovery of hooks, skills, custom commands, subagents, installed plugins, MCP servers, auto memory and CLAUDE.md, leaving Bash and the file read and edit tools; skills in a directory passed with `--add-dir` still load, but Claude is not given the skill list, so invoke them by name. It does not use subscription login (OAuth or keychain), so on the Anthropic API it needs `ANTHROPIC_API_KEY` or an `apiKeyHelper` (Amazon Bedrock, Google Cloud's Agent Platform and Microsoft Foundry use their own provider credentials as usual). It is planned to become the default for `-p` in a future release. [3.6]
9. In GitHub Actions, use `anthropics/claude-code-action@v1`, pass CLI flags via `claude_args`, check out the repo first when Claude must read repo files or run repo skills (a job that works only through the GitHub API can omit it), keep the credential in a repository secret, and set a minimal `permissions` block. [3.6, beyond the guide]
10. Run parallel sessions in separate git worktrees; coordinate shared files by sequencing (first merges, second rebases), not locking. `claude --worktree <name>` creates `.claude/worktrees/<name>/` on a new branch `worktree-<name>`; add `.claude/worktrees/` to `.gitignore` (the docs now recommend this). [3.6, beyond the guide]
11. Use real-time calls for blocking pre-merge checks; use the Message Batches API (50% cheaper, up to 24 h, no latency SLA) only for overnight or weekly non-blocking jobs. [3.6]

**Anti-patterns to catch in review**
- `claude "..."` without `-p` in any CI script.
- Parsing human-readable text output, or reading schema output from the JSON top level instead of `structured_output`.
- One job that generates and then reviews in the same session.
- Review jobs with no memory of earlier findings (same comments every push).
- `--system-prompt` used just to add review criteria.
- No `--allowedTools`/`--max-turns` in unattended jobs, or no explicit `--permission-mode`.
- API keys as literals in workflow YAML; missing `actions/checkout` in a job that reads repo files or runs repo skills; broad workflow `permissions`.
- Batch API behind a required pre-merge check.
- `--bare` in a job that expects CLAUDE.md standards to apply, or that calls the Anthropic API with no `ANTHROPIC_API_KEY` or `apiKeyHelper`.

**Exam answer vs current practice**
- GitHub Actions and worktrees are not in Task Statement 3.6, but readers report 4–5 exam questions on Actions and the practice bank tests worktrees. [3.6]
- Pre-v1 action inputs map to v1: `custom_instructions` → `--append-system-prompt`, `direct_prompt` → `prompt`, `mode` removed. [3.6]

---

## Decision rules

| Situation | Choose | Over | Why |
|---|---|---|---|
| Team convention for all code | Project `CLAUDE.md` / `.claude/CLAUDE.md` (one level, either place) | `~/.claude/CLAUDE.md` | User level is not shared via git [3.1] |
| Personal preference | `~/.claude/` or `CLAUDE.local.md` | Project files | Keeps teammates unaffected [3.1][3.2] |
| Rule must always hold | `settings.json` permissions or hook | CLAUDE.md wording | CLAUDE.md is guidance; settings and hooks are enforced [3.1][QR] |
| "Guaranteed enforcement, cannot be bypassed" | PreToolUse `command` hook to block (exit 2); PostToolUse hook for follow-up such as a formatter | Prompt instruction | Command hooks are deterministic code (`prompt` and `agent` hooks are judged by a model); PostToolUse cannot undo or block a call that already ran [QR] |
| Style guidance, preferred approach | CLAUDE.md | Hook | Probabilistic guidance is enough [QR] |
| Convention for one file type across many dirs | `.claude/rules/` + `paths:` | Per-directory CLAUDE.md; root CLAUDE.md | No duplication; loads only when relevant [3.3] |
| Convention for one package | Directory `CLAUDE.md` | Root CLAUDE.md | Scoped to that directory [3.3] |
| Long CLAUDE.md, want cleaner source | `@path` imports | One file | Modular; same context size [3.1] |
| Long CLAUDE.md, want less context | Path-scoped rules | `@` imports | Imports load eagerly [3.1] |
| Reusable on-demand workflow | Skill `.claude/skills/<n>/SKILL.md` | CLAUDE.md procedure | Full content loads only when invoked by the user or picked by Claude as relevant [3.2] |
| "Prompt template with arguments" | Skill (takes `$ARGUMENTS`) | Command in `.claude/commands/` | (Guide/exam answer: the command; current: commands are the older format, skills take `$ARGUMENTS` too, and a skill wins over a command of the same name) [QR][3.2] |
| Verbose skill output | `context: fork` | Inline skill | Keeps main context clean [3.2] |
| Hard tool restriction for a skill | Permission `deny` rules, or a subagent's `tools`/`disallowedTools` | `allowed-tools`; `disallowed-tools` | `allowed-tools` only pre-approves; both skill fields clear at the user's next message [3.2] |
| Ambiguous, multi-approach, multi-file task | Plan mode, then direct | Direct first | Complexity is known up front [3.4] |
| Known fix, known place | Direct execution | Plan mode | Planning adds nothing [3.4] |
| Verbose codebase discovery | Explore subagent | Main conversation | Summaries only [3.4] |
| Inconsistent interpretation | A few input/output examples (guide: 2–3; Anthropic few-shot: 3–5) | Better prose; tests; interview | Removes interpretation [3.5] |
| Complex transformation, many edge cases | Test-driven iteration | Prose feedback | Failures are unambiguous [3.5] |
| Unfamiliar domain | Interview pattern | Prescribing a solution | Surfaces missed considerations [3.5] |
| Interacting fixes / independent fixes | One message / sequential | The reverse | [3.5] |
| CI, automated, non-interactive | `claude -p` | `CLAUDE_HEADLESS`, `--batch`, stdin redirect | Only documented method [3.6] |
| Machine-parseable CI output | `--output-format json` + `--json-schema` | Text output | Validated `structured_output` [3.6] |
| Extra rules, keep defaults | `--append-system-prompt` | `--system-prompt` | Keeps tool and safety guidance [3.6] |
| Fast scripted run, no project config | `--bare` (on the Anthropic API: `ANTHROPIC_API_KEY` or `apiKeyHelper`) | Normal run | Skips discovery; no subscription login [3.6] |
| Reviewing generated code | Independent session | Same session | Self-review bias [3.6] |
| Repeat PR reviews | Prior findings in context | Fresh scan | Avoids duplicate comments [3.6] |
| Blocking pre-merge check | Real-time API | Batch API | No latency SLA on batch [3.6] |
| Unattended pipeline permissions | `--permission-mode dontAsk` + `--allowedTools` allowlist | Denylist; no explicit mode | Tighter default; anything not allowed is denied, not prompted [GL][3.6] |
| Team MCP servers | `.mcp.json` at project root | `mcpServers` in `settings.json` | Not a settings key [GL] |

---
