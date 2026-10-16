"""Round-2 mutation test of tools/build_harness.py --check on a scratch copy.

Usage: python -I tools/mutation/mutate_lint.py <scratch copy folder (harness, kb, tools)>
Each mutant: restore pristine harness/ and kb/, apply one change, run --check.
expect FAIL = the lint should reject it. A mutant that exits 0 has ESCAPED.
"""
import pathlib
import shutil
import subprocess
import sys

try:  # a FAIL line may contain non-ASCII; never crash the report on a cp1252 console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

Q = pathlib.Path(sys.argv[1])

if any((p / 'PLAN.md').exists() or (p / 'tools' / 'install_harness.py').exists() and (p / '_project').exists()
       for p in [Q, *Q.resolve().parents]):
    sys.exit('Refusing to run: point this at a scratch copy of the project, never the project itself.')


def claim_dir(p):
    """Return p as an empty folder this script owns. Refuses to delete anything it did not create."""
    p = pathlib.Path(p)
    marker = p / ".mutation-work"
    if p.exists():
        if any(p.iterdir()) and not marker.exists():
            sys.exit(f"Refusing to delete {p}: it is not empty and was not created by a mutation script.")
        shutil.rmtree(p)
    p.mkdir(parents=True)
    marker.write_text("created by a tools/mutation script; safe for it to delete\n", encoding="utf-8")
    return p

# Work on a private copy, so nothing in the folder given on the command line is ever deleted.
SOURCE = Q
Q = claim_dir(SOURCE.parent / "mutation-lint-work")
for sub in ("harness", "kb", "tools"):
    shutil.copytree(SOURCE / sub, Q / sub, ignore=shutil.ignore_patterns("__pycache__"))
PRISTINE = claim_dir(SOURCE.parent / "mutation-lint-pristine")
shutil.copytree(Q / "harness", PRISTINE / "harness")
shutil.copytree(Q / "kb", PRISTINE / "kb")


def restore():
    for d in ("harness", "kb"):
        shutil.rmtree(Q / d)
        shutil.copytree(PRISTINE / d, Q / d)


def edit(rel, old, new, count=1):
    p = Q / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, f"mutant setup: {rel} has {t.count(old)} of {old!r}"
    p.write_text(t.replace(old, new), encoding="utf-8", newline="")


def append(rel, text):
    p = Q / rel
    p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8", newline="")


def write(rel, text):
    p = Q / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


R_ON = "harness/rules/claude-engineering.md"
R_CFG = "harness/rules/claude-code-config.md"
S_ENG = "harness/skills/claude-engineering/SKILL.md"
S_SET = "harness/skills/claude-eng-setup/SKILL.md"
S_AUD = "harness/skills/claude-eng-audit/SKILL.md"
A_STD = "harness/agents/reviewer-standards.md"
A_FACT = "harness/agents/reviewer-facts.md"
A_END = "harness/agents/reviewer-end-user.md"
REF1 = "harness/skills/claude-engineering/references/domain-1-agentic-architecture.md"
DESC_SET = next(l for l in (Q / S_SET).read_text(encoding="utf-8").splitlines() if l.startswith("description:"))

