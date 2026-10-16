"""Build the harness from source and lint it.

Usage:  python -I tools/build_harness.py          build references, then lint
        python -I tools/build_harness.py --check  lint only, including "references match kb/"

Build: generates harness/skills/claude-engineering/references/ from kb/:
- each kb/domain-*.md, minus its build-time sections (claims to verify, harness mapping,
  capture quality), which are about producing the harness rather than standards to follow;
- kb/claude-code-current-spec.md as is;
- verification.md: kb/verification/domain-N.md joined, minus internal QA sections.
The new set is written to a staging folder and swapped in only when complete, so a failed
build never leaves a half-written references folder.

Lint (exits non-zero on any failure):
- frontmatter is a strict, simple YAML subset (no BOM, closed '---', 'key: value' or
  'key:' with '- item' lines, plain values free of ': ' and ' #'); rules, skills, agents
- skill name matches folder; description present; description + when_to_use <= 1,536 chars;
  SKILL.md under 500 lines; side-effect skills have disable-model-invocation: true
- always-on rule under 50 lines; path-scoped rule has a paths list
- references contain no project-only pointers (kb/, harness/, source/, _project/, "DECISION: Dave")
- every reference SKILL.md names exists, and every reference file is named
- agents: name matches file; tools listed and known; reviewers limited to read-only tools
  (Read, Grep, Glob, WebFetch, WebSearch), plus Bash/PowerShell for reviewer-end-user only;
  model value valid; preloaded skills exist
- frontmatter keys limited to an allowlist per file type; the knowledge skill stays auto-loadable
- cross-references: reviewer agents, ~/.claude/rules files and references named in any skill,
  rule or agent exist in the harness
- no placeholders and nothing that looks like a secret, in any harness file
- with --check: references on disk equal a fresh build from kb/
"""
import argparse
import ast
import os
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KB = ROOT / "kb"
H = ROOT / "harness"
REFS = H / "skills" / "claude-engineering" / "references"

SECRET = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}|Bearer [A-Za-z0-9._-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abposr]-[A-Za-z0-9-]{10,}"
    r"|(api[_-]?key|apikey|secret|token|passw(or)?d|_key)[\"']?\s*[:=]\s*[\"']?(?![$]|os\.environ|process\.env)[A-Za-z0-9_\-./+=]{16,})", re.I)
