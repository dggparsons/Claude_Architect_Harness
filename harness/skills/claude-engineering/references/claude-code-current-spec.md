# Claude Code – current behaviour from Anthropic's docs
Fetched 2026-10-14 from code.claude.com/docs by a research subagent. Items marked **[spot-checked]** were re-read on the doc page directly by the lead session. Where this file and the certification guide disagree, this file wins; where this file says "not stated", do not assume.

## 1. Memory (https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/context-window)
- CLAUDE.md locations, broadest first: managed (`C:\Program Files\ClaudeCode\CLAUDE.md` on Windows); user `~/.claude/CLAUDE.md`; project `./CLAUDE.md` or `./.claude/CLAUDE.md`; local `./CLAUDE.local.md` (gitignore it).
- Files from cwd and every parent load at launch; concatenated, not overridden; root down to cwd; `CLAUDE.local.md` after `CLAUDE.md` in each directory. Subdirectory CLAUDE.md files load on demand when Claude touches files there.
- Memory is context, not enforcement: "To block an action regardless of what Claude decides, use a PreToolUse hook instead." **[spot-checked]**
- `@path` imports: relative paths resolve from the importing file; absolute allowed; max depth four hops **[spot-checked]**; `@~/...` supported; skipped inside code spans/fences; imports load at launch so they do not reduce context **[spot-checked]**. Project files importing outside the working directory trigger an approval dialog; user-scope files (`~/.claude/CLAUDE.md`, `~/.claude/rules/`) do not **[spot-checked]**. HTML block comments are stripped.
- Rules: `.claude/rules/` scanned recursively. No `paths:` = loads at launch. `paths:` (YAML list of globs) = loads when a matching file is read/edited. `paths` is the only frontmatter field read. **User-level `~/.claude/rules/` applies to every project on the machine [spot-checked].**
- Size: target under 200 lines per CLAUDE.md; longer files reduce adherence; files over 4 MiB skipped **[spot-checked]**.
- Auto memory: `~/.claude/projects/<project>/memory/`, `MEMORY.md` index, first 200 lines or 25 KB loaded **[spot-checked]**. Controls: `/memory` toggle, `autoMemoryEnabled`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `autoMemoryDirectory`. Subagents do not inherit it unless they set `memory`.
- `/memory` lists/opens memory files and toggles auto memory; `/context` shows what loaded under "Memory files". `/doctor prompt-audit` audits instruction files and proposes edits.
- After `/compact`: project-root CLAUDE.md re-read and re-injected **[spot-checked]**; up to five recent files re-read; invoked skill bodies re-injected (up to 5,000 tokens each, 25,000 total); SessionStart hooks with `compact` matcher re-run; nested CLAUDE.md and path-scoped rules return only when their trigger file is touched again **[spot-checked]**.
- `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` stops all loading; `claudeMdExcludes` skips files.

## 2. Skills (https://code.claude.com/docs/en/skills) – all items **[spot-checked]**
- Locations: personal `~/.claude/skills/<name>/SKILL.md` (all projects on this machine, not Cowork/cloud); project `.claude/skills/<name>/SKILL.md`; nested `<subdir>/.claude/skills/`; plugin `<plugin>/skills/` (invoked `/plugin:skill`). Precedence enterprise > personal > project.
- Frontmatter: `name`, `description` (recommended; Claude uses it to decide when to apply the skill; falls back to the first non-empty body line; with `when_to_use` truncated at 1,536 chars in the listing – put the key use case first), `when_to_use`, `argument-hint` (autocomplete hint only), `arguments`, `disable-model-invocation` (true = manual `/name` only), `user-invocable` (false = Claude-only background knowledge), `allowed-tools` (pre-approves tools; does not restrict; clears at the user's next message), `disallowed-tools` (removes tools; also clears at the next message), `model`, `effort`, `context: fork` (subagent without the conversation; background by default with fewer tools since v2.1.218; `background: false` to wait), `agent`, `background`, `hooks`, `paths` (auto-load only for matching files), `shell` (`bash`/`powershell`), `metadata`, `license`, `compatibility`.
- Descriptions are always in context; the full body loads only when invoked, then stays in context across turns ("every line is a recurring token cost").
- Keep `SKILL.md` under 500 lines; move reference material to supporting files referenced from SKILL.md; scripts are executed, not loaded.
- Substitutions: `$ARGUMENTS`, `$ARGUMENTS[N]`, `$N`, named `$name`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_PROJECT_DIR}`, and plugin vars. `${CLAUDE_SKILL_DIR}` is "The directory containing the skill's `SKILL.md` file ... Use this in bash injection commands to reference scripts or files bundled with the skill, regardless of the current working directory"; Claude Code substitutes it and `${CLAUDE_PROJECT_DIR}` in "the skill's markdown content, and Bash rules in the `allowed-tools` frontmatter" (checked 2026-10-15).
- Reloading: edits under an existing skills folder are picked up within the session; "If you create a top-level skills directory that didn't exist when the session started, run `/reload-skills`" (https://code.claude.com/docs/en/skills). For agents, "The watcher covers only directories that existed when the session started, so after creating a scope's first agent file in a new `agents` directory, restart to load it" (https://code.claude.com/docs/en/sub-agents). Both checked 2026-10-15.
- Custom commands are merged into skills: `.claude/commands/x.md` and `.claude/skills/x/SKILL.md` both create `/x`; skill wins on a clash; prefer skills for new work.

## 3. Subagents (https://code.claude.com/docs/en/sub-agents)
- Priority: managed > `--agents` flag > `.claude/agents/` > `~/.claude/agents/` > plugin `agents/`.
- Frontmatter: required `name`, `description`; optional `tools`, `disallowedTools`, `model` (sonnet/opus/haiku/fable/full ID/inherit), `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory` (user/project/local), `background`, `effort`, `isolation: worktree`, `omitClaudeMd`, `color`, `initialPrompt`.
- Built-ins: Explore (read-only), Plan (read-only), general-purpose.
- Invocation: automatic by description; by name in natural language; `@"name (agent)"`; `claude --agent <name>`.
- Nesting allowed, three layers by default (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`).
- Fresh context; non-fork subagents load the CLAUDE.md hierarchy (except Explore, Plan, `omitClaudeMd: true`); skills listed in `skills:` are preloaded in full, and unlisted skills can still be invoked through the Skill tool.

