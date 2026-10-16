# Claude Engineering Harness
A set of rules, skills and reviewer agents for [Claude Code](https://code.claude.com) that makes every session on a machine follow the same engineering standards: how to plan, delegate, handle errors, write prompts and tool schemas, configure Claude Code, keep secrets out of projects, and review work.

The standards are distilled from [claudecertificationguide.com](https://claudecertificationguide.com), an independent community study guide for the Claude Certified Architect (Foundations) exam, and every technical claim the harness relies on was checked against Anthropic's own documentation (14 and 15 October 2026). Where the guide and the documentation disagree, the documentation wins. This project is not affiliated with or endorsed by Anthropic or by the guide's authors. See [Credits](#credits-and-licence).

## What gets installed
Everything goes into your Claude config folder (`~/.claude`; on Windows `C:\Users\<you>\.claude`), 21 files in all. Your own `CLAUDE.md` and `settings.json` are never touched.

| Installed | When it is used |
|---|---|
| `rules/claude-engineering.md` | Every session, in every project (44 lines) |
| `rules/claude-code-config.md` | Loads by itself when Claude reads or edits a project's `CLAUDE.md`, `AGENTS.md`, `.claude/` files, `.mcp.json` or a `SKILL.md` |
| `skills/claude-engineering/` | Loads when you build anything that calls Claude or another LLM, or type `/claude-engineering`. Holds the checklists, five domain references, the current Claude Code spec, the verification evidence, and the working practice (plan template, review loop, severity scale) the other skills use |
| `skills/claude-eng-setup/` | `/claude-eng-setup` sets up a project. You type it; Claude never starts it by itself, because it writes files |
| `skills/claude-eng-audit/` | `/claude-eng-audit` reviews a project and proposes fixes. You type it |
| `skills/claude-eng-doctor/` | `/claude-eng-doctor`, or ask "is my setup working?". Read-only health check |
| `agents/reviewer-facts.md`, `reviewer-consistency.md`, `reviewer-end-user.md`, `reviewer-standards.md` | Independent reviewers for the review loop. Three only read; the end-user reviewer can run commands to test the work, has no editing tools, and is told not to change anything |

If your own `~/.claude/CLAUDE.md` defines its own plan template, review loop or severity scale, yours takes precedence.

## Requirements
Git, Claude Code, and Python 3 on the PATH (check with `python --version`; on Windows the Microsoft Store stub does not count).

## Install
```
git clone https://github.com/dggparsons/Claude_Architect_Harness.git
cd Claude_Architect_Harness
python -I tools/update_harness.py --no-pull
```
This runs the automated tests and installs; nothing is installed if the tests or the lint fail. A clone runs 188 tests and lists 18 as SKIPPED: those exercise maintainer tooling for refreshing the knowledge base from its source site, which is not part of this repository. On macOS and Linux a few Windows-only tests are also listed as SKIPPED. Then start a new Claude Code session and type `/claude-eng-doctor` to confirm. (The always-on rule loads when a session starts. Skills added during a session are usually picked up straight away; if `~/.claude/skills` did not exist when the session started, run `/reload-skills`. Agents in a newly created `~/.claude/agents` folder need a new session.)

## Update, check, remove
```
python -I tools/update_harness.py                        # git pull, test, install
python -I tools/install_harness.py --status              # does ~/.claude match the source?
python -I tools/install_harness.py --uninstall --apply   # remove (keeps files you edited)
```
`update_harness.py` runs `git pull --ff-only`, the tests, then the install, and stops at the first failure; nothing is installed if the pull, the tests or the lint fail. Backups of anything replaced or removed go to `~/.claude/backups/claude-eng-harness-<timestamp>/`.
- **If the pull stops:** run `git status`. Uncommitted edits: `git stash`, then rerun. Local commits: `git pull --rebase`, then rerun.
- **If the install is BLOCKED:** a file in `~/.claude` was edited by hand, or is your own file with the same name as a harness file. Nothing is overwritten. To replace it with the harness version (a backup is kept), run `python -I tools/install_harness.py --apply --force`.
- **If it says KEEP:** a file the harness installed earlier is no longer in the source, but you edited it, so it was kept (and still loads). Remove it by hand, or rerun with `--force` to remove it with a backup. Unchanged retired files are backed up and removed automatically.
- **If it says UNSAFE:** the manifest (`~/.claude/claude-eng-harness.manifest.json`) names a path outside the harness folders or one that is not a plain file, or `rules/`, `agents/` or `skills/` in your config folder (or a folder inside one) is a link to somewhere else. The installer stopped before changing anything. Linked harness folders are not supported.
- **If it says FAILED:** a retired file could not be removed (for example it is read-only or open). It is kept and still listed in the manifest; fix the cause and rerun.

## Starting a new project
1. Create the folder and open Claude Code in it.
2. Type `/claude-eng-setup`. Claude looks at the project, drafts a `CLAUDE.md`, path-scoped rules, `settings.json` with deny rules, `.gitignore` entries, a plan and a review folder, lists every file it will write, shows the full text of `CLAUDE.md` and `settings.json`, and writes only after you approve. Hooks are offered, never assumed, and each one is tested.
3. Type `/claude-eng-doctor`. It should say **READY** (or **READY with warnings** you have chosen to accept).
4. Build as normal. The standards are already loaded.
5. Before you hand the work over, type `/claude-eng-audit` for a full review.

## Existing projects
Nothing to install per project: the standards apply to every session in every project once the harness is installed. What is not automatic is fixing what a project already contains.
1. Open Claude Code in the project and type `/claude-eng-doctor` for a quick yes or no.
2. Type `/claude-eng-audit`. It runs 32 numbered checks and a secrets scan, then writes a report with a findings table, a scorecard and an improvement plan into the project's review folder. It changes nothing else.
3. Tell Claude which fixes to apply. Each goes through the review loop.

## How do I know it is working?
`/claude-eng-doctor` checks:
- the install: every file the harness should have is present, non-empty, listed in the install manifest with a hash, and unchanged; no retired file is still loading; and where the source is;
- this session: the always-on rule, the knowledge skill and the four reviewers are available;
- the project: `CLAUDE.md` under 200 lines, a plan, a review folder, `settings.json` that parses, and (in a git repository) that the project's own `.gitignore` ignores the local Claude files (a personal ignore file alone is a warning, because a teammate who clones is not protected) and that git does not already track them. A repository git cannot read is a FAIL.

It ends with **READY**, **READY with warnings** or **NOT READY**, and says what to do next.

## What it does not do
- It guides Claude; only `settings.json` rules and hooks enforce, and those match command text, so they stop mistakes rather than a determined bypass. On native Windows there is no sandbox behind them.
- The config rule loads for files in the current project, not for files under `~/.claude`; the always-on rule tells Claude to read it first in that case.
- **The hook tester** (`/claude-eng-setup` uses it) covers `command` hooks on `PreToolUse` and `PostToolUse` and follows the exit-code table in the hooks documentation, including `async` hooks, `onFailure`, the deprecated PreToolUse `decision`, `disableAllHooks` in the project settings, `hookEventName` and `continue: false`. It reports NOT RUN, never a pass, for what it does not model: other events, `if` conditions, http, mcp_tool, prompt and agent handlers, `disableAllHooks` in `settings.local.json` or the user settings, and hooks that leave a background process running after they exit (Claude Code treats those specially, and the outcome cannot be told from here). Managed settings are not read. Confirm one important guard in a live session.
- **The secrets scanner** recognises only the formats listed at the top of `harness/skills/claude-eng-audit/scripts/secrets_scan.py`. It reads the files as they are now and the staged copies. It exits 1, never 0, when it could not scan something: a binary file, a repository git cannot read, a file over 2 MB, a file that took more than 30 seconds, or an untracked file in `node_modules`, a virtual environment or a tool cache. It does not read older commits or recognise credentials written as free text, and it never prints a value or the source line. It is an aid that needs a person's judgement, not a guarantee.
- With `CLAUDE_CONFIG_DIR` set, the installer and the doctor use that folder and the skills find their own files through the skill folder, but both rules files and the standards reviewer still name `~/.claude` paths, because rules and agents get no substitution.
- Facts are dated 14 and 15 October 2026. The knowledge skill tells Claude to check the live documentation before relying on an exact field or limit.

## Changing the harness
This repository is the source of truth; `~/.claude` is a generated copy.
1. Edit `harness/` or `kb/`, never the installed copy in `~/.claude`.
2. Run `python -I tools/build_harness.py` to regenerate the references from `kb/` and lint (`--check` lints without writing). Commit the regenerated files with their source.
3. Run `python -I tools/test_harness_scripts.py`. It runs in temporary folders with its own config folder and never touches your `~/.claude`.
4. Every guard has a test, and every guard has a mutant in `tools/mutation/`: a deliberate break of the guard that the tests must catch. `mutate_skill_scripts.py` and `mutate_doctor_installer.py` take this folder (read only) and a new empty work folder outside it; `mutate_lint.py` takes a scratch copy. Their usage lines are at the top of each file, and each takes optional words to run only the mutants whose names contain them.

## Folder map
| Folder | Contents |
|---|---|
| `harness/` | Source of everything installed. `skills/claude-engineering/references/` is generated by `tools/build_harness.py`; do not edit it by hand |
| `kb/` | The study guide distilled into rules per domain, corrections applied inline; the current Claude Code spec; the working practice; `verification/` with the evidence for every checked claim |
| `tools/` | Build and lint, installer, updater and the test suite |
| `tools/mutation/` | Mutation tests that prove the guards can fail |

## Credits and licence
- The engineering standards in `kb/` and the generated references are distilled, in this project's own words, from the lessons at [claudecertificationguide.com](https://claudecertificationguide.com) (© 2026 claudecertificationguide.com, an independent community resource), and corrected against Anthropic's documentation. The guide's pages themselves are not included. If you are the guide's author and want attribution changed or anything removed, please open an issue.
- Claude and Claude Code are products of Anthropic. This project is independent.
- The code and this project's own text are released under the [MIT licence](LICENSE).
