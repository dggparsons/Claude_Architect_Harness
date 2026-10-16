"""Break each guard added to the doctor and the installer after the team audit, one at a time, in a fresh
scratch copy; the suite must fail.

Usage: python -I tools/mutation/mutate_doctor_installer.py <project folder (read only)> <new work folder outside the project>

Not mutated, by design (equivalent or untestable from outside):
- the second unsafe-path check inside install()/uninstall(): load_manifest() refuses the same paths first,
  so removing either one alone is caught by neither test (defence in depth);
- the status check at the end of install(): after a successful copy the result always matches the source;
- the atomic manifest write: a failure inside the rename cannot be forced from a test without patching os.
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
DOC = "harness/skills/claude-eng-doctor/scripts/doctor.py"
INST = "tools/install_harness.py"
BUILD = "tools/build_harness.py"
MUTANTS = [
    ("doctor checks only owned files, not the inventory", DOC,
     '    files = data.get("inventory") or data.get("files", {})', '    files = data.get("files", {})'),
    ("doctor passes an empty manifest", DOC, '    if not files:\n        report("FAIL"', '    if False:\n        report("FAIL"'),
    ("doctor accepts a manifest of the wrong shape", DOC,
     "    if not isinstance(data, dict) or not isinstance(", "    if False and not isinstance(data, dict) or False and not isinstance("),
    ("doctor trusts .gitignore text instead of git", DOC,
     'git(project, "check-ignore", "-q", "--no-index", probe) is None', "False"),
    ("doctor ignores local files git already tracks", DOC, "    if tracked:", "    if False:"),
    ("installer accepts a path outside the config folder", INST,
     '    except ValueError:\n        return f"is outside {root}"', '    except ValueError:\n        return None'),
    ("installer accepts paths outside rules/agents/skills", INST,
     "    if len(rel.parts) < 2 or rel.parts[0] not in PAYLOAD_DIRS:", "    if False:"),
    ("installer copies straight onto the destination", INST,
     '        shutil.copy2(src, tmp)\n        if sha(tmp) != sha(src):\n            raise OSError(f"copy of {src} to {tmp} does not match the source")\n        os.replace(tmp, dst)',
     "        shutil.copy2(src, dst)"),
    ("installer leaves its temporary file behind", INST,
     'does not match the source")\n        os.replace(tmp, dst)\n    finally:\n        tmp.unlink(missing_ok=True)',
     'does not match the source")\n        os.replace(tmp, dst)\n    finally:\n        pass'),
    ("retired files never removed", INST, '            if how == "remove":', "            if False:"),
    ("retired files removed without a backup", INST,
     "                    backup(t, bdir)\n                    t.unlink()", "                    t.unlink()"),
    ("edited retired files removed without --force", INST, "        elif sha(t) == owned[path_s] or force:", "        elif True:"),
    ("kept retired files reported as success", INST, "    if kept_stale:\n        sys.exit(", "    if False:\n        sys.exit("),
    ("manifest keys not normalised (two spellings of one folder)", INST, "    return os.path.normcase(os.path.realpath(p))", "    return str(p)"),
    ("config folder not resolved", INST,
     'CLAUDE = pathlib.Path(os.path.realpath(os.path.abspath(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")))',
     'CLAUDE = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")'),
    ("destinations not checked before writing", INST, "    if unsafe:\n        for u in unsafe:", "    if False:\n        for u in unsafe:"),
    ("folders accepted as manifest entries", INST, "    if p.exists() and not p.is_file():", "    if False:"),
    ("fixed temporary file name", INST,
     '    fd, name = tempfile.mkstemp(dir=dst.parent, prefix="." + dst.name + ".", suffix=".claude-eng-tmp")\n    os.close(fd)\n    return pathlib.Path(name)',
     '    return dst.with_name(dst.name + ".claude-eng-tmp")'),
    ("a failed retirement crashes", INST, "                except OSError as exc:", "                except ZeroDivisionError as exc:"),
    ("doctor ignores its required list", DOC, "    if absent:", "    if False:"),
    ("doctor accepts entries outside the config folder", DOC, "    if outside:", "    if False:"),
    ("doctor reports unreadable git as no repository", DOC, '        if any((d / ".git").exists() for d in [project, *project.parents]):', "        if False:"),
    ("doctor accepts personal ignore files", DOC, "    if personal:", "    if False:"),
    ("doctor passes an older manifest without a warning", DOC, 'report("WARN", "harness", "manifest from an older installer', 'report("INFO", "harness", "manifest from an older installer'),
    ("lint ignores the case of skill-folder paths", BUILD, "not exact_case_exists(spelt)", "not spelt.exists()"),
    ("lint accepts paths the installer never copies", BUILD, " or not installed(target):", ":"),
    ("lint accepts a required script that does not compile", BUILD, '                compile(code, str(sp), "exec")', "                pass"),
    ("lint accepts a required script with no entry point", BUILD, """            if 'if __name__ == "__main__":' not in code:""", "            if False:"),
    ("lint bans only the ~ spelling of hard-coded paths", BUILD, r'(?:~|\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE)', r'(?:~)'),
    # R06, R07: the doctor reads the whole inventory and the retired files
    ("doctor accepts a manifest that omits required files", DOC, "        if uncovered:", "        if False:"),
    ("doctor accepts an empty required file", DOC, "    if empty:", "    if False:"),
    ("doctor ignores a retired file that is still installed", DOC, "        if retired:", "        if False:"),
    ("lint does not compare the doctor's list with harness/", BUILD, "        elif required != payload:", "        elif False:"),
    # R08: quoted script paths
    ("lint accepts an unquoted skill-folder script path", BUILD,
     """        for _ in re.finditer(r'(?<!")\\$\\{CLAUDE_SKILL_DIR\\}/scripts/', body):""", "        for _ in []:"),
    # R09: links inside a payload folder
    ("installer follows a link inside a payload folder", INST, "        if redirected(folder):", "        if False:"),
    # two installs in one second share a backup folder
    ("a second backup in the same second overwrites the first", INST, "    while dest.exists():", "    while False:"),
]
ONLY = sys.argv[3:]                      # optional: run only mutants whose name contains one of these words
TIMEOUT = 900                            # a mutant that hangs the suite counts as caught
caught = ran = 0
for i, (name, rel, old, new) in enumerate(MUTANTS, 1):
    if ONLY and not any(word in name for word in ONLY):
        continue
    ran += 1
    d = WORK / str(i)
    for sub in ("harness", "kb", "tools"):  # these tests do not need source/
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
    shutil.rmtree(d, ignore_errors=True)  # keep the disk clear
print(f"\n{caught} of {ran} caught")