## 4. Hooks (https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/hooks-guide)
- Events include SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, Notification, SubagentStart, SubagentStop, Stop, PreCompact, PostCompact, InstructionsLoaded, ConfigChange, FileChanged, SessionEnd and others.
- Shape: `hooks -> event -> [{matcher, hooks:[{type, command, timeout}]}]`. Types: command, http, mcp_tool, prompt, agent (experimental).
- Exit codes (checked 2026-10-15), from the exit-code table: exit 0 with valid JSON, "Success. The fields apply"; exit 2, "Blocking error. Claude Code still reads the fields, but they can't override the block" (stderr is the reason; for SessionStart/UserPromptSubmit exit-0 stdout becomes context); any other exit code with valid JSON, "Success. Claude Code ignores the exit code, and the fields alone decide"; JSON that cannot be parsed or "fails schema validation", a "Non-blocking error" (on exit 2 it still blocks); plain text or nothing on another exit code, a non-blocking error.
- What counts as JSON (checked 2026-10-15): stdout is parsed as JSON "when the whole output is one JSON object with nothing around it but whitespace"; "Output that doesn't start with `{`, or that starts with `{` and doesn't end with `}`" is plain text; "Anything else that starts with `{` and ends with `}` but isn't valid JSON" is a parse failure.
- `hookSpecificOutput` "requires a `hookEventName` field set to the event name"; with the rule above that output failing schema validation is a non-blocking error, a missing or mismatched `hookEventName` is treated as an error (inferred: the docs do not name this case). `continue: false`: "Claude stops processing entirely after the hook runs. Takes precedence over any event-specific decision fields" (checked 2026-10-15).
- Async hooks (checked 2026-10-15): "Async hooks can't block or control Claude's behavior: response fields like `decision`, `permissionDecision`, and `continue` have no effect, because the action they would have controlled has already completed."
- `disableAllHooks` (checked 2026-10-15): "Claude Code reads the value left after settings precedence applies, so a `"disableAllHooks": false` in a project's `.claude/settings.json` overrides a `true` in your user settings"; set in user, project or local settings it "can't disable those managed hooks".
- PreToolUse `hookSpecificOutput.permissionDecision`: allow/deny/ask/defer, plus `updatedInput`. PostToolUse: `updatedToolOutput`. `additionalContext` capped at 10,000 chars.
- Defined in user/project/local/managed settings, plugin `hooks/hooks.json`, skill or subagent frontmatter; entries merge.
- Windows: command hooks run under Git Bash (or PowerShell if absent); `"shell": "powershell"` available; `${CLAUDE_PROJECT_DIR}` placeholder.

