"""Break each guard in the two skill scripts, one at a time, in a fresh scratch copy; the suite must fail.

Usage: python -I tools/mutation/mutate_skill_scripts.py <project folder (read only)> <new work folder outside the project>
"""
import pathlib
import shutil
import subprocess
import sys

try:  # a FAIL line may contain non-ASCII; never crash the report on a cp1252 console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

SRC = pathlib.Path(sys.argv[1])          # the real project (read only)
WORK = pathlib.Path(sys.argv[2])         # a new folder that must not exist yet
if WORK.exists():
    sys.exit(f"{WORK} already exists; pass a new folder")
if any(p == SRC.resolve() for p in [WORK.resolve(), *WORK.resolve().parents]):
    sys.exit("Refusing to run: the work folder must be outside the project.")
SCAN = "harness/skills/claude-eng-audit/scripts/secrets_scan.py"
HOOK = "harness/skills/claude-eng-setup/scripts/test_hook.py"
MUTANTS = [
    ("tracked files in skipped folders not scanned", SCAN, "    for repo, tracked in (repos or {}).items():", "    for repo, tracked in {}.items():"),
    ("outermost repo wins instead of nearest", SCAN, "key=lambda r: len(r.parts))", "key=lambda r: -len(r.parts))"),
    ("UTF-16 not decoded", SCAN, 'if data[:2] in (b"\\xff\\xfe", b"\\xfe\\xff"):', "if False:"),
    ("secret printed in full", SCAN, 'return f"**** ({len(value)} chars)"', "return value"),
    ("PostToolUse treated as able to block", HOOK, 'CAN_BLOCK = {"PreToolUse"}', 'CAN_BLOCK = {"PreToolUse", "PostToolUse"}'),
    ("could-not-start check removed", HOOK, "    if returncode != 0 and COULD_NOT_START.search(stderr):", "    if False:"),
    ("WSL launcher check removed", HOOK, '        if os.name == "nt" and WSL_LAUNCHER.search(exe):', "        if False:"),
    ("onFailure ignored", HOOK, '        if failed and h.get("onFailure") == "block":', "        if False:"),
    ("onFailure on PostToolUse acts as a block", HOOK, '            if name in CAN_BLOCK:\n                outcome, detail = "block"', '            if True:\n                outcome, detail = "block"'),
    ("out-of-scope events guessed instead of refused", HOOK, "    if name not in SUPPORTED:", "    if False:"),
    ("unquoted values in code flagged", SCAN, "            if not in_string[m.start(1)]:\n                continue", "            if False:\n                continue"),
    ("string state inverted", SCAN, "            if not in_string[m.start(1)]:", "            if in_string[m.start(1)]:"),
    ("source line printed with each finding", SCAN, 'value {mask(value)}  [{status}]")', 'value {mask(value)}  [{status}]  {line}")'),
    ("staged copies not scanned", SCAN, "    for repo in [r for r, tracked in (repos or {}).items() if tracked is not None]:", "    for repo in []:"),
    ("skipped folders not listed", SCAN, "        if files:", "        if False:"),
    ("first characters of a value shown", SCAN, 'return f"**** ({len(value)} chars)"', 'return f"{value[:4]}... ({len(value)} chars)"'),
    ("skipped files do not affect the exit code", SCAN, "or tracked_sensitive or skipped or unscanned else 0", "or tracked_sensitive or unscanned else 0"),
    ("unscanned skipped folders do not affect the exit code", SCAN, "or tracked_sensitive or skipped or unscanned else 0", "or tracked_sensitive or skipped else 0"),
    ("if condition ignored", HOOK, '    if handler.get("if"):', "    if False:"),
    ("async hooks run as if synchronous", HOOK, '    if handler.get("async") or handler.get("asyncRewake"):', "    if False:"),
    ("disableAllHooks ignored", HOOK, 'disabled = config.get("disableAllHooks") is True', "disabled = False"),
    ("hookEventName not checked", HOOK, '        if hso.get("hookEventName") != event_name:', "        if False:"),
    ("continue: false ignored", HOOK, '    if obj.get("continue") is False:', "    if False:"),
    ("output schema not validated", HOOK, 'problem = obj if kind == "bad" else (schema_problem(obj, event_name) if kind == "json" else None)',
     'problem = obj if kind == "bad" else None'),
    ("JSON ignored on other exit codes", HOOK, "    if kind == \"json\":\n        outcome, why = from_fields(obj, event_name)",
     "    if kind == \"json\" and not other_exit:\n        outcome, why = from_fields(obj, event_name)"),
    ("JSON followed by text parsed as JSON", HOOK, '    if not (s.startswith("{") and s.endswith("}")):', '    if not s.startswith("{"):'),
    ("other settings files ignored", HOOK, "    for other in other_settings(root, settings):", "    for other in []:"),
    ("non-command handlers skipped silently", HOOK, "    if others:", "    if False:"),
    ("non-boolean async accepted", HOOK, "        if f in handler and not isinstance(handler[f], bool):", "        if False:"),
    ("non-boolean disableAllHooks accepted", HOOK, '    if "disableAllHooks" in config and not isinstance(config["disableAllHooks"], bool):', "    if False:"),
    ("permissionDecision values not checked", HOOK, '        if "permissionDecision" in hso and hso["permissionDecision"] not in DECISIONS:', "        if False:"),
    ("field types not checked", HOOK, "    for f in BOOL_FIELDS:\n        if f in obj and not isinstance(obj[f], bool):", "    for f in BOOL_FIELDS:\n        if False:"),
    ("stop ranked below block", HOOK, '("stop", "block", "ask", "feedback", "allow")', '("block", "stop", "ask", "feedback", "allow")'),
    ("shell scripts treated as code again", SCAN, '".rs", ".kt", ".swift", ".c", ".cpp", ".h"}', '".rs", ".kt", ".swift", ".c", ".cpp", ".h", ".sh"}'),
    ("overlapping matches reported twice", SCAN, "            if overlaps(*m.span()) or (filtered and placeholder(value)):",
     "            if filtered and placeholder(value):"),
    ("placeholder filter applied to cracked passwords", SCAN,
     r'(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32}):(\S.*?)\s*$", re.M), False, None)',
     r'(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32}):(\S.*?)\s*$", re.M), True, None)'),
    ("placeholder words matched as prefixes", SCAN, r'|x{3,}|\*{3,}|your[_-][\w-]*|[\w-]*[_-]here)$")', r'|x{3,}|\*{3,}|your[_-][\w-]*|[\w-]*[_-]here)")'),
    ("-p flagged without -u/-l or sshpass on the line", SCAN, r're.compile(r"(?:^|\s)-[ulU](?:\s+|(?=\S))\S|\bsshpass\b")),', "None),"),
    ("ports after -p flagged as passwords", SCAN, r"""(?!\d{1,5}(?:[\s\"']|$))""", ""),
    ("any pyvenv.cfg hides a folder", SCAN, '    cfg = folder / "pyvenv.cfg"\n', '    return (folder / "pyvenv.cfg").exists()\n'),
    ("a file outside the project crashes the scan", SCAN, "        if not (path == root or root in path.parents):", "        if False:"),
    ("unreadable git reported as clean", SCAN, "    if repos is None and has_git_dir(root):", "    if False:"),
    # R01: one unreadable repository must not hide the others
    ("one unreadable repository hides every staged copy", SCAN,
     "            continue  # stays None: this repository is unreadable; main() reports it, the others are still scanned", "            return None"),
    ("unreadable repository not reported", SCAN, "    for repo in sorted(r for r, tracked in (repos or {}).items() if tracked is None):", "    for repo in []:"),
    ("files in an unreadable repository crash the scan", SCAN,
     '    if repos[repo] is None:\n        return "git status unknown (repository unreadable)"\n', ""),
    # R02: an unscanned binary file is an unscanned file
    ("binary file does not make the scan incomplete", SCAN,
     '            binary += 1\n            skipped += 1\n            print(f"SKIPPED  {rel}  binary file (contains NUL bytes), not scanned  [{status}]")',
     "            binary += 1"),
    ("staged binary does not make the scan incomplete", SCAN,
     '                binary += 1\n                skipped += 1\n                print(f"SKIPPED  {rel}  binary file (contains NUL bytes), not scanned  [STAGED in git]")',
     "                binary += 1"),
    # R10: bounded work and an explicit result when the limit is reached
    ("scan time limit ignored", SCAN, "        if time.monotonic() > deadline:", "        if False:"),
    ("a scan that ran out of time is not counted", SCAN,
     '        if not complete:\n            skipped += 1\n            print(f"SKIPPED  {rel}  scan stopped', '        if False:\n            skipped += 1\n            print(f"SKIPPED  {rel}  scan stopped'),
    ("assignment name unbounded", SCAN, r"([a-z0-9_.-]{0,60}(?:api", r"([a-z0-9_.-]*(?:api"),
    ("assignment pre-check removed", SCAN, "if CREDENTIAL_WORD.search(line) else ()", "if True else ()"),
    ("URL scheme unbounded", SCAN, r"\b[a-z][a-z0-9+.-]{0,40}://", r"\b[a-z][a-z0-9+.-]*://"),
    ("NetNTLM names unbounded", SCAN, r"[^:\s]{1,256}::[^:\s]{1,256}:([a-fA-F0-9]{16}:", r"[^:\s]+::[^:\s]+:([a-fA-F0-9]{16}:"),
    ("string state recomputed for every match", SCAN,
     "            if in_string is None:\n                in_string = string_state(line)", "            if True:\n                in_string = string_state(line)"),
    ("long lines scanned in one piece", SCAN, "    if len(line) <= CHUNK:", "    if True:"),
    # R03-R05: hook tester
    ("leftover process ignored", HOOK, '    if outcome not in ("block", "stop", "error"):\n        if leftover is None:',
     '    if False:\n        if leftover is None:'),
    ("a block printed before a leftover process not kept", HOOK, 'if outcome not in ("block", "stop", "error"):', 'if outcome not in ("stop", "error"):'),
    ("leftover processes not ended", HOOK, "        finally:\n            group.end(proc)", "        finally:\n            pass"),
    ("deprecated PreToolUse decision ignored", HOOK, 'legacy = {"approve": "allow", "block": "deny"}.get(obj.get("decision"))', "legacy = None"),
    ("conflicting decisions not an error", HOOK, "            if decision is not None and legacy is not None and decision != legacy:", "            if False:"),
]
ONLY = sys.argv[3:]                      # optional: run only mutants whose name contains one of these words
TIMEOUT = 900                            # a mutant that hangs the suite counts as caught
caught = ran = 0
for i, (name, rel, old, new) in enumerate(MUTANTS, 1):
    if ONLY and not any(word in name for word in ONLY):
        continue
    ran += 1
    d = WORK / str(i)
    for sub in ("harness", "kb", "tools"):  # the skill-script tests do not need source/
        shutil.copytree(SRC / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    p = d / rel
    t = p.read_text(encoding="utf-8")
    if t.count(old) != 1:
        print(f"NOT RUN  | {name} | target found {t.count(old)} times")
        continue
    p.write_text(t.replace(old, new), encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "-I", str(d / "tools/test_harness_scripts.py")], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"caught   | {name} | the suite did not finish in {TIMEOUT} seconds", flush=True)
        caught += 1
        shutil.rmtree(d, ignore_errors=True)
        continue
    fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
    verdict = "caught" if r.returncode else "ESCAPED"
    caught += r.returncode != 0
    print(f"{verdict:8s} | {name} | {len(fails)} failing: " + (" ## ".join(f[6:90] for f in fails[:4]) if fails else '-'), flush=True)
    shutil.rmtree(d, ignore_errors=True)  # each copy is ~10 MB; keep the disk clear
print(f"\n{caught} of {ran} caught")
