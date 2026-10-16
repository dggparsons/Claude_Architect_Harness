---
name: claude-eng-doctor
description: Check that the Claude engineering harness is installed, unchanged and loaded in this session, and that the current project is set up to build properly (CLAUDE.md, plan, review folder, settings, gitignore). Read-only. Use when the user asks whether their setup works, whether a new project is ready, or after installing or updating the harness.
argument-hint: "[project-path]"
---
# Claude engineering doctor

Read-only health check. Change nothing. Target project: `$ARGUMENTS` (if empty, the current working directory).

## 1. Run the checker
Run `python -I "${CLAUDE_SKILL_DIR}/scripts/doctor.py" "<project path>"` and keep its output. It checks:
- the harness: every file in its install inventory present and unchanged (including files that were already there), every entry inside the config folder, a fixed list of required harness files present whatever the manifest says, and where the source lives (with its last git commit if it is a repository);
- the project: `CLAUDE.md` under 200 lines, `PLAN.md`, a review folder, `.claude/settings.json` that parses, and, in a git repository, that git ignores the local Claude files through the project's own `.gitignore` (not only a personal ignore file) and does not already track them. A repository git cannot read is a FAIL.
Exit code 0 = ready, 1 = something needs attention, 2 = the check could not run (say so; never call it a pass).

## 2. Check this session
A script cannot see what is loaded in this conversation, so answer these from your own context, honestly:
- Is a rule titled "Claude engineering standards (always on)" in your context? (It should be, in every session.)
- Is the `claude-engineering` skill in your list of available skills?
- Are the agents `reviewer-facts`, `reviewer-consistency`, `reviewer-end-user` and `reviewer-standards` available?
- The config rule ("Writing Claude Code configuration") loads only after a project config file such as `CLAUDE.md` is read. If it is not in context yet, that is expected; say so rather than calling it a failure.
If any of the first three is missing, tell the user to start a new Claude Code session (the always-on rule loads at start-up; skills added during a session are usually picked up, or after `/reload-skills` if `~/.claude/skills` did not exist when the session started; agents in a newly created `~/.claude/agents` folder need a new session), and if it is still missing, to reinstall from the harness source with `python -I tools/install_harness.py --apply`.

## 3. Report
Lead with one line: READY, READY with warnings, or NOT READY. Then:
- What failed or needs attention, each with the one action that fixes it.
- For a project that is not set up: recommend typing `/claude-eng-setup`.
- For an existing project that is set up: mention that `/claude-eng-audit` gives a full review against the standards.
- If the harness source is a git repository, remind the user that running `python -I tools/update_harness.py` there pulls, tests and installs the latest harness (see the source folder's README).
