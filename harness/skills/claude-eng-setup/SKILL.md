---
name: claude-eng-setup
description: Set up a new or existing project with a well-formed Claude Code configuration following the Claude engineering standards - project CLAUDE.md, path-scoped rules, settings with permission rules, optional hooks, gitignore entries, plan and review folder. Shows every file before writing and never overwrites without approval.
argument-hint: "[project-path]"
disable-model-invocation: true
---
# Claude engineering project setup

Target: `$ARGUMENTS` (if empty, the current working directory). Confirm the resolved absolute path in your first message.

**Ground rules**
- Read before you write. Never overwrite an existing file; if one exists, show the proposed change as a diff and ask.
- Every command, path and tool you put in a file must exist in this project. Check before you write it. Do not invent build or test commands.
- If the project already has a Claude Code setup, suggest `/claude-eng-audit` instead, and only fill gaps here.
- Standards: `${CLAUDE_SKILL_DIR}/../../rules/claude-code-config.md` (read it now if it is not already in context) and `${CLAUDE_SKILL_DIR}/../claude-engineering/references/domain-3-claude-code-config.md`.

## 1. Understand the project
- What it is, who uses it, languages, frameworks, package manager, how it is built, tested and run (read the README, manifests such as `package.json`/`pyproject.toml`, scripts and CI files).
- Whether it is a git repository (`git rev-parse --show-toplevel` from the target; never run `git init` in a home folder).
- Existing conventions you can see in the code (naming, layout, test location, error handling).
- Whether it calls Claude or another LLM (if so, the `claude-engineering` skill applies to that code), and whether it uses a local-model client with a key file (for example `tools/local_ai.py` with `tools/local_ai.json`).
- Whether a plan exists (`PLAN.md`, `_project/`). If not, the working practice (`${CLAUDE_SKILL_DIR}/../claude-engineering/references/working-practice.md`) asks for one before substantial work: offer to create it from its plan template.
- Ask the user only what you cannot find: the audience, what "finished" means, anything off-limits. Log anything else they must decide as a decision with a recommended default.

## 2. Draft the configuration
Draft these, sized to the project. Small projects need less; do not pad.

1. **`CLAUDE.md`** at the project root, well under the 200-line limit (aim for about 120):
   - One paragraph: what this project is and who it is for.
   - Commands: build, test, lint, run, exactly as they work here.
   - Layout: where the important things live.
   - Conventions Claude must follow that it could not infer from the code.
   - Done-when standard for changes (tests pass, files open, etc.) and a pointer to `PLAN.md` and the review folder.
   - No multi-step procedures (those become skills) and no file-type rules (those become path-scoped rules).
2. **`.claude/rules/<topic>.md`** with `paths:` globs (YAML block list), only for conventions that apply to part of the codebase (for example tests, API handlers, infrastructure).
3. **`.claude/settings.json`**:
   - `permissions.deny` for secret files the project has (for example `Read(./.env)`, `Read(./.env.*)`, `Read(./tools/local_ai.json)`, key files) and for destructive commands that should never run here. Tell the user plainly what this covers: Read and Edit deny rules apply to Claude's file tools and to file commands Claude Code recognises in Bash (`cat`, `head`, `tail`, `sed`, `tee`), but not to commands that read without naming the file (for example `grep -r` run in that folder) or to scripts that open files themselves (Python, Node). The sandbox enforces at OS level but runs only on macOS, Linux and WSL2; on native Windows it does not apply. So where a tool supports it, prefer supplying the key through an environment variable instead of a file in the project (for example, a local-model client that reads its key from an environment variable before falling back to a key file). If the sandbox is used, set both `sandbox.failIfUnavailable: true` (exit instead of running unsandboxed when it cannot start) and `sandbox.allowUnsandboxedCommands: false` (no retrying a failed command outside the sandbox).
   - `permissions.allow` only for safe, frequent commands you have confirmed exist (the test and lint commands).
