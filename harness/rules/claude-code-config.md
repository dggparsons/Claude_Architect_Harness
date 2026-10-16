---
paths:
  - "CLAUDE.md"
  - "CLAUDE.local.md"
  - "AGENTS.md"
  - "**/AGENTS.md"
  - "**/CLAUDE.md"
  - "**/CLAUDE.local.md"
  - "**/.claude/**"
  - "**/.mcp.json"
  - ".mcp.json"
  - "**/SKILL.md"
---
# Writing Claude Code configuration
Loaded because you are reading or editing Claude Code config. Facts come from Anthropic's Claude Code docs (checked 2026-10-14); items marked *(practice)* are recommended practice from the certification guide rather than documented behaviour. Detail and doc URLs: `references/claude-code-current-spec.md` and `references/verification.md` in the `claude-engineering` skill. Where the guide's exam answer differs from current behaviour, build to current behaviour.

## Memory files
- Levels, loaded broadest first: managed, user `~/.claude/CLAUDE.md`, project (`./CLAUDE.md` or `./.claude/CLAUDE.md`, two places for the same level), local `./CLAUDE.local.md`. Subdirectory `CLAUDE.md` files load when Claude touches files there. Claude can also read a repo's `AGENTS.md`; see the memory docs for how it interacts with `CLAUDE.md` and `CLAUDE.local.md`.
- All applicable files are concatenated, not overridden. If two instructions conflict, Claude may follow either. Remove contradictions rather than relying on order.
- Target under 200 lines per CLAUDE.md. `@path` imports (allowed anywhere in the file; relative to the importing file; at most four hops; ignored inside code spans and fences) organise a file but do not save context, because they load at launch. To save context, move part-of-the-codebase conventions to `.claude/rules/*.md` with `paths:`.
- `paths:` is the only frontmatter field a rules file reads; use a YAML block list or a comma-separated string. A rule without it, or with YAML that fails to parse, loads in every session.
- Team conventions must live in the repo (project CLAUDE.md or `.claude/rules/`), never only in someone's `~/.claude/`. A new teammate who clones the repo must get them.
- CLAUDE.md does not enforce anything. Must-hold rules go in `.claude/settings.json` permissions (deny, then ask, then allow; first match wins) or in hooks.
- `/context` lists the memory files loaded at launch (a subdirectory CLAUDE.md loaded later shows as a separate `Loaded` line). `/memory` lists and opens memory files, and can create one.
- After `/compact`, the project-root CLAUDE.md, unscoped rules and auto memory are re-injected; nested CLAUDE.md files and path-scoped rules return only when a matching file is touched again.

## Skills and commands
- A skill is a directory: `.claude/skills/<name>/SKILL.md` (project) or `~/.claude/skills/<name>/SKILL.md` (personal). `.claude/commands/<name>.md` still works but is the older format; prefer skills. On a name clash the skill wins.
- `description` decides when Claude auto-loads the skill (if omitted, the first non-empty body line is used). Put the main use case first; description plus `when_to_use` is cut at 1,536 characters.
- `disable-model-invocation: true` = manual `/name` only (use for anything with side effects). `user-invocable: false` = background knowledge only Claude loads.
- `allowed-tools` pre-approves tools and `disallowed-tools` removes them, and both last only until the user's next message. For a lasting restriction use permission deny rules, or a subagent's `tools`/`disallowedTools`.
- `context: fork` (with optional `agent:`) runs the skill in a subagent that does not see the conversation. It runs in the background by default with fewer tools; set `background: false` to wait for it with all tools.
- Keep `SKILL.md` under 500 lines; move reference material to supporting files that SKILL.md names and describes, so they load only when needed.
- Multi-step procedures belong in skills; always-on conventions belong in CLAUDE.md or rules.

## Subagents
- Files in `.claude/agents/` or `~/.claude/agents/` with frontmatter `name` and `description` (required). Common optional fields: `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory`, `background`, `effort`, `isolation: worktree`, `omitClaudeMd` (full list in the sub-agents docs).
- Give each agent the smallest tool set its role needs; reviewers that only read get no Edit/Write/Bash.
- A new subagent starts fresh: it gets the CLAUDE.md hierarchy (except Explore, Plan and agents with `omitClaudeMd`) but not the conversation (only a fork inherits it). `skills:` preloads skills in full; unlisted skills can still be invoked through the Skill tool.
- In permission rules use `Agent(...)`; `Task(...)` is an old alias.

