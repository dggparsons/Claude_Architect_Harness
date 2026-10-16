---
name: claude-eng-audit
description: Audit an existing project against the Claude engineering standards - its Claude Code setup (CLAUDE.md, rules, skills, agents, settings, hooks, MCP, CI), any code that calls Claude or another LLM, and its working practice (plan, review records, secrets) - then write findings in the review-table format and propose an improvement plan. Changes nothing until the user approves.
argument-hint: "[project-path]"
disable-model-invocation: true
---
# Claude engineering audit

Target: `$ARGUMENTS` (if empty, the current working directory). Confirm the resolved absolute path with the user in your first message, then continue.

**Ground rules**
- This is an audit. Do not change any project file except the audit report you write in step 5. Fixes come after the user approves (step 7).
- Every finding quotes the exact text or names the exact `file:line`. A finding with no evidence is not a finding.
- If a check cannot run (no access, tool missing), record it as "not run" with the reason, never as a pass.
- If the project's own rules require an edit during reviews (for example "update the tracker in the same turn"), do not make it during the audit: put the exact rows or text in the report, log it as a decision, and apply it in step 7 once the user approves (and once no other session has unsaved edits to that file).
- Standards: `${CLAUDE_SKILL_DIR}/../../rules/claude-engineering.md`, `${CLAUDE_SKILL_DIR}/../../rules/claude-code-config.md` (read it now if it is not in context), the `claude-engineering` skill and its references (`${CLAUDE_SKILL_DIR}/../claude-engineering/references/`), including the working practice `${CLAUDE_SKILL_DIR}/../claude-engineering/references/working-practice.md` (the plan template, review loop and severity scale; where the user's own `~/.claude/CLAUDE.md` defines these, it wins). Read the parts relevant to what you find.

## 1. Find the plan and context
Look for `PLAN.md`, a `_project/` folder, a README status list, and an existing review folder (`_project/review/`, `docs/reviews/`, `qa/`, `review/`). Use what exists; never start a second plan. Note what the project delivers (course, assessment, tool, app) and who uses it.

## 2. Inventory (delegate if the project is large)
For a project with more than about 50 files, send the inventory to an Explore subagent with a self-contained brief and ask for a structured list back. Collect:
- **Claude config anywhere in the project**, not only under `.claude/`: every `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md` (with line counts), `SKILL.md`; every file in a `.claude/rules/` or `.claude/agents/` folder; any other folder whose files the project installs into a `.claude` directory (for example `harness/rules/`, `harness/agents/`), with or without frontmatter; `settings*.json` with `permissions` or `hooks`; `.mcp.json`.
- `.gitignore` entries for `CLAUDE.local.md`, `.claude/settings.local.json`, `.claude/worktrees/` (git repositories only).
- CI workflows that run Claude (`claude -p`, `claude-code-action`).
- **Code that calls an LLM:** search source files only (`*.py`, `*.ts`, `*.tsx`, `*.js`, `*.mjs`, `*.go`, `*.java`, `*.cs`, `*.rb`, `*.php`, `*.sh`, `*.ps1`), skipping `node_modules`, virtual environments, build output and vendored code, for: `import anthropic`, `from anthropic`, `@anthropic-ai/`, `messages.create`, `tool_choice`, `local_ai`, `openai`, `claude_agent_sdk`, `@anthropic-ai/claude-agent-sdk`. List each hit with `file:line`. Then find the prompts and schemas that code uses.
- **Secrets:** run the tested scanner that ships with this skill: `python -I "${CLAUDE_SKILL_DIR}/scripts/secrets_scan.py" "<project path>"`. It reads every file, including gitignored ones (Claude's Grep tool skips those, even when git still tracks them), always scans files git tracks even inside skipped folders, scans the staged copy of any tracked file whose content differs from the working tree (marked STAGED), and handles nested repositories. It skips `node_modules`, real virtual environments and tool caches, listing each as SKIPDIR with a count of the untracked files it did not scan (and any sensitive file names inside). Its docstring lists exactly what it recognises: key formats, credentials in URLs and auth headers, credential assignments, command-line passwords (`--password`, `-Password`, `ConvertTo-SecureString`, `-p` after `-u`/`-l` or in `sshpass`, `/p:`, `curl -u user:pass`, `[domain/]user:pass@host`), and loot (NTLM in secretsdump form, `user:NThash`, DCC2, NetNTLMv2, Kerberos roasts, Unix crypt, bcrypt, Argon2, cracked `hash:password` potfile lines, `.netrc`). Anything else, including credentials written as free text and older commits, is not recognised. It never prints a value or the source line: each finding gives the file, line and column, what kind of secret it looks like (with the variable name for assignments), its length and its git status. Judge each finding from that and from the file's path and purpose. Never Read, Grep, cat or otherwise print a flagged file or line to confirm a hit: that puts the secret into the transcript. If that is not enough to judge, record the finding as needing the user's check. A real key in a file git tracks or has staged is High (rotate it and remove it from history); fake keys in documentation, tests or fixtures are not findings. A SKIPPED item or a SKIPDIR folder was not checked: ask the user how to check it (for SKIPDIR, whether it holds only third-party packages), or record C7 as "not run" for it. The scanner exits 1 whenever anything was not scanned. Exit code 2 means the scan did not run: record "not run".

## 3. Check against the standards
Mark every check pass, fail (with a finding), not applicable, or not run. Skip a whole area only if it does not apply, and say why.

**A. Claude Code setup** (standard: `claude-code-config.md`)
- A1 A project `CLAUDE.md` (or `.claude/CLAUDE.md`) exists, says what the project is, how to build and test it, and its conventions; under about 200 lines.
- A2 Project-specific conventions live in the project, not only in `~/.claude/`. (General working standards that come from `~/.claude/` by design are fine; for a project other people will clone or receive, every convention they need must be in the repo.)
- A3 No contradictions between the project's memory files, or between them and `~/.claude/CLAUDE.md`; no multi-step procedures in the project's CLAUDE.md (they belong in skills). Do not audit `~/.claude/CLAUDE.md` itself unless asked.
- A4 File-type conventions sit in `.claude/rules/` with `paths:` (valid YAML), not copied into several directory CLAUDE.md files.
- A5 Skills are `<name>/SKILL.md` directories with a clear `description`; side-effect skills have `disable-model-invocation: true`; no duplicate skill/command names; `allowed-tools` is not relied on as a restriction.
- A6 Agents have least-privilege `tools`; reviewers cannot edit files (no Edit/Write/NotebookEdit), and any that can run commands say so in their description.
- A7 Must-hold rules (secrets, destructive commands, required checks) are backed by `settings.json` permissions or hooks, not only by prose. Hook scripts exist, are referenced through the project-directory placeholder (a `$` sign followed immediately by `{CLAUDE_PROJECT_DIR}`; not an absolute path) in exec form with `args`, or quoted in shell form, and, on reading them, block by exiting 2 or by printing JSON `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}` (the docs define `permissionDecision` inside `hookSpecificOutput`; a hook that prints it anywhere else fails the behaviour test). Running a hook runs the project's own code, which an audit must not do unasked: only with the user's approval, run `python -I ${CLAUDE_SKILL_DIR}/../claude-eng-setup/scripts/test_hook.py --project "<temporary copy of the project>" --event-json '<sample event>' --expect block|ask|allow|feedback|stop` against a temporary copy, with a block case and an allow case for each `PreToolUse` guard, and record the output as evidence. The script covers `command` hooks on `PreToolUse` and `PostToolUse` only and reports NOT RUN for anything it does not model (other events, `if` conditions, other handler types, `disableAllHooks` in another settings file); those are reviewed by reading them or tested live. Without approval, record the behaviour test as "not run".
- A8 `.mcp.json`: no literal secrets; every server has a valid shape; credentials via `${VAR}` in `headers` (remote) or `env` (local); variables documented.
- A9 `CLAUDE.local.md`, `.claude/settings.local.json` and `.claude/worktrees/` are gitignored.
- A10 CI: `-p` with an explicit `--permission-mode`, JSON or schema output, explicit tool allowlist, turn cap, secrets from the secret store, review run separately from generation.

**B. LLM-powered code** (standard: `claude-engineering` SKILL.md checklists; cite the module tag)
- B1 Agent loop ends on `stop_reason`, handles every value including `refusal` and `max_tokens`, appends tool results; any iteration cap is a logged safety net.
- B2 Orchestration: coordinator owns delegation and aggregation; subagent briefs are self-contained; tool sets are focused.
- B3 Tool definitions: rich descriptions, clear names, `enum`s, minimal `required`.
- B4 Tool errors are structured; empty success is distinct from failure; no swallowed exceptions.
- B5 `tool_choice` usage is valid for the model in use (no forced choice on models that reject it).
- B6 Structured output: `strict: true` or `output_config.format` where available; nullable fields as type arrays; `stop_reason` checked before parsing.
- B7 Semantic validation in code; retries carry the specific error; retry cap; "absent from source" goes to review, not retry.
- B8 Batch use (if any): latency-tolerant work only, `custom_id` join, all result types handled, failures resubmitted.
- B9 Caching and context: stable prefix first; facts kept verbatim; verbose tool output trimmed in code.
- B10 Escalation: explicit triggers in code or prompt with a handoff format; never on sentiment or self-rated confidence.
- B11 Human review and confidence: thresholds calibrated on labelled data; accuracy measured per segment.
- B12 Provenance: claims keep source and date through synthesis; conflicts shown, not resolved silently.
- B13 Calls to a local or self-hosted model behind a queue (if any): follow that service's rules for concurrency, timeouts and back-off on busy replies; key from an environment variable or an untracked file; output schema-checked.

**C. Working practice** (standard: `${CLAUDE_SKILL_DIR}/../claude-engineering/references/working-practice.md`, or the user's own `~/.claude/CLAUDE.md` where it defines its own)
- C1 A plan exists, uses the template's sections, and its statuses match reality (spot-check three tasks against the files).
- C2 Tasks have testable done-when checks.
- C3 Decisions only the user can make are logged with a recommended default.
- C4 A review folder exists with one findings table per round and a response log of what was applied, what was not, and why.
- C5 Outputs (documents, decks, audio, packages) are built from source by script and can be rebuilt.
- C6 No placeholders (TODO, TBC, dummy text) outside logged decisions.
- C7 No secrets in tracked files (the secrets scan in step 2 finds no real key and no tracked sensitive file); keys only in environment variables or untracked local files.
- C8 UK English unless the project says otherwise.
- C9 For deliverables (courses, assessments, reports, tools): an end-user walkthrough has been recorded, and sources are cited for factual claims.

## 4. Independent review of your findings
Before writing the report, brief the `reviewer-standards` agent (and `reviewer-facts` for any claim about Claude or API behaviour) with a self-contained brief: project path, the standards files, your findings with evidence. Ask each to confirm, reject or re-grade every finding and to list anything missed. Apply their verdicts; where you disagree, say why in the report.

## 5. Write the report
Write `<review-folder>/claude-eng-audit-<YYYY-MM-DD>.md` (create `_project/review/` if there is no review folder; if that file already exists, add `-2`, `-3` and so on rather than overwriting it). Contents:
- **Summary:** three to five plain sentences: overall state, the biggest risks, the quickest wins.
- **Scorecard:** per area (A, B, C): passed / failed / not applicable / not run, with the check IDs.
- **Findings table:** `# | Severity | File:line | Problem | Evidence | Fix | Status` (the same columns the reviewer agents use; Evidence is the quoted text, command output or doc link that proves the finding), ordered High, Medium, Low. Severity as in the working practice (section 3): High = wrong, broken, unsafe or misleading, would embarrass the user in front of a customer, or fails a done-when check; Medium = confusing, inconsistent between files, or makes the next person's job harder; Low = cosmetic. Status starts as `open`.
- **Improvement plan:** the fixes grouped into small tasks, each with a testable done-when check, ready to paste into the project's plan.
- **Decisions for the user:** anything only they can decide, each with a recommended default.

## 6. Report to the user
Lead with the outcome in plain sentences, then the top findings, then the numbered decisions with your recommendation. Link the report file. Do not paste the whole table.

## 7. Fix, only after approval
When the user approves some or all fixes, run each as a task through the review loop in the working practice (section 2): fix the source at the root cause, search for the same problem elsewhere, then have an independent reviewer re-check what changed. Record each round in the review folder, update the Status column and the response log, and keep the project plan current.