4. **Hooks (offer, do not assume):** propose only hooks that enforce something that must always hold, such as running the formatter after edits (`PostToolUse`) or blocking a dangerous command (`PreToolUse`). Put scripts in `.claude/hooks/` and call them in exec form, which the docs recommend whenever a hook references a path: set `command` to the interpreter and `args` to the script, for example `{"type": "command", "command": "python", "args": ["<PROJECT_DIR>/.claude/hooks/<name>.py"]}`, where `<PROJECT_DIR>` stands for the project-directory placeholder: a `$` sign followed immediately by `{CLAUDE_PROJECT_DIR}`. Write that placeholder, never an absolute path, so the hook works wherever the project is cloned. (This skill cannot spell the placeholder in one piece: Claude Code would replace it with the current folder when the skill loads.) Exec form uses no shell, so paths with spaces need no quoting; on Windows `command` must be a real executable (`python`, `node`, `powershell.exe` with `-NoProfile -ExecutionPolicy Bypass -File <script>`), not a `.cmd` shim. Do not use `bash` in exec form on Windows: on the PATH it can resolve to the WSL launcher instead of Git Bash; write such hooks in Python, or use shell form, which runs under Git Bash. A blocking `PreToolUse` hook either exits 2 with a reason on stderr, or exits 0 and prints JSON `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`. The docs define `permissionDecision` inside `hookSpecificOutput`, so put it there; the test script only counts it there. A missing script is not harmless: Python exits 2 when it cannot open its script, which blocks every call.
5. **Project skills** only for repeatable procedures the user already does (for example release, content build). Use `disable-model-invocation: true` for anything with side effects.
6. **`.gitignore`** (git repositories only): add `CLAUDE.local.md`, `.claude/settings.local.json`, `.claude/worktrees/`, and any local secret files such as `tools/local_ai.json`.
7. **`PLAN.md`** from the plan template in `${CLAUDE_SKILL_DIR}/../claude-engineering/references/working-practice.md` if there is none (or the user's own template, if their `~/.claude/CLAUDE.md` has one), and a review folder (`_project/review/`).
8. **`.mcp.json`** only if the user wants team MCP servers, with `${VAR}` for every secret (`headers` for remote servers, `env` for local ones).

## 3. Show, then write
Show the user the list of files with a one-line purpose each, and the full text of `CLAUDE.md` and `settings.json`. Write only after they approve. Then test, and record real results:
- Every JSON file parses.
- Every command named in `CLAUDE.md` runs (or say which were not run and why).
- Each hook works. For `PreToolUse` and `PostToolUse` hooks, test with the script that ships with this skill. It runs the hooks from `settings.json` as closely to Claude Code's documented behaviour as a script can (exec or shell form, the right shell for the platform, `CLAUDE_PROJECT_DIR` set), and on `PreToolUse` counts both exit 2 and a JSON `hookSpecificOutput.permissionDecision: "deny"` as a block. Hooks on other events have their own rules: the script refuses them, so test those live in a new session. Confirm one important guard live as well.
  `python -I "${CLAUDE_SKILL_DIR}/scripts/test_hook.py" --project "<project path>" --event-json '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' --expect block`
  For a guard, run one case it must block (`--expect block`) and one it must allow (`--expect allow`); `--expect ask` checks a hook that asks the user. On `PostToolUse` the tool has already run, so a "block" only gives Claude feedback: expect `feedback` there. For a hook that blocks nothing, such as a formatter, run an allow case and then check its effect (for example, the file was formatted). A hook that prints `{"continue": false}` stops Claude entirely, whatever else it says: expect `stop` for it. The script follows the exit-code table in the hooks docs: exit 2 blocks whatever the JSON says; for any other code, valid JSON decides and the exit code is ignored; stdout counts as JSON only when it is one whole object. It counts `async` and `asyncRewake` hooks as allow (they run in the background and cannot block), treats every hook as off when the project settings set `disableAllHooks: true`, and counts output that fails validation (a `hookSpecificOutput` without the matching `hookEventName`, a `permissionDecision` outside allow/deny/ask/defer, a field of the wrong type) as an error, as Claude Code does. It reports NOT RUN, never a pass, for what it does not model: `disableAllHooks` set in `settings.local.json` or the user settings, http, mcp_tool, prompt or agent handlers, `if` conditions, and non-boolean `async` or `disableAllHooks` values. Hooks for the same event in those other settings files are listed as also running live. Managed settings are not read. The script exits 0 when the outcome is as expected, 1 when not, and 2 when it could not run; a hook that errors (a missing tool such as `jq`, a script that cannot be opened, exec-form `bash` that resolves to WSL) fails the test rather than passing. Run it from Git Bash or pwsh 7: Windows PowerShell 5.1 mangles the quoted JSON argument. Edits to hooks in settings files are normally picked up automatically; if a hook does not fire in a live session, start a new session and test again.
- Memory loads: ask the user to start a new session in the project and run `/context`. The project `CLAUDE.md` and any unscoped rules should be listed under Memory files. Path-scoped rules load only when a matching file is touched, so test each one by asking Claude to read a matching file and confirm the rule is now in context.

## 4. Independent review loop
Run the review loop from `${CLAUDE_SKILL_DIR}/../claude-engineering/references/working-practice.md` (section 2; the user's own `~/.claude/CLAUDE.md` loop wins if it defines one) on the new configuration:
- Brief the `reviewer-standards` agent (self-contained: project path, files created, standards to check against, done-when checks). Save its findings as `_project/review/claude-setup-round-<N>.md`.
- Fix every High and Medium finding at the source, then review again. The setup is clean when a full round finds no High or Medium and every check in step 3 passes.
- Report: what was created, what was verified (with results), and any decisions left for the user, each with a recommended default.