PLACEHOLDER = re.compile(r"\b(TODO|TBC|TBD|FIXME|XXX)\b|lorem ipsum|<insert[^>]*>|\[insert[^\]]*\]", re.I)
PLACEHOLDER_OK = re.compile(r"placeholders? \(TODO|^Status: todo ·", re.I)  # a reviewer told to look for them; the plan template's status key
BUILD_ONLY = re.compile(r"^(\d+\.\s*)?(Specific technical claims|Harness mapping|Capture quality)", re.I)
INTERNAL_QA = re.compile(r"^(Rules file check|Notes on `kb/)", re.I)
KNOWN_TOOLS = {"Read", "Grep", "Glob", "WebFetch", "WebSearch", "Bash", "PowerShell", "Edit", "Write",
               "NotebookEdit", "Agent", "Skill", "TodoWrite"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
COMMAND_TOOLS = {"Bash", "PowerShell"}
READ_ONLY_TOOLS = {"Read", "Grep", "Glob", "WebFetch", "WebSearch"}  # no Agent/Skill: a spawned agent could edit
ALLOWED_KEYS = {
    "rules": {"paths"},
    "skills": {"name", "description", "when_to_use", "argument-hint", "disable-model-invocation", "user-invocable"},
    "agents": {"name", "description", "tools", "model", "skills"},
}
MODELS = {"inherit", "sonnet", "opus", "haiku", "fable"}
MANUAL_SKILLS = {"claude-eng-setup", "claude-eng-audit"}
EXPECTED_SKILLS = MANUAL_SKILLS | {"claude-engineering", "claude-eng-doctor"}
ALWAYS_ON_LIMIT = 50
EXPECTED_RULES = {"claude-engineering.md": False, "claude-code-config.md": True}  # name -> path-scoped?
EXPECTED_SCRIPTS = {"claude-eng-audit": ("secrets_scan.py",), "claude-eng-setup": ("test_hook.py",),
                    "claude-eng-doctor": ("doctor.py",)}
PROJECT_ONLY = re.compile(r"(`|\b)(kb|harness|source)/[A-Za-z0-9_.-]|DECISION: Dave")  # _project/ is a target-project folder


# ---------------------------------------------------------------- build
def split_sections(text):
    """Yield (heading_text or None, block_text) for each level-2 section."""
    current, buf = None, []
    for line in text.splitlines():
        if line.startswith("## "):
            yield current, buf
            current, buf = line[3:].strip(), [line]
        else:
            buf.append(line)
    yield current, buf


def without(text, pattern):
    keep = []
    for heading, block in split_sections(text):
        if heading is None or not pattern.match(heading):
            keep.extend(block)
    return "\n".join(keep).rstrip() + "\n"


def expected_references():
    """Return {file name: content} for a fresh build from kb/. Exits on missing or unready source."""
    out = {}
    domains = sorted(KB.glob("domain-*.md"))
    if len(domains) != 5:
        sys.exit(f"BUILD FAIL: expected 5 domain files in kb/, found {len(domains)}")
    for f in domains:
        text = f.read_text(encoding="utf-8")
        if "corrections applied inline" not in text[:3000]:
            sys.exit(f"BUILD FAIL: {f.name} header does not say corrections were applied inline")
        out[f.name] = without(text, BUILD_ONLY)
    spec = KB / "claude-code-current-spec.md"
    out[spec.name] = spec.read_text(encoding="utf-8")
    practice = KB / "working-practice.md"
    out[practice.name] = practice.read_text(encoding="utf-8")
    ver = sorted((KB / "verification").glob("domain-[1-5].md"))
    if len(ver) != 5:
        sys.exit(f"BUILD FAIL: expected 5 kb/verification/domain-N.md files, found {len(ver)}")
    parts = ["# Verification of guide claims against Anthropic's docs",
             "Each domain's technical claims were checked against official docs on 2026-10-14. "
             "The domain references already include these corrections; this file holds the evidence.", ""]
    for f in ver:
        parts += [without(f.read_text(encoding="utf-8"), INTERNAL_QA).rstrip(), ""]
    out["verification.md"] = "\n".join(parts)
    return out


def build():
    refs = expected_references()
    stage = REFS.parent / ".references.staging"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name, content in refs.items():
        (stage / name).write_text(content, encoding="utf-8")
    old = REFS.parent / ".references.old"
    if old.exists():
        shutil.rmtree(old)
    if REFS.exists():
        os.replace(REFS, old)
    os.replace(stage, REFS)
    if old.exists():
        shutil.rmtree(old)
    print(f"built {len(refs)} reference files")


# ---------------------------------------------------------------- lint
def frontmatter(path, errors):
    """Strict parse of a simple YAML frontmatter block. Returns dict, or None if there is none."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append(f"{rel(path)}: starts with a byte-order mark")
        raw = raw[3:]
    text = raw.decode("utf-8")
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if lines[0] != "---":
        errors.append(f"{rel(path)}: opening '---' line has extra characters")
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        errors.append(f"{rel(path)}: frontmatter has no closing '---'")
        return {}
    fm, current = {}, None
    for n, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        if "\t" in line:
            errors.append(f"{rel(path)}:{n}: tab in frontmatter")
            continue
        item = re.match(r"^  - (.+)$", line)
        if item:
            if current is None or not isinstance(fm.get(current), list):
                errors.append(f"{rel(path)}:{n}: list item without a list key")
                continue
            fm[current].append(scalar(item.group(1), path, n, errors))
            continue
        kv = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):(?: (.*))?$", line)
        if not kv:
            errors.append(f"{rel(path)}:{n}: not 'key: value' or '  - item': {line!r}")
            continue
        current = kv.group(1)
        if current in fm:
            errors.append(f"{rel(path)}:{n}: duplicate key {current!r}")
        value = (kv.group(2) or "").strip()
        fm[current] = [] if value == "" else scalar(value, path, n, errors)
    return fm


def scalar(value, path, n, errors):
    if value[0] in "\"'":
        q = value[0]
        if len(value) < 2 or value[-1] != q:
            errors.append(f"{rel(path)}:{n}: unterminated quoted value")
            return value
        if value[1:-1].lower() in ("true", "false"):
            errors.append(f"{rel(path)}:{n}: quoted boolean {value} is a string, not true/false")
        return value[1:-1]
    if value[0] in "[{&*!|>%@`#" or ": " in value or " #" in value:
        errors.append(f"{rel(path)}:{n}: plain value needs quoting: {value[:60]!r}")
    return value


def tool_list(value):
    if isinstance(value, list):
        return [v.strip() for v in value if v.strip()]
    return [t for t in re.split(r"[,\s]+", value or "") if t]


def rel(p):
    return p.relative_to(ROOT).as_posix()


def exact_case_exists(path):
    """True if path exists with exactly this spelling of every part (Windows ignores case; other systems do not)."""
    path = pathlib.Path(path)
    for part_path in [*reversed(path.parents), path]:
        parent = part_path.parent
        if part_path == parent:
            continue
        try:
            if part_path.name not in os.listdir(parent):
                return False
        except OSError:
            return False
    return True


def installed(path):
    """True if the harness file or folder at path is one the installer copies (rules/*.md, agents/*.md, skill files)."""
    rel = pathlib.Path(path).resolve().relative_to(H.resolve())
    if rel.parts[0] in ("rules", "agents"):
        return len(rel.parts) == 1 or (len(rel.parts) == 2 and rel.suffix == ".md")
    return rel.parts[0] == "skills" and "__pycache__" not in rel.parts and not any(
        part.startswith(".references.") for part in rel.parts)


def lint(check_stale):
    errors = []

    def err(path, msg):
        errors.append(f"{rel(path)}: {msg}")

    files = [p for p in H.rglob("*") if p.is_file() and ".references." not in p.as_posix()]
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if PLACEHOLDER.search(line) and not PLACEHOLDER_OK.search(line):
                err(f, f"line {i}: placeholder {PLACEHOLDER.search(line).group(0)!r}")
            if SECRET.search(line):
                err(f, f"line {i}: looks like a secret")

    rules = sorted((H / "rules").glob("*.md"))
    found_rules = {r.name for r in rules} | {p.name for p in (H / "rules").iterdir() if p.is_file()}
    if found_rules != set(EXPECTED_RULES):
        errors.append(f"harness/rules: expected exactly {sorted(EXPECTED_RULES)}, found {sorted(found_rules)}")
    for f in rules:
        fm = frontmatter(f, errors)
        if f.name in EXPECTED_RULES and (fm is not None) != EXPECTED_RULES[f.name]:
            err(f, "must be path-scoped (have paths frontmatter)" if EXPECTED_RULES[f.name]
                else "must be always-on (no frontmatter): a paths list would stop it loading every session")
        lines = len(f.read_text(encoding="utf-8").splitlines())
        if fm is None and lines >= ALWAYS_ON_LIMIT:
            err(f, f"always-on rule is {lines} lines (limit {ALWAYS_ON_LIMIT})")
        if fm is not None and not (isinstance(fm.get("paths"), list) and fm["paths"]):
            err(f, "frontmatter present but no 'paths' list")

    skills = sorted((H / "skills").glob("*/SKILL.md"))
    found = {s.parent.name for s in skills}
    for d in sorted(p for p in (H / "skills").iterdir() if p.is_dir()):
        if not (d / "SKILL.md").is_file():
            err(d, "skill folder has no SKILL.md (the installer would ship it anyway)")
    if found != EXPECTED_SKILLS:
        errors.append(f"harness/skills: expected {sorted(EXPECTED_SKILLS)}, found {sorted(found)}")
    for s in skills:
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s.parent.name):
            err(s, "skill folder name must be lowercase letters, digits and hyphens")
    for f in skills:
        fm = frontmatter(f, errors)
        if not fm:
            err(f, "no frontmatter")
            continue
        name = f.parent.name
        if fm.get("name") != name:
            err(f, f"name {fm.get('name')!r} does not match folder {name!r}")
        if not fm.get("description"):
            err(f, "missing description")
        desc = str(fm.get("description") or "") + str(fm.get("when_to_use") or "")
        if len(desc) > 1536:
            err(f, f"description + when_to_use is {len(desc)} chars (limit 1536)")
        body = f.read_text(encoding="utf-8")
        # The project placeholder is replaced with the session's folder when the skill loads, so a hook example
        # written with it would carry an absolute path; the skill-folder placeholder is the documented way to
        # reach a skill's own files from any config folder.
        for token in re.findall(r"\$\{CLAUDE_PROJECT_DIR\}", body):
            err(f, f"contains {token}, which Claude Code replaces with a real path when the skill loads; describe it in words")
        # A config folder can contain spaces; unquoted, the shell splits the script path at the first one.
        for _ in re.finditer(r'(?<!")\$\{CLAUDE_SKILL_DIR\}/scripts/', body):
            err(f, "runs a script through an unquoted skill-folder path; put the whole path in double quotes "
                   "(the config folder can contain spaces)")
        for path in re.findall(r"(?:~|\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE)[\\/]\.claude[\\/](?:skills|rules|agents)[\\/][A-Za-z0-9_.\\/-]*", body):
            err(f, f"hard-codes {path}; use the skill-folder placeholder (CLAUDE_SKILL_DIR) so the skill works "
                   "from any config folder")
        # harness/ mirrors the installed layout (rules/, skills/<name>/, agents/), so each skill-folder path
        # can be resolved here exactly as it will resolve once installed.
        for skill_path in set(re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([A-Za-z0-9_./-]+)", body)):
            spelt = pathlib.Path(os.path.normpath(H / "skills" / name / skill_path.split("--")[0].rstrip(".-")))  # "x.py--it"
            target = spelt.resolve()  # on Windows this also corrects the case, so the case check uses the spelling
            if H.resolve() not in target.parents or not exact_case_exists(spelt) or not installed(target):
                err(f, f"mentions the skill-folder path {skill_path}, which does not exist once installed "
                       "(names must match exactly, including case)")
        for script in EXPECTED_SCRIPTS.get(name, ()):
            sp = f.parent / "scripts" / script
            if not sp.is_file():
                err(f, f"required script scripts/{script} is missing")
                continue
            code = sp.read_text(encoding="utf-8", errors="replace")
            try:
                compile(code, str(sp), "exec")
            except SyntaxError as exc:
                err(sp, f"required script does not compile ({exc.msg}, line {exc.lineno})")
            if 'if __name__ == "__main__":' not in code:
                err(sp, "required script has no main entry point (it would run as an empty, silent script)")
            elif f"scripts/{script}" not in body:
                err(f, f"never names its script scripts/{script}")
        if len(body.splitlines()) >= 500:
            err(f, f"SKILL.md is {len(body.splitlines())} lines (limit 500)")
        if name in MANUAL_SKILLS and fm.get("disable-model-invocation") != "true":
            err(f, "side-effect skill must set disable-model-invocation: true")
        if name not in MANUAL_SKILLS and ("disable-model-invocation" in fm or "user-invocable" in fm):
            err(f, "this read-only skill must stay auto-loadable (no disable-model-invocation / user-invocable)")
        if name in MANUAL_SKILLS and "user-invocable" in fm:
            err(f, "a manual-only skill must stay user-invocable (no user-invocable key)")
        extra = [p for p in f.parent.rglob("*") if p.is_file() and p != f and "__pycache__" not in p.parts
                 and not (p.parent.name == "references" and p.suffix == ".md")
                 and not (p.parent.name == "scripts" and p.suffix == ".py" and p.name in EXPECTED_SCRIPTS.get(name, ()))]
        for p in extra:
            err(p, "unexpected file in a skill folder (it would be installed)")
        refdir = f.parent / "references"
        if refdir.exists():
            named = set(re.findall(r"`references/([A-Za-z0-9_.-]+\.md)`", body))
            present = {p.name for p in refdir.glob("*.md")}
            for missing in sorted(named - present):
                err(f, f"names references/{missing}, which does not exist")
            for unnamed in sorted(present - named):
                err(f, f"references/{unnamed} exists but SKILL.md never names it")

    # The doctor checks every file the install should have; its list must match what the harness ships.
    doctor = H / "skills" / "claude-eng-doctor" / "scripts" / "doctor.py"
    if doctor.is_file():
        required = None
        try:
            for node in ast.parse(doctor.read_text(encoding="utf-8")).body:
                if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "REQUIRED" for t in node.targets):
                    required = set(ast.literal_eval(node.value))
        except (SyntaxError, ValueError):
            pass
        payload = {f.relative_to(H).as_posix() for f in H.rglob("*")
                   if f.is_file() and ".references." not in f.as_posix() and "__pycache__" not in f.parts}
        if required is None:
            err(doctor, "no readable REQUIRED list of installed files")
        elif required != payload:
            err(doctor, f"REQUIRED differs from the files under harness/: missing {sorted(payload - required)}, "
                        f"not shipped {sorted(required - payload)}")

    agents = sorted((H / "agents").glob("*.md"))
    if len(agents) != 4:
        errors.append(f"harness/agents: expected 4 agents, found {len(agents)}")
    skill_names = {s.parent.name for s in skills}
    for f in agents:
        fm = frontmatter(f, errors)
        if not fm:
            err(f, "no frontmatter")
            continue
        for key in ("name", "description", "tools"):
            if not fm.get(key):
                err(f, f"missing {key}")
        if fm.get("name") != f.stem:
            err(f, f"name {fm.get('name')!r} does not match file name")
        tools = set(tool_list(fm.get("tools")))
        if tools - KNOWN_TOOLS:
            err(f, f"unknown tools {sorted(tools - KNOWN_TOOLS)}")
        if tools & EDIT_TOOLS:
            err(f, f"reviewer has editing tools {sorted(tools & EDIT_TOOLS)}")
        allowed = READ_ONLY_TOOLS | (COMMAND_TOOLS if f.stem == "reviewer-end-user" else set())
        if tools - allowed - EDIT_TOOLS:
            err(f, f"reviewer has tools outside its allowlist {sorted(tools - allowed - EDIT_TOOLS)}")
        model = fm.get("model")
        if model and model not in MODELS:
            err(f, f"model {model!r} is not one of {sorted(MODELS)} (use an alias, not a full ID)")
        for s in fm.get("skills") or []:
            if s not in skill_names:
                err(f, f"preloads unknown skill {s!r}")

    agent_names = {a.stem for a in agents}
    rule_names = {r.name for r in rules}
    ref_names = {p.name for p in REFS.glob("*.md")} if REFS.exists() else set()
    for f in rules + skills + agents:
        text = f.read_text(encoding="utf-8")
        for a in set(re.findall(r"\b(reviewer-[a-z]+(?:-[a-z]+)*)\b", text)):
            if a not in agent_names:
                err(f, f"mentions agent {a!r}, which does not exist")
        for r in set(re.findall(r"~/\.claude/rules/([A-Za-z0-9_.-]+\.md)", text)):
            if r not in rule_names:
                err(f, f"mentions ~/.claude/rules/{r}, which does not exist")
        for r in set(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", text)):
            if r not in ref_names:
                err(f, f"mentions references/{r}, which does not exist")
        for s in set(re.findall(r"~/\.claude/skills/([A-Za-z0-9_-]+)", text)):
            if s not in skill_names:
                err(f, f"mentions ~/.claude/skills/{s}, which does not exist")
        for s in set(re.findall(r"(?<![\w./~-])/(claude-[a-z0-9]+(?:-[a-z0-9]+)*)(?![\w<-])", text)):
            if s not in skill_names:
                err(f, f"mentions /{s}, which is not one of the harness skills")

    for p in sorted(REFS.glob("*.md")) if REFS.exists() else []:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            m = PROJECT_ONLY.search(line)
            if m:
                err(p, f"line {i}: project-only pointer {m.group(0)!r} will not resolve once installed")

    if check_stale:
        expected = expected_references()
        on_disk = {p.name: p.read_text(encoding="utf-8") for p in REFS.glob("*.md")} if REFS.exists() else {}
        for name in sorted(set(expected) | set(on_disk)):
            if expected.get(name) != on_disk.get(name):
                errors.append(f"references/{name}: out of date with kb/ (run: python -I tools/build_harness.py)")

    for kind, group in (("rules", rules), ("skills", skills), ("agents", agents)):
        for f in group:
            fm = frontmatter(f, []) or {}
            for key in sorted(set(fm) - ALLOWED_KEYS[kind]):
                err(f, f"frontmatter key {key!r} is not in the allowlist for {kind}")

    for e in errors:
        print("LINT FAIL", e)
    print(f"lint: {len(rules)} rules, {len(skills)} skills, {len(agents)} agents, {len(errors)} errors")
    return not errors


def main():
    ap = argparse.ArgumentParser(description="Build the harness references from kb/ and lint the harness.")
    ap.add_argument("--check", action="store_true", help="lint only (no writes), including stale-reference check")
    args = ap.parse_args()
    if not args.check:
        build()
    sys.exit(0 if lint(check_stale=True) else 1)


if __name__ == "__main__":
    main()