## 5. Settings and permissions (https://code.claude.com/docs/en/settings, /settings-reference, /permissions)
- Precedence high to low: managed > `--settings` > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`. Scalars: higher wins; lists (e.g. `permissions.allow`) combine.
- Read/Edit deny rules cover Claude's file tools, file commands Claude Code recognises in Bash (`cat`, `head`, `tail`, `sed`, `tee`) and redirection targets; they "don't apply to a command that reads files without naming them, such as `grep -r` … or to arbitrary subprocesses … like a Python or Node script that opens files itself" (https://code.claude.com/docs/en/permissions, checked 2026-10-14).
- Sandbox: "runs on macOS, Linux, and WSL2. On native Windows, Claude Code runs commands unsandboxed." If it cannot start, commands run unsandboxed unless `sandbox.failIfUnavailable` is `true`; Claude can also retry a failed command outside the sandbox unless `sandbox.allowUnsandboxedCommands` is `false` (https://code.claude.com/docs/en/sandboxing, checked 2026-10-14).
- Hook command forms: exec form when `args` is set (no shell; `${CLAUDE_PROJECT_DIR}` substituted as plain text; recommended whenever a hook references a path; on Windows `command` must be a real executable, not a `.cmd` shim); shell form otherwise (`sh -c` on macOS and Linux, Git Bash on Windows, PowerShell if Git Bash is missing or with `"shell": "powershell"`). Both export `CLAUDE_PROJECT_DIR` to the process (https://code.claude.com/docs/en/hooks, checked 2026-10-14).
- Permission evaluation: deny, then ask, then allow; first match wins. Rule forms such as `Bash(npm run *)`, `Read(./secrets/**)`, `Edit(src/**)`, `WebFetch(domain:x.com)`, `mcp__server__*`, `Agent(...)`, `Skill(...)`. Bash rules are not a security boundary.
- `permissions.defaultMode` (a key inside `permissions`, not top-level): default, acceptEdits, plan, auto, dontAsk, bypassPermissions.

## 6. Permission modes (https://code.claude.com/docs/en/permission-modes)
- Plan mode: Shift+Tab cycle, `/plan` prefix, `--permission-mode plan`, or `"permissions": {"defaultMode": "plan"}` in settings. Explores without editing; approval then offers auto or manual edits.
- Auto mode is the built-in starting mode for interactive sessions from v2.1.283; a classifier reviews actions.

## 7. Headless and CI (https://code.claude.com/docs/en/headless, /cli-reference, /github-actions)
- `claude -p`; `--output-format text|json|stream-json`; `--json-schema` with json output puts the result in `structured_output`; `--max-turns`, `--max-budget-usd`, `--allowedTools`, `--disallowedTools`, `--permission-mode`, `--continue`, `--resume`, `--append-system-prompt[-file]`, `--system-prompt[-file]`, `--settings`, `--mcp-config`, `--strict-mcp-config`, `--agents`, `--add-dir`, `--model`.
- `--bare` skips hooks, skills, plugins, MCP, auto memory, CLAUDE.md, custom commands and subagents; recommended for scripted runs. On the Anthropic API it needs `ANTHROPIC_API_KEY` or an `apiKeyHelper` (not a subscription login); Bedrock, Agent Platform and Foundry keep using their own credentials.
- In `-p` with no permission host (no SDK `canUseTool`, no `--permission-prompt-tool`), anything that would prompt is denied; CI should pass an explicit `--permission-mode` (documented pattern: `dontAsk` plus `--allowedTools`).
- Security: without `--bare`, `claude -p` runs project hooks and `.mcp.json` servers even in an untrusted folder, with no trust dialog.
- GitHub Action `anthropics/claude-code-action@v1` (docs say to update from `@beta` to `v1`): inputs `prompt`, `claude_args`, `anthropic_api_key`, `claude_code_oauth_token`, `settings`, `plugins`, `trigger_phrase`.

## 8. Plugins (https://code.claude.com/docs/en/plugins/create, /plugins/manifest-reference, /plugins/loading)
- `.claude-plugin/plugin.json` (only `name` required). Bundles skills/, agents/, hooks/hooks.json, .mcp.json, output-styles/, bin/. A plugin-root CLAUDE.md is NOT loaded – put instructions in a skill.
- Local: `claude --plugin-dir ./x`, `/reload-plugins`, `claude plugin validate <path>`. Plugin skills are namespaced `/plugin:skill`.
- Worth it for versioned cross-machine distribution; a plain `~/.claude` setup needs no plugin.

## 9. Other
- Output styles: `~/.claude/output-styles/` or `.claude/output-styles/`; instructions, not enforcement.
- Managed settings on Windows: `C:\Program Files\ClaudeCode\managed-settings.json`.
- Deprecations: `includeCoAuthoredBy` → `attribution`; `--enable-auto-mode` removed; `--remote` → `--cloud`; `--bare` to become default for `-p`.