## Hooks and settings
- Settings precedence: managed > command-line `--settings` > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`. Lists such as `permissions.allow` combine across files. `mcpServers` is not a settings key.
- Hooks: `hooks -> event -> [{matcher, hooks: [{type: "command", command, timeout}]}]`. Handler types: command, http, mcp_tool, prompt, agent. Exit 0 = continue; exit 2 = block (stderr is the reason) on events that can block; other codes = non-blocking error. Hooks can also live in plugins and in skill or subagent frontmatter.
- Use `PreToolUse` to block or gate actions (a deny holds even in `bypassPermissions` mode). Use `PostToolUse` to format, normalise, redact or log: it runs after the side effect, a `block` there only adds feedback and Claude carries on (only `"continue": false` halts), and `updatedToolOutput` can replace what Claude sees. Use `${CLAUDE_PROJECT_DIR}` in hook command paths.
- Know the gaps: typing `/skillname` skips `PreToolUse`; a file changed through Bash does not trigger an `Edit|Write` matcher; `prompt` and `agent` hook types are judged by a model, not deterministic code.
- Prefer exec form for script hooks, as the docs recommend whenever a hook references a path: `{"type": "command", "command": "python", "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py"]}`. No shell is involved, placeholders are substituted as plain text, and paths with spaces need no quoting; on Windows `command` must be a real executable, not a `.cmd` shim, and not `bash` (on the PATH it can be the WSL launcher). Shell form (no `args`) runs under `sh -c` on macOS and Linux and Git Bash on Windows (PowerShell if Git Bash is missing, or with `"shell": "powershell"`); there, quote placeholders. A hook whose script cannot be found usually fails with a non-blocking "hook error" notice and the action goes ahead, but Python exits 2 when it cannot open its script, which blocks every call.
- A blocking `PreToolUse` hook exits 2 with a reason on stderr, or exits 0 and prints JSON with `hookSpecificOutput.permissionDecision: "deny"`. Other events have their own blocking rules (exit 2 is not honoured on every event); check the hooks docs for the event. Test `PreToolUse` and `PostToolUse` hooks with `~/.claude/skills/claude-eng-setup/scripts/test_hook.py`; test hooks on other events live.
- Bash permission rules match command text, so they are not a security boundary (`curl` can be reached by path or inside `sh -c`). For enforcement that does not depend on the command text, use the sandbox, which runs on macOS, Linux and WSL2 only: on native Windows commands run unsandboxed. Where the sandbox cannot start, Claude Code runs commands unsandboxed unless `sandbox.failIfUnavailable` is `true`, and Claude can retry a failed command outside the sandbox unless `sandbox.allowUnsandboxedCommands` is `false`. A `PreToolUse` hook can inspect the full command with your own logic, but it still works on the text. Read/Edit deny rules also cover file commands Claude Code recognises in Bash (`cat`, `head`, `tail`, `sed`, `tee`), but not commands that read without naming the file (`grep -r` in that folder) or scripts that open files themselves (Python, Node).

## MCP
- Team servers go in project `.mcp.json` (committed). Personal ones go in `~/.claude.json`: local scope (the default, this project only) or user scope (all projects).
- Never put a literal secret in `.mcp.json`: use `${VAR}` in `headers` for remote `http` servers and in `env` for local stdio servers.
- An unset `${VAR}` does not fail: the config loads with a warning in `claude mcp list` and the literal text is used. In a remote server's `url`/`headers`, a documented set of credential variables reads as empty (Claude Code's own such as `ANTHROPIC_API_KEY`, cloud-provider credentials such as `AWS_BEARER_TOKEN_BEDROCK`, and others listed in the MCP docs), so give secrets for MCP servers their own variable names.
- MCP tools are deferred by default (tool search): only names and server instructions load at start. Set `"alwaysLoad": true` on a server whose tools must load upfront (all its tools then load; a server author can mark a single tool with `anthropic/alwaysLoad` in its `_meta`).
- Prefer an existing, maintained MCP server before building one, and give MCP tools rich descriptions so Claude picks them over built-in tools. *(practice)*

## CI and headless
- `claude -p` with an explicit `--permission-mode` (CI pattern: `dontAsk` plus `--allowedTools ...`), `--output-format json` (add `--json-schema` for structured output), `--max-turns`, and secrets from the CI secret store. In `-p` with no permission host (no SDK `canUseTool`, no `--permission-prompt-tool`), anything that would prompt is denied.
- `--bare` is the documented mode for scripted runs: it skips hooks, skills, plugins, MCP, auto memory, CLAUDE.md, custom commands and subagents. On the Anthropic API it needs `ANTHROPIC_API_KEY` or `apiKeyHelper`, not a subscription login.
- Without `--bare`, `claude -p` runs the project's hooks and `.mcp.json` servers even in an untrusted folder, so review those before running headless on someone else's repo.
- Run review as a separate invocation from generation, and pass prior findings so reruns do not repeat them. *(practice)*

## Housekeeping
- Gitignore `CLAUDE.local.md` (not automatic), `.claude/settings.local.json` (automatic only when Claude Code creates it) and `.claude/worktrees/`.
- No duplicate skill/command names; no contradictions between memory files; no secrets in any committed Claude config.