MUTANTS = [
    # --- round-1 mutants (still applicable)
    ("R1 TODO in always-on rule", lambda: append(R_ON, "\n- TODO decide this\n")),
    ("R1 TODO on a line that also says 'placeholder'", lambda: append(R_ON, "\n- TODO: write the placeholder section\n")),
    ("R1 TBC in a reference file", lambda: append(REF1, "\nTBC\n")),
    ("R1 lowercase todo:", lambda: append(R_ON, "\n- todo: finish\n")),
    ("R1 sk-ant- key", lambda: append(A_FACT, "\nsk-ant-api03-abcdefghijklmnopqrstuv\n")),
    ("R1 sk-proj- key", lambda: append(A_FACT, "\nsk-proj-abcdefghijklmnopqrstuvwxyz0123\n")),
    ("R1 api_key assignment", lambda: append(A_FACT, '\napi_key = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"\n')),
    ("R1 always-on rule over 80 lines", lambda: append(R_ON, "".join(f"- extra line {i}\n" for i in range(40)))),
    ("R1 paths renamed path", lambda: edit(R_CFG, "\npaths:\n", "\npath:\n")),
    ("R1 unclosed quote in paths", lambda: edit(R_CFG, '  - "AGENTS.md"\n', '  - "AGENTS.md\n')),
    ("R1 closing --- removed", lambda: edit(R_CFG, '  - "**/SKILL.md"\n---\n', '  - "**/SKILL.md"\n\n')),
    ("R1 skill name differs from folder", lambda: edit(S_SET, "name: claude-eng-setup", "name: claude-eng-set-up")),
    ("R1 skill description removed", lambda: edit(S_SET, DESC_SET + "\n", "")),
    ("R1 description+when_to_use over 1536", lambda: edit(S_ENG, "when_to_use: Use when", "when_to_use: " + "x" * 1300 + " Use when")),
    ("R1 SKILL.md 500+ lines", lambda: append(S_SET, "".join(f"line {i}\n" for i in range(460)))),
    ("R1 named reference missing", lambda: (Q / REF1).rename(Q / REF1.replace("domain-1-", "domain-one-"))),
    ("R1 extra reference never named", lambda: write("harness/skills/claude-engineering/references/extra.md", "x\n")),
    ("R1 disable-model-invocation removed", lambda: edit(S_SET, "disable-model-invocation: true\n", "")),
    ("R1 disable_model_invocation misspelt", lambda: edit(S_SET, "disable-model-invocation: true\n", "disable_model_invocation: true\n")),
    ("R1 ': ' in plain description", lambda: edit(S_SET, "description: Set up a new", "description: Setup: a new")),
    ("R1 skill name with capitals/spaces (folder renamed too)",
     lambda: [edit(S_SET, "name: claude-eng-setup", "name: Claude Eng Setup"),
              (Q / "harness/skills/claude-eng-setup").rename(Q / "harness/skills/Claude Eng Setup")]),
    ("R1 agent tools removed", lambda: edit(A_STD, "tools: Read, Grep, Glob\n", "")),
    ("R1 Edit added (string)", lambda: edit(A_STD, "tools: Read, Grep, Glob", "tools: Read, Grep, Glob, Edit")),
    ("R1 Edit added (YAML list)", lambda: edit(A_STD, "tools: Read, Grep, Glob\n", "tools:\n  - Read\n  - Grep\n  - Edit\n")),
    ("R1 NotebookEdit added", lambda: edit(A_STD, "tools: Read, Grep, Glob", "tools: Read, Grep, Glob, NotebookEdit")),
    ("R1 Bash via space-separated list", lambda: edit(A_STD, "tools: Read, Grep, Glob", "tools: Read Grep Glob Bash")),
    ("R1 tool misspelt Reed", lambda: edit(A_STD, "tools: Read, Grep, Glob", "tools: Reed, Grep, Glob")),
    ("R1 agent name differs from file", lambda: edit(A_STD, "name: reviewer-standards", "name: reviewer-standard")),
    ("R1 unknown preloaded skill", lambda: edit(A_STD, "  - claude-engineering\n", "  - claude-engineering-x\n")),
    ("R1 model gpt-4", lambda: edit(A_STD, "model: inherit", "model: gpt-4")),
    ("R1 kb changed, references stale", lambda: append("kb/domain-1-agentic-architecture.md", "\n- New rule added to kb only.\n")),
    ("R1 BOM before path-rule frontmatter", lambda: write(R_CFG, "﻿" + (Q / R_CFG).read_text(encoding="utf-8"))),
    ("R1 cross-skill reference domain-9", lambda: edit(S_SET, "domain-3-claude-code-config.md`", "domain-9-claude-code-config.md`")),
    # --- round-2 new mutants
    ("N1 TBD placeholder", lambda: append(R_ON, "\n- Retry budget: TBD\n")),
    ("N2 TODO on a line using the exemption phrase", lambda: append(R_ON, "\n- TODO: list the placeholders (TODO, TBC) here\n")),
    ("N3 'lorem ipsum' dummy text", lambda: append(R_ON, "\n- Lorem ipsum dolor sit amet.\n")),
    ("N4 Agent tool on a read-only reviewer (can spawn an editing subagent)",
     lambda: edit(A_STD, "tools: Read, Grep, Glob", "tools: Read, Grep, Glob, Agent")),
    ("N5 permissionMode: bypassPermissions on reviewer-end-user",
     lambda: edit(A_END, "model: inherit\n", "model: inherit\npermissionMode: bypassPermissions\n")),
    ("N6 permissionMode: acceptEdits on a read-only reviewer",
     lambda: edit(A_STD, "model: inherit\n", "model: inherit\npermissionMode: acceptEdits\n")),
    ("N7 mcpServers added to a read-only reviewer",
     lambda: edit(A_FACT, "model: inherit\n", "model: inherit\nmcpServers:\n  - github\n")),
    ("N8 unknown skill key 'when-to-use' (silently ignored by Claude Code)",
     lambda: edit(S_ENG, "when_to_use:", "when-to-use:")),
    ("N9 unknown agent key 'disallowed-tools' (silently ignored)",
     lambda: edit(A_END, "model: inherit\n", "model: inherit\ndisallowed-tools: Edit\n")),
    ("N10 claude-engineering gets disable-model-invocation (breaks auto-load and preload)",
     lambda: edit(S_ENG, "when_to_use:", "disable-model-invocation: true\nwhen_to_use:")),
    ("N11 claude-eng-setup gets user-invocable: false (with DMI true = unreachable)",
     lambda: edit(S_SET, "disable-model-invocation: true\n", "disable-model-invocation: true\nuser-invocable: false\n")),
    ("N12 cross-skill path to a misspelt skill folder",
     lambda: edit(S_SET, "${CLAUDE_SKILL_DIR}/../claude-engineering/references/domain-3-claude-code-config.md",
                  "${CLAUDE_SKILL_DIR}/../claude-engneering/references/domain-3-claude-code-config.md")),
    ("N12b skill-folder path to a misspelt rules file",
     lambda: edit(S_AUD, "${CLAUDE_SKILL_DIR}/../../rules/claude-code-config.md", "${CLAUDE_SKILL_DIR}/../../rules/claude-code-confg.md")),
    ("N12c skill-folder path to a misspelt script",
     lambda: edit(S_AUD, "${CLAUDE_SKILL_DIR}/scripts/secrets_scan.py", "${CLAUDE_SKILL_DIR}/scripts/secret_scan.py")),
    ("N12d hard-coded ~/.claude path to a harness file", lambda: append(S_AUD, "\nRun ~/.claude/skills/claude-eng-audit/scripts/secrets_scan.py\n")),
    ("N13 slash command misspelt in always-on rule", lambda: edit(R_ON, "`/claude-eng-setup`", "`/claude-eng-setpu`")),
    ("N14 always-on rule grows to 60 lines (DESIGN ceiling is 50)",
     lambda: append(R_ON, "".join(f"- extra line {i}\n" for i in range(17)))),
    ("N15 invented full model ID", lambda: edit(A_STD, "model: inherit", "model: claude-opus-9-9")),
    ("N16 disable-model-invocation quoted string \"true\"",
     lambda: edit(S_SET, "disable-model-invocation: true\n", 'disable-model-invocation: "true"\n')),
    ("N17 disable-model-invocation: yes (documented boolean from v2.1.218)",
     lambda: edit(S_SET, "disable-model-invocation: true\n", "disable-model-invocation: yes\n")),
    ("N18 duplicate key", lambda: edit(A_STD, "model: inherit\n", "model: inherit\nmodel: opus\n")),
    ("N19 tab in frontmatter", lambda: edit(A_STD, "model: inherit\n", "model:\tinherit\n")),
    ("N20 private key block in a skill file", lambda: append(S_AUD, "\n-----BEGIN RSA PRIVATE KEY-----\n")),
    ("N21 secret in a non-.md file shipped in a skill folder",
     lambda: write("harness/skills/claude-eng-setup/notes.txt", "token: 'abcdefghijklmnopqrstuvwxyz'\n")),
    ("N22 stray non-Markdown file in a skill folder (would be installed)",
     lambda: write("harness/skills/claude-eng-setup/scratch.py", "print('hi')\n")),
    ("N23 xoxb- Slack token", lambda: append(A_FACT, "\nxoxb-1234567890-abcdefghijkl\n")),
    ("N24 path rule entry unquoted '**/CLAUDE.md' (YAML alias char)",
     lambda: edit(R_CFG, '  - "**/CLAUDE.md"\n', "  - **/CLAUDE.md\n")),
    ("N25 path rule paths: [] flow list", lambda: edit(R_CFG, "\npaths:\n", "\npaths: []\nx:\n")),
    ("N27 agent description removed", lambda: edit(A_FACT, next(l for l in (Q / A_FACT).read_text(encoding='utf-8').splitlines() if l.startswith('description:')) + "\n", "")),
    ("N28 fifth agent with Write added", lambda: write("harness/agents/reviewer-extra.md",
     "---\nname: reviewer-extra\ndescription: x\ntools: Read, Write\nmodel: inherit\n---\nbody\n")),
    ("N29 path rule loses all patterns but keeps key", lambda: edit(R_CFG,
     '  - "CLAUDE.md"\n  - "CLAUDE.local.md"\n  - "AGENTS.md"\n  - "**/AGENTS.md"\n  - "**/CLAUDE.md"\n  - "**/CLAUDE.local.md"\n  - "**/.claude/**"\n  - "**/.mcp.json"\n  - ".mcp.json"\n  - "**/SKILL.md"\n', "")),
    ("N30 mention of unknown agent reviewer-security", lambda: append(S_AUD, "\nAsk reviewer-security too.\n")),
    ("N31 mention of missing ~/.claude/rules file", lambda: append(S_AUD, "\nSee `~/.claude/rules/claude-eng-extra.md`.\n")),
]

restore()
base = subprocess.run([sys.executable, "-I", str(Q / "tools/build_harness.py"), "--check"], capture_output=True, encoding="utf-8", errors="replace")
print(f"baseline exit={base.returncode} :: {base.stdout.strip().splitlines()[-1]}")
caught = escaped = setup = 0
for name, fn in MUTANTS:
    restore()
    try:
        fn()
    except AssertionError as e:
        print(f"SETUP-ERROR | {name} | {e}")
        setup += 1
        continue
    r = subprocess.run([sys.executable, "-I", str(Q / "tools/build_harness.py"), "--check"], capture_output=True, encoding="utf-8", errors="replace")
    verdict = "caught" if r.returncode else "ESCAPED"
    caught += verdict == "caught"
    escaped += verdict != "caught"
    first = next((l for l in r.stdout.splitlines() if l.startswith("LINT FAIL")), r.stderr.strip()[-160:] or "-")
    print(f"{verdict:8s} | exit={r.returncode} | {name} | {first[:150]}")
restore()
print(f"\n{caught} caught, {escaped} escaped, {setup} not run (setup errors), of {len(MUTANTS)}")
sys.exit(1 if setup else 0)  # a mutant that cannot run is "not run", never a pass
