# Claude Engineering Harness

The source of a set of rules, skills and reviewer agents that the installer copies into a Claude config folder (`~/.claude` by default). The installed copy is generated: edit the source here, never the copy. The README explains what is installed and how to use it.

## Build and test
- `python -I tools/build_harness.py`: regenerates `harness/skills/claude-engineering/references/` from `kb/` and lints the harness. Add `--check` to lint without writing.
- `python -I tools/test_harness_scripts.py`: the full suite. It runs in temporary folders, with `CLAUDE_CONFIG_DIR` pointing at a temporary config folder, and never touches `~/.claude`.
- `python -I tools/install_harness.py --status`: compares the installed copy with the source. `--apply` installs; it writes to the user's `~/.claude`, so ask first.
- `tools/mutation/*.py`: mutation suites that prove the guards fail when broken. Each takes a scratch copy or a new work folder and refuses to run on the project itself. Their usage lines are at the top of each file. Do not edit `harness/`, `kb/` or `tools/` while one is running: each mutant copies them fresh.

## Conventions
- **Source of truth:** `harness/` and `kb/`. Never hand-edit the generated `references/` folder; rebuild it, and commit it with the source change.
- **Tests:** every guard in a script has a test, and every new guard gets a mutant in `tools/mutation/`. Never weaken a test to make it pass.
- **Skills:** a SKILL.md reaches its own files through the skill-folder placeholder, with the whole path in double quotes when it is part of a command (the config folder can contain spaces). Lint bans hard-coded `~/.claude/skills|rules|agents/` paths and the project-directory placeholder.
- **Bulk edits:** use a script that checks each replacement matches the expected number of times and writes nothing if one does not.
- **Facts:** every claim about Claude Code or the API is checked against Anthropic's documentation, with the quote and date recorded in `kb/verification/` or `kb/claude-code-current-spec.md`.
- **Secrets:** use only fake values in tests. Run the secrets scanner (`harness/skills/claude-eng-audit/scripts/secrets_scan.py`) before committing.
- **Spelling:** UK English.
