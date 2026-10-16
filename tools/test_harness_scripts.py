"""Prove the build and install guards work, without touching the real ~/.claude.

Usage:  python -I tools/test_harness_scripts.py

Copies harness/, kb/ and tools/ to a temporary folder and runs every scenario there, with
CLAUDE_CONFIG_DIR pointing at a temporary config folder. Prints PASS/FAIL per scenario and exits
non-zero if any scenario fails.
"""
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

try:  # a FAIL line may contain non-ASCII; never crash the report on a cp1252 console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass
results = []
skipped = []
# The scraped study-guide copy is private and may be absent (for example in a public copy).
HAVE_SOURCE = (ROOT / "source").is_dir()


def run(work, cfg, *args):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(cfg))
    return subprocess.run([sys.executable, "-I", *args], cwd=work, env=env, capture_output=True,
                          encoding="utf-8", errors="replace")


def nk(p):
    """The installer's manifest key for a path (resolved, and case-folded on Windows)."""
    return os.path.normcase(os.path.realpath(p))


def run_env(work, env_extra, *args):
    return subprocess.run([sys.executable, "-I", *args], cwd=work, env=dict(os.environ, **env_extra),
                          capture_output=True, encoding="utf-8", errors="replace")


def make_link(link, target):
    """A directory link: a junction on Windows (no admin rights needed), a symlink elsewhere. True if made."""
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        return r.returncode == 0
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))


def skip(count, why):
    skipped.append((count, why))
    print(f"SKIPPED  {count} {why}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        work = tmp / "project"
        for d in ("harness", "kb", "tools") + (("source",) if HAVE_SOURCE else ()):
            shutil.copytree(ROOT / d, work / d, ignore=shutil.ignore_patterns("__pycache__"))
        cfg = tmp / "claude"
        cfg.mkdir()
        inst = ["tools/install_harness.py"]
        build = ["tools/build_harness.py"]
        manifest = cfg / "claude-eng-harness.manifest.json"
        rule = cfg / "rules" / "claude-engineering.md"

        r = run(work, cfg, *build, "--check")
        check("lint passes on the current harness", r.returncode == 0, r.stdout[-300:])

        orphan = work / "harness" / "skills" / "orphan-skill"
        orphan.mkdir()
        (orphan / "notes.md").write_text("no SKILL.md here\n", encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint fails on a skill folder with no SKILL.md", r.returncode != 0 and "no SKILL.md" in r.stdout, r.stdout[-300:])
        shutil.rmtree(orphan)
        setup_md = work / "harness" / "skills" / "claude-eng-setup" / "SKILL.md"
        good_setup = setup_md.read_text(encoding="utf-8")
        setup_md.write_text(good_setup + "\nRun $" + "{CLAUDE_PROJECT_DIR}/.claude/hooks/x.py\n", encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint fails when a SKILL.md contains a path placeholder Claude Code would substitute",
              r.returncode != 0 and "replaces with a real path" in r.stdout, r.stdout[-300:])
        setup_md.write_text(good_setup + "\nRun python ~/.claude/skills/claude-eng-setup/scripts/test_hook.py\n", encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint fails when a SKILL.md hard-codes a ~/.claude path to a harness file",
              r.returncode != 0 and "hard-codes ~/.claude/skills/" in r.stdout, r.stdout[-300:])
        setup_md.write_text(good_setup, encoding="utf-8")
        scan_src = work / "harness" / "skills" / "claude-eng-audit" / "scripts" / "secrets_scan.py"
        scan_keep = tmp / "secrets_scan.keep"
        shutil.move(str(scan_src), scan_keep)
        r = run(work, cfg, *build, "--check")
        check("lint fails when a skill's required script is missing (team audit F09)",
              r.returncode != 0 and "required script scripts/secrets_scan.py is missing" in r.stdout, r.stdout[-300:])
        shutil.move(str(scan_keep), scan_src)
        # Docs round 4 (adversarial R17-R19, R24): more ways a skill can name a file that will not be there.
        good_scan = scan_src.read_text(encoding="utf-8")
        for label, body, expect in (("is an empty file", "", "no main entry point"),
                                    ("does not compile", good_scan + "\ndef broken(:\n", "does not compile")):
            scan_src.write_text(body, encoding="utf-8")
            r = run(work, cfg, *build, "--check")
            check(f"lint fails when a skill's required script {label}", r.returncode != 0 and expect in r.stdout,
                  r.stdout[-300:])
        scan_src.write_text(good_scan, encoding="utf-8")
        for label, extra, expect in (
                ("hard-codes $HOME/.claude/skills/", "\nRun $HOME/.claude/skills/claude-eng-setup/scripts/test_hook.py\n",
                 "hard-codes"),
                ("hard-codes %USERPROFILE%\\.claude\\skills\\", "\nRun %USERPROFILE%\\.claude\\skills\\x\\y.py\n", "hard-codes"),
                ("names a skill-folder path with the wrong case", "\nRun ${CLAUDE_SKILL_DIR}/Scripts/Test_Hook.py\n",
                 "including case"),
                ("names a harness file the installer never copies", "\nSee ${CLAUDE_SKILL_DIR}/../../agents/notes.txt\n",
                 "does not exist once installed")):
            (work / "harness" / "agents" / "notes.txt").write_text("not installed\n", encoding="utf-8")
            setup_md.write_text(good_setup + extra, encoding="utf-8")
            r = run(work, cfg, *build, "--check")
            check(f"lint fails when a SKILL.md {label}", r.returncode != 0 and expect in r.stdout, r.stdout[-300:])
            (work / "harness" / "agents" / "notes.txt").unlink()
        setup_md.write_text(good_setup + "\nThe tester (\"${CLAUDE_SKILL_DIR}/scripts/test_hook.py--it runs hooks) is here.\n",
                            encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint accepts a skill-folder path run into a sentence with a dash", r.returncode == 0, r.stdout[-300:])
        # Redo audit R08: a script path through the skill-folder placeholder must be quoted (the folder can have spaces).
        setup_md.write_text(good_setup + "\nRun `python -I ${CLAUDE_SKILL_DIR}/scripts/test_hook.py --project x`\n", encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint fails on an unquoted skill-folder script path (R08)",
              r.returncode != 0 and "unquoted skill-folder path" in r.stdout, r.stdout[-300:])
        setup_md.write_text(good_setup + '\nRun `python -I "${CLAUDE_SKILL_DIR}/scripts/test_hook.py" --project x`\n', encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint accepts the same command with the path quoted (R08)", r.returncode == 0, r.stdout[-300:])
        # Redo audit R06: the doctor's list of installed files must match what harness/ ships.
        doc_py = work / "harness" / "skills" / "claude-eng-doctor" / "scripts" / "doctor.py"
        good_doc = doc_py.read_text(encoding="utf-8")
        doc_py.write_text(good_doc.replace('            "agents/reviewer-standards.md")', ")"), encoding="utf-8")
        r = run(work, cfg, *build, "--check")
        check("lint fails when the doctor's REQUIRED list leaves out a shipped file (R06)",
              r.returncode != 0 and "REQUIRED differs" in r.stdout and "reviewer-standards.md" in r.stdout, r.stdout[-300:])
        doc_py.write_text(good_doc, encoding="utf-8")
        setup_md.write_text(good_setup, encoding="utf-8")
        setup_md.write_text(good_setup, encoding="utf-8")

        r = run(work, cfg, *inst, "--unistall", "--apply")
        check("installer rejects a mistyped flag and writes nothing",
              r.returncode != 0 and not any(cfg.iterdir()), r.stderr[-200:])

        r = run(work, cfg, *build, "--chek")
        check("build rejects a mistyped flag", r.returncode != 0)

        r = run(work, cfg, *inst)
        check("dry run writes nothing", r.returncode == 0 and not (cfg / "rules").exists(), r.stdout[-300:])

        (cfg / "agents").mkdir()
        (cfg / "agents" / "reviewer-facts.md").write_text("someone else's agent\n", encoding="utf-8")
        r = run(work, cfg, *inst, "--apply")
        check("a file not installed by the harness blocks the install",
              r.returncode != 0 and "BLOCKED" in r.stdout and not rule.exists(), r.stdout[-300:])
        (cfg / "agents" / "reviewer-facts.md").unlink()

        shutil.copy2(work / "harness" / "agents" / "reviewer-consistency.md", cfg / "agents" / "reviewer-consistency.md")
        r = run(work, cfg, *inst, "--apply")
        files = json.loads(manifest.read_text(encoding="utf-8"))["files"] if manifest.exists() else {}
        check("install applies", r.returncode == 0 and rule.exists(), r.stdout[-300:])
        check("an identical file that was already there is not adopted",
              len(files) > 0 and nk(cfg / "agents" / "reviewer-consistency.md") not in files
              and nk(rule) in files, sorted(files)[:3])

        r = run(work, cfg, *inst, "--status")
        check("status is clean after install", r.returncode == 0, r.stdout[-300:])

        r = run(work, cfg, *inst, "--status", "--uninstall")
        check("--status and --uninstall together are rejected", r.returncode == 2)
        r = run(work, cfg, *inst, "--status", "--apply")
        check("--status with --apply is rejected (status is read-only)", r.returncode == 2)

        agent_src = work / "harness" / "agents" / "reviewer-facts.md"
        agent_dst = cfg / "agents" / "reviewer-facts.md"
        old_agent = agent_src.read_text(encoding="utf-8")
        agent_src.write_text(old_agent.replace("You are an independent reviewer.", "You are an independent reviewer (v2)."),
                             encoding="utf-8")
        r = run(work, cfg, *inst, "--apply")
        backups = list((cfg / "backups").rglob("reviewer-facts.md")) if (cfg / "backups").exists() else []
        check("a source update replaces the installed file and backs up the old version",
              r.returncode == 0 and "(v2)" in agent_dst.read_text(encoding="utf-8")
              and any("(v2)" not in b.read_text(encoding="utf-8") for b in backups), r.stdout[-300:])
        agent_src.write_text(old_agent, encoding="utf-8")
        run(work, cfg, *inst, "--apply")

        rule.write_text(rule.read_text(encoding="utf-8") + "\nmy own edit\n", encoding="utf-8")
        r = run(work, cfg, *inst, "--status")
        check("status reports drift", r.returncode != 0 and "differs" in r.stdout)
        r = run(work, cfg, *inst, "--apply")
        check("an installed file edited by the user blocks reinstall (and is not mislabelled stale)",
              r.returncode != 0 and "changed after install" in r.stdout and "stale" not in r.stdout
              and "my own edit" in rule.read_text(encoding="utf-8"), r.stdout[-300:])
        r = run(work, cfg, *inst, "--apply", "--force")
        backups = list((cfg / "backups").rglob("claude-engineering.md")) if (cfg / "backups").exists() else []
        check("--force replaces it and keeps a backup",
              r.returncode == 0 and "my own edit" not in rule.read_text(encoding="utf-8")
              and any("my own edit" in b.read_text(encoding="utf-8") for b in backups))

        installed_before = sorted(p for p in cfg.rglob("*") if p.is_file() and "backups" not in p.parts)
        r = run(work, cfg, *inst, "--uninstall")
        installed_after = sorted(p for p in cfg.rglob("*") if p.is_file() and "backups" not in p.parts)
        check("uninstall without --apply deletes nothing", r.returncode == 0 and installed_before == installed_after,
              r.stdout[-300:])

        rule.write_text(rule.read_text(encoding="utf-8") + "\nedited again\n", encoding="utf-8")
        r = run(work, cfg, *inst, "--uninstall", "--apply")
        backed_up = list((cfg / "backups").rglob("claude-engineering/SKILL.md")) if (cfg / "backups").exists() else []
        check("uninstall backs up every file it removes", bool(backed_up), r.stdout[-300:])
        files = json.loads(manifest.read_text(encoding="utf-8"))["files"] if manifest.exists() else {}
        check("uninstall keeps an edited file and still lists it in the manifest",
              rule.exists() and nk(rule) in files and len(files) == 1, r.stdout[-300:])
        check("uninstall removes the unedited files",
              not (cfg / "skills" / "claude-engineering" / "SKILL.md").exists())
        check("uninstall leaves the pre-existing identical file alone",
              (cfg / "agents" / "reviewer-consistency.md").exists())
        r = run(work, cfg, *inst, "--uninstall", "--apply", "--force")
        check("uninstall --force removes the edited file and the manifest",
              not rule.exists() and not manifest.exists(), r.stdout[-300:])

        dom = work / "kb" / "domain-1-agentic-architecture.md"
        text = dom.read_text(encoding="utf-8")
        marker = "## 1.1"
        if marker in text:
            dom.write_text(text.replace(marker, "Inserted rule text, not yet built.\n\n" + marker, 1), encoding="utf-8")
            r = run(work, cfg, *build, "--check")
            check("--check catches references that are out of date with kb/",
                  r.returncode != 0 and "out of date" in r.stdout, r.stdout[-300:])
            r = run(work, cfg, *build)
            check("a rebuild brings them back in date", r.returncode == 0, r.stdout[-300:])
            dom.write_text(text, encoding="utf-8")
        else:
            check("stale-reference test could not find a module heading to edit (not run)", False, marker)

        cfg2 = tmp / "claude2"
        cfg2.mkdir()
        src_rule = work / "harness" / "rules" / "claude-engineering.md"
        good_rule = src_rule.read_text(encoding="utf-8")
        src_rule.write_text(good_rule + "\nTBD\n", encoding="utf-8")
        r = run(work, cfg2, *inst, "--apply")
        check("a failed build stops the install and writes nothing",
              r.returncode != 0 and not any(cfg2.iterdir()), r.stdout[-300:])
        src_rule.write_text(good_rule, encoding="utf-8")

        (cfg2 / "skills").write_text("a file where the skills folder should be\n", encoding="utf-8")
        r = run(work, cfg2, *inst, "--apply")
        m2 = cfg2 / "claude-eng-harness.manifest.json"
        recorded = json.loads(m2.read_text(encoding="utf-8"))["files"] if m2.exists() else {}
        copied = [p for p in (cfg2 / "rules").glob("*.md")] if (cfg2 / "rules").exists() else []
        check("a copy that fails part-way still saves the manifest for files already written",
              r.returncode != 0 and copied and all(nk(p) in recorded for p in copied),
              r.stdout[-200:] + r.stderr[-200:])

        hdr = text.replace("corrections applied inline", "corrections pending", 1)
        dom.write_text(hdr, encoding="utf-8")
        refs = sorted((work / "harness/skills/claude-engineering/references").glob("*.md"))
        before = {p.name: p.read_bytes() for p in refs}
        r = run(work, cfg, *build)
        after = {p.name: p.read_bytes() for p in sorted((work / "harness/skills/claude-engineering/references").glob("*.md"))}
        check("a failed build leaves the existing references untouched", r.returncode != 0 and before == after,
              r.stdout[-200:] + r.stderr[-200:])
        dom.write_text(text, encoding="utf-8")

        if HAVE_SOURCE:
            # Extractor baseline: the saved pages extract cleanly (so the failure tests below fail for their own reason).
            r = run(work, cfg, "tools/extract_study_data.py")
            check("extractor runs clean on the saved pages", r.returncode == 0 and "30 modules written, 0 failures" in r.stdout,
                  r.stdout[-300:])

            # Extractor: an empty field must fail the run and leave the saved study file unchanged.
            raw = work / "source" / "raw" / "1-1-agentic-loops.html"
            study = work / "source" / "study" / "1-1-agentic-loops.md"
            raw_text, study_before = raw.read_text(encoding="utf-8"), study.read_bytes()
            mutated = raw_text.replace('\\"youShouldSee\\":\\"', '\\"youShouldSee\\":\\"\\",\\"was\\":\\"', 1)
            if mutated == raw_text:
                check("extractor test could not find a youShouldSee field to blank (not run)", False)
            else:
                raw.write_text(mutated, encoding="utf-8")
                r = run(work, cfg, "tools/extract_study_data.py")
                check("extractor fails on an empty field and leaves the saved file unchanged",
                      r.returncode != 0 and "unresolved youShouldSee" in r.stdout and study.read_bytes() == study_before,
                      r.stdout[-300:])
                raw.write_text(raw_text, encoding="utf-8")

            # More extractor guards: each blanked field must fail the run without touching the saved file.
            for field in ("why", "reasoning"):
                key = '\\"' + field + '\\":\\"'
                mutated = raw_text.replace(key, key + '\\",\\"was\\":\\"', 1)
                if mutated == raw_text:
                    check(f"extractor test could not find a {field} field to blank (not run)", False)
                    continue
                raw.write_text(mutated, encoding="utf-8")
                r = run(work, cfg, "tools/extract_study_data.py")
                check(f"extractor fails on an empty {field} and leaves the saved file unchanged",
                      r.returncode != 0 and study.read_bytes() == study_before, r.stdout[-300:])
                raw.write_text(raw_text, encoding="utf-8")

            # Extractor: missing question text, two correct answers, and a missing lesson page each fail the run.
            cases = (("no question text", raw_text.replace('id="practice-scenario"', 'id="practice-gone"', 1)),
                     ("two correct answers", raw_text.replace('\\"correct\\":false', '\\"correct\\":true', 1)),
                     ("an unresolved option text", raw_text.replace('\\"text\\":\\"', '\\"text\\":\\"$zz\\",\\"t0\\":\\"', 1)),
                     ("an unresolved step instruction",
                      raw_text.replace('\\"instruction\\":\\"', '\\"instruction\\":\\"$3ff\\",\\"i0\\":\\"', 1)))
            for label, mutated in cases:
                if mutated == raw_text:
                    check(f"extractor test '{label}' could not be set up (not run)", False)
                    continue
                raw.write_text(mutated, encoding="utf-8")
                r = run(work, cfg, "tools/extract_study_data.py")
                check(f"extractor fails on {label} and leaves the saved file unchanged",
                      r.returncode != 0 and study.read_bytes() == study_before, r.stdout[-300:])
                raw.write_text(raw_text, encoding="utf-8")
            spare = tmp / "spare.html"
            shutil.move(str(work / "source" / "raw" / "5-6-information-provenance.html"), spare)
            r = run(work, cfg, "tools/extract_study_data.py")
            check("extractor fails when a lesson page is missing", r.returncode != 0 and "expected 30" in r.stdout,
                  r.stdout[-300:])
            shutil.move(str(spare), work / "source" / "raw" / "5-6-information-provenance.html")
        else:
            skip(9, "extractor tests need the private source/ copy, which is absent")

        # Installer status: an entry in the manifest that is no longer in the source is reported.
        cfg3 = tmp / "claude3"
        cfg3.mkdir()
        run(work, cfg3, *inst, "--apply")
        m3 = cfg3 / "claude-eng-harness.manifest.json"
        data = json.loads(m3.read_text(encoding="utf-8"))
        data["files"][str(cfg3 / "rules" / "retired-rule.md")] = "0" * 64
        m3.write_text(json.dumps(data), encoding="utf-8")
        r = run(work, cfg3, *inst, "--status")
        check("status reports an installed file that is no longer in the source",
              r.returncode != 0 and "stale" in r.stdout and "retired-rule.md" in r.stdout, r.stdout[-300:])

        if HAVE_SOURCE:
            # Scraper (offline): fetch is replaced by the saved pages; one page can be swapped for a bad one.
            driver = tmp / "scrape_driver.py"
            driver.write_text(
                "import pathlib, sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "import scrape_guide as s\n"
                "raw, mode = pathlib.Path(sys.argv[2]), sys.argv[3]\n"
                "BAD = {'error': ('Page not found', 300), 'shrink': ('1.2 — Multi-Agent Orchestration', 400),\n"
                "       'thin': ('1.2 — Multi-Agent Orchestration', 60), 'e404': ('404 | Claude Certification Guide', 300),\n"
                "       'bare': ('Error', 300), 'server': ('502 Bad Gateway', 300)}\n"
                "saved = {p.stem: p.read_bytes() for p in raw.glob('*.html')}\n"
                "def fake(url):\n"
                "    slug = url.rstrip('/').split('/')[-1]\n"
                "    if slug == '1-2-orchestration-patterns' and mode == 'raise':\n"
                "        raise RuntimeError('simulated network failure')\n"
                "    if slug == '1-2-orchestration-patterns' and mode == 'noarticle':\n"
                "        body = ' '.join(['word'] * 300)\n"
                "        return f'<html><head><title>1.2 Orchestration</title></head><body><div>{body}</div></body></html>'.encode()\n"
                "    if slug == '1-2-orchestration-patterns' and mode in BAD:\n"
                "        title, n = BAD[mode]\n"
                "        body = ' '.join(['word'] * n)\n"
                "        return f'<html><head><title>{title}</title></head><body><article><p>{body}</p></article></body></html>'.encode()\n"
                "    for stem, data in saved.items():\n"
                "        if url.endswith(s.EXTRA.get(stem, '/' + stem)):\n"
                "            return data\n"
                "    raise RuntimeError('no saved page for ' + url)\n"
                "s.fetch = fake\n"
                "s.time.sleep = lambda _: None\n"
                "s.main()\n", encoding="utf-8")
            target = work / "source" / "text" / "1-2-orchestration-patterns.md"
            r = run(work, cfg, str(driver), str(work / "tools"), str(work / "source" / "raw"), "none")
            check("scraper accepts every saved page unchanged, including titles containing 'Error'",
                  r.returncode == 0 and "0 failures" in r.stdout, r.stdout[-400:] + r.stderr[-300:])
            for mode, expect in (("error", "error page"), ("e404", "error page"), ("bare", "error page"),
                                 ("server", "error page"), ("shrink", "shrank"), ("thin", "words extracted"),
                                 ("raise", "fetch failed"), ("noarticle", "no <article> or <main>")):
                before = target.read_bytes()
                r = run(work, cfg, str(driver), str(work / "tools"), str(work / "source" / "raw"), mode)
                check(f"scraper rejects a {mode} page and keeps the saved copy",
                      r.returncode != 0 and expect in r.stdout and target.read_bytes() == before,
                      r.stdout[-400:] + r.stderr[-300:])
        else:
            skip(9, "scraper tests need the private source/ copy, which is absent")

        # Updater: stops before installing when the tests fail; installs when they pass; rejects unknown flags.
        upd = tmp / "updater copy"
        for d in ("harness", "kb", "tools"):
            shutil.copytree(work / d, upd / d, ignore=shutil.ignore_patterns("__pycache__"))
        cfg5 = tmp / "claude5"
        cfg5.mkdir()
        stub = upd / "tools" / "test_harness_scripts.py"
        stub.write_text("import sys\nprint('stub suite: failing on purpose')\nsys.exit(1)\n", encoding="utf-8")
        r = run(upd, cfg5, str(upd / "tools" / "update_harness.py"), "--no-pull")
        check("updater stops before installing when the tests fail",
              r.returncode != 0 and "tests failed" in (r.stdout + r.stderr) and not (cfg5 / "claude-eng-harness.manifest.json").exists(),
              r.stdout[-300:] + r.stderr[-200:])
        stub.write_text("print('stub suite: passing')\n", encoding="utf-8")
        r = run(upd, cfg5, str(upd / "tools" / "update_harness.py"), "--no-pull")
        check("updater installs when the tests pass", r.returncode == 0 and (cfg5 / "claude-eng-harness.manifest.json").exists(),
              r.stdout[-300:] + r.stderr[-200:])
        r = run(upd, cfg5, str(upd / "tools" / "update_harness.py"), "--force")
        check("updater rejects an option it does not have", r.returncode == 2, r.stderr[-200:])

        # Doctor: harness install state and project readiness.
        doctor = work / "harness" / "skills" / "claude-eng-doctor" / "scripts" / "doctor.py"
        cfg4 = tmp / "claude4"
        cfg4.mkdir()
        dp = tmp / "doctor project"
        dp.mkdir()
        r = run(work, cfg4, str(doctor), str(dp))
        check("doctor: no harness installed is NOT READY", r.returncode == 1 and "not installed" in r.stdout
              and "NOT READY" in r.stdout, r.stdout[-300:])
        run(work, cfg4, *inst, "--apply")
        r = run(work, cfg4, str(doctor), str(dp))
        check("doctor: a bare project is NOT READY and points to /claude-eng-setup",
              r.returncode == 1 and "no CLAUDE.md" in r.stdout and "/claude-eng-setup" in r.stdout
              and "files installed and unchanged" in r.stdout, r.stdout[-400:])
        (dp / "CLAUDE.md").write_text("# Doctor project\nBuild: python -m build\n", encoding="utf-8")
        (dp / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
        (dp / "_project" / "review").mkdir(parents=True)
        (dp / ".claude").mkdir()
        (dp / ".claude" / "settings.json").write_text('{"permissions": {"deny": ["Read(./.env)"]}}', encoding="utf-8")
        r = run(work, cfg4, str(doctor), str(dp))
        check("doctor: a set-up project with the harness installed is READY", r.returncode == 0
              and "Verdict: READY" in r.stdout, r.stdout[-400:])
        (dp / ".claude" / "settings.json").write_text("{not json", encoding="utf-8")
        r = run(work, cfg4, str(doctor), str(dp))
        check("doctor: a settings.json that does not parse is a FAIL", r.returncode == 1 and "does not parse" in r.stdout,
              r.stdout[-300:])
        rule4 = cfg4 / "rules" / "claude-engineering.md"
        rule4.write_text(rule4.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
        r = run(work, cfg4, str(doctor), str(dp))
        check("doctor: an installed file edited by hand is reported", "edited by hand" in r.stdout, r.stdout[-300:])

        # Team audit 2026-10-15 (F03, F08): the doctor checks the whole install and asks git about ignores.
        (dp / ".claude" / "settings.json").write_text('{"permissions": {"deny": ["Read(./.env)"]}}', encoding="utf-8")
        cfg6 = tmp / "claude6"
        scan_rel = pathlib.Path("skills/claude-eng-audit/scripts/secrets_scan.py")
        (cfg6 / scan_rel).parent.mkdir(parents=True)
        shutil.copy2(work / "harness" / scan_rel, cfg6 / scan_rel)  # identical file already there: left unowned
        run(work, cfg6, *inst, "--apply")
        (cfg6 / scan_rel).unlink()
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a missing harness file is NOT READY even if the installer did not own it",
              r.returncode == 1 and "missing" in r.stdout and "NOT READY" in r.stdout, r.stdout[-400:])
        m6 = cfg6 / "claude-eng-harness.manifest.json"
        good_m6 = m6.read_text(encoding="utf-8")
        m6.write_text(json.dumps({"files": {}, "inventory": {}}), encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: an empty manifest is a FAIL, not a pass", r.returncode == 1 and "lists no installed files" in r.stdout,
              r.stdout[-300:])
        m6.write_text("[]", encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a manifest of the wrong shape is a FAIL", r.returncode == 1 and "not a harness manifest" in r.stdout,
              r.stdout[-300:])
        shutil.copy2(work / "harness" / scan_rel, cfg6 / scan_rel)
        old = json.loads(good_m6)
        old.pop("inventory")
        m6.write_text(json.dumps(old), encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a manifest from the older installer (no inventory) still verifies, with a warning",
              r.returncode == 1 and "WARN" in r.stdout and "older installer" in r.stdout
              and "Verdict: READY with warnings" in r.stdout and "FAIL" not in r.stdout, r.stdout[-400:])
        # Docs round 4 (adversarial R16): the doctor does not trust the manifest alone.
        cut = json.loads(good_m6)
        cut["inventory"] = {k: v for k, v in cut["inventory"].items() if os.sep + "rules" + os.sep in k}
        m6.write_text(json.dumps(cut), encoding="utf-8")
        skill_md = cfg6 / "skills" / "claude-eng-audit" / "SKILL.md"
        skill_keep = skill_md.read_bytes()
        skill_md.unlink()
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a cut-down manifest cannot hide a missing required file",
              r.returncode == 1 and "required harness files are missing" in r.stdout, r.stdout[-400:])
        skill_md.write_bytes(skill_keep)
        # Redo audit R06: a cut-down manifest, an emptied script and a lost reference must not read as READY.
        m6.write_text(json.dumps(cut), encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a manifest that omits required files is a FAIL even when every file is present (R06)",
              r.returncode == 1 and "does not list" in r.stdout and "Verdict: NOT READY" in r.stdout, r.stdout[-500:])
        m6.write_text(good_m6, encoding="utf-8")
        scan6 = cfg6 / scan_rel
        scan_keep6 = scan6.read_bytes()
        scan6.write_bytes(b"")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: an emptied required script is a FAIL (R06)",
              r.returncode == 1 and "are empty" in r.stdout and "Verdict: NOT READY" in r.stdout, r.stdout[-500:])
        scan6.write_bytes(scan_keep6)
        ref6 = cfg6 / "skills" / "claude-engineering" / "references" / "claude-code-current-spec.md"
        ref_keep6 = ref6.read_bytes()
        ref6.unlink()
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a missing reference file is a FAIL (R06)",
              r.returncode == 1 and "claude-code-current-spec.md" in r.stdout and "Verdict: NOT READY" in r.stdout, r.stdout[-500:])
        ref6.write_bytes(ref_keep6)
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: restoring every file gives a clean harness section again (control for R06)",
              "FAIL" not in r.stdout.split("Project:")[0], r.stdout[-500:])
        # Redo audit R07: a retired rule the installer kept because it was edited must still be reported.
        retired6 = cfg6 / "rules" / "retired-rule.md"
        retired6.write_text("# Retired and edited by hand\n", encoding="utf-8")
        owned6 = json.loads(good_m6)
        owned6["files"][str(retired6)] = "0" * 63 + "1"  # a hash that no longer matches: edited since install
        m6.write_text(json.dumps(owned6), encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a retired file the installer kept is a FAIL, not READY (R07)",
              r.returncode == 1 and "no longer part of the harness" in r.stdout and "retired-rule.md" in r.stdout
              and "Verdict: NOT READY" in r.stdout, r.stdout[-500:])
        retired6.unlink()
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: once the retired file is removed the warning goes (control for R07)",
              "no longer part of the harness" not in r.stdout, r.stdout[-500:])
        m6.write_text(good_m6, encoding="utf-8")
        moved = json.loads(good_m6)
        moved["inventory"] = {str(tmp / "elsewhere" / "rules" / "x.md"): "0" * 64, **moved["inventory"]}
        m6.write_text(json.dumps(moved), encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(dp))
        check("doctor: a manifest entry outside the config folder is a FAIL",
              r.returncode == 1 and "point outside" in r.stdout, r.stdout[-400:])
        m6.write_text(good_m6, encoding="utf-8")
        dmod = tmp / "doctor_required_driver.py"
        dmod.write_text("import importlib.util, pathlib, sys\n"
                        "s = importlib.util.spec_from_file_location('d', sys.argv[1]); m = importlib.util.module_from_spec(s)\n"
                        "s.loader.exec_module(m)\n"
                        "h = pathlib.Path(sys.argv[2])\n"
                        "print('MISSING', [r for r in m.REQUIRED if not (h / r).is_file()])\n", encoding="utf-8")
        r = run(work, cfg6, str(dmod), str(doctor), str(work / "harness"))
        check("doctor: every file on its required list exists in the harness source", "MISSING []" in r.stdout,
              r.stdout[-300:] + r.stderr[-300:])
        broken = tmp / "doctor broken git project"
        shutil.copytree(dp, broken)
        (broken / ".git").mkdir()
        (broken / ".git" / "HEAD").write_text("not a ref\n", encoding="utf-8")
        r = run(work, cfg6, str(doctor), str(broken))
        check("doctor: a repository git cannot read is a FAIL, not 'not a git repository'",
              r.returncode == 1 and "cannot read it" in r.stdout and "not a git repository (gitignore checks skipped)" not in r.stdout, r.stdout[-400:])
        if not shutil.which("git"):
            check("doctor gitignore tests need git (not run)", False)
        else:
            gp = tmp / "doctor git project"
            shutil.copytree(dp, gp)
            gg = lambda *a: subprocess.run(["git", "-C", str(gp), *a], capture_output=True, text=True)
            gg("init", "-q")
            gg("config", "core.excludesFile", str(tmp / "no-global-excludes"))
            (gp / ".gitignore").write_text("# CLAUDE.local.md\n# .claude/settings.local.json\n# .claude/worktrees/\n",
                                           encoding="utf-8")
            r = run(work, cfg6, str(doctor), str(gp))
            check("doctor: commented-out .gitignore entries do not count as ignored",
                  "git does not ignore" in r.stdout and "git ignores the local" not in r.stdout, r.stdout[-400:])
            (gp / ".gitignore").write_text("CLAUDE.local.md\n.claude/*.local.json\n.claude/worktrees/\n", encoding="utf-8")
            r = run(work, cfg6, str(doctor), str(gp))
            check("doctor: a broader pattern that git honours counts as ignored",
                  r.returncode == 0 and "git ignores the local Claude files" in r.stdout, r.stdout[-400:])
            (gp / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
            gg("add", "-f", ".claude/settings.local.json")
            r = run(work, cfg6, str(doctor), str(gp))
            check("doctor: a local settings file that git already tracks is a FAIL",
                  r.returncode == 1 and "already tracks" in r.stdout and ".claude/settings.local.json" in r.stdout,
                  r.stdout[-400:])
            gg("rm", "-q", "--cached", ".claude/settings.local.json")
            personal = tmp / "personal-excludes"
            personal.write_text("CLAUDE.local.md\n.claude/settings.local.json\n.claude/worktrees/\n", encoding="utf-8")
            gg("config", "core.excludesFile", str(personal))
            (gp / ".gitignore").write_text("", encoding="utf-8")
            r = run(work, cfg6, str(doctor), str(gp))
            check("doctor: files ignored only by a personal ignore file are a WARN (a teammate who clones is not protected)",
                  r.returncode == 1 and "ignored only outside the project's .gitignore" in r.stdout, r.stdout[-400:])

        # Team audit 2026-10-15 (F05, F06, F07): installer safety.
        cfg7 = tmp / "claude7"
        run(work, cfg7, *inst, "--apply")
        m7 = cfg7 / "claude-eng-harness.manifest.json"
        good_m7 = m7.read_text(encoding="utf-8")
        victim = tmp / "outside-victim.txt"
        victim.write_text("must survive", encoding="utf-8")
        bad = json.loads(good_m7)
        bad["files"][str(cfg7 / ".." / victim.name)] = hashlib.sha256(victim.read_bytes()).hexdigest()
        m7.write_text(json.dumps(bad), encoding="utf-8")
        installed7 = sorted(p for p in cfg7.rglob("*") if p.is_file())
        r1 = run(work, cfg7, *inst, "--uninstall", "--apply")
        r2 = run(work, cfg7, *inst, "--apply")
        check("installer refuses a manifest path outside the config folder, before changing anything",
              r1.returncode != 0 and r2.returncode != 0 and "UNSAFE" in r1.stdout and "UNSAFE" in r2.stdout
              and victim.exists() and sorted(p for p in cfg7.rglob("*") if p.is_file()) == installed7,
              r1.stdout[-300:] + r1.stderr[-200:])
        bad = json.loads(good_m7)
        bad["files"][str(cfg7 / "CLAUDE.md")] = "0" * 64
        m7.write_text(json.dumps(bad), encoding="utf-8")
        r = run(work, cfg7, *inst, "--uninstall", "--apply")
        check("installer refuses a manifest path inside the config folder but outside rules/agents/skills",
              r.returncode != 0 and "UNSAFE" in r.stdout, r.stdout[-300:] + r.stderr[-200:])
        m7.write_text(good_m7, encoding="utf-8")
        retired = cfg7 / "rules" / "retired-rule.md"
        retired.write_text("# Retired instructions\n", encoding="utf-8")
        data7 = json.loads(good_m7)
        data7["files"][str(retired)] = hashlib.sha256(retired.read_bytes()).hexdigest()
        m7.write_text(json.dumps(data7), encoding="utf-8")
        r = run(work, cfg7, *inst, "--apply")
        rs = run(work, cfg7, *inst, "--status")
        backed = list((cfg7 / "backups").rglob("retired-rule.md")) if (cfg7 / "backups").exists() else []
        check("an install retires an unchanged file no longer in the source, with a backup, and status is clean",
              r.returncode == 0 and not retired.exists() and backed and rs.returncode == 0,
              r.stdout[-300:] + rs.stdout[-200:])
        retired.write_text("# Retired instructions, edited by hand\n", encoding="utf-8")
        data7 = json.loads(m7.read_text(encoding="utf-8"))
        data7["files"][str(retired)] = "0" * 64
        m7.write_text(json.dumps(data7), encoding="utf-8")
        r = run(work, cfg7, *inst, "--apply")
        check("an edited retired file is kept and reported, and the install does not claim success",
              r.returncode != 0 and retired.exists() and "KEEP" in r.stdout and "retired file(s) kept" in r.stderr,
              r.stdout[-300:] + r.stderr[-200:])
        retired.unlink()
        drv7 = tmp / "partial_copy_driver.py"
        drv7.write_text(
            "import importlib.util, pathlib, subprocess, sys\n"
            "from unittest.mock import patch\n"
            "s = importlib.util.spec_from_file_location('inst', sys.argv[1]); m = importlib.util.module_from_spec(s)\n"
            "s.loader.exec_module(m)\n"
            "dst = m.CLAUDE / 'rules' / 'new-rule.md'\n"
            "src = pathlib.Path(sys.argv[2])\n"
            "def partial(a, b, *x, **k):\n"
            "    pathlib.Path(b).write_text('partial', encoding='utf-8'); raise OSError('simulated full disk')\n"
            "ok = subprocess.CompletedProcess([], 0)\n"
            "with patch.object(m, 'planned', return_value={dst: src}), patch.object(m.subprocess, 'run', return_value=ok):\n"
            "    with patch.object(m.shutil, 'copy2', side_effect=partial):\n"
            "        try:\n"
            "            m.install({}, True, False, m.CLAUDE / 'backups' / 'p')\n"
            "        except OSError:\n"
            "            pass\n"
            "    leftovers = [p.name for p in dst.parent.iterdir()]\n"
            "    m.install({}, True, False, m.CLAUDE / 'backups' / 'q')\n"
            "    print('LEFTOVERS', leftovers, 'AFTER', dst.read_text(encoding='utf-8') == src.read_text(encoding='utf-8'))\n",
            encoding="utf-8")
        cfg8 = tmp / "claude8"
        (cfg8 / "rules").mkdir(parents=True)
        r = run(work, cfg8, str(drv7), str(work / "tools" / "install_harness.py"),
                str(work / "harness" / "rules" / "claude-engineering.md"))
        check("an interrupted copy leaves no partial file, and the retry installs cleanly",
              "LEFTOVERS [] AFTER True" in r.stdout, r.stdout[-300:] + r.stderr[-300:])
        drv8 = tmp / "raw_key_driver.py"
        drv8.write_text(
            "import importlib.util, pathlib, subprocess, sys\n"
            "from unittest.mock import patch\n"
            "s = importlib.util.spec_from_file_location('inst', sys.argv[1]); m = importlib.util.module_from_spec(s)\n"
            "s.loader.exec_module(m)\n"
            "stale = m.CLAUDE / 'rules' / 'retired.md'\n"
            "stale.parent.mkdir(parents=True, exist_ok=True)\n"
            "stale.write_text('# Retired\\n', encoding='utf-8')\n"
            "ok = subprocess.CompletedProcess([], 0)\n"
            "with patch.object(m, 'planned', return_value={}), patch.object(m.subprocess, 'run', return_value=ok):\n"
            "    m.install({str(stale).upper() if m.os.name == 'nt' else str(stale): m.sha(stale)}, True, False,\n"
            "              m.CLAUDE / 'backups' / 'r')\n"
            "print('RETIRED', not stale.exists(), 'MANIFEST', m.MANIFEST.exists())\n", encoding="utf-8")
        cfg11 = tmp / "claude11"
        r = run(work, cfg11, str(drv8), str(work / "tools" / "install_harness.py"))
        check("install() accepts owned paths however the caller spells them, retires the file and leaves no stale entry",
              r.returncode == 0 and "RETIRED True MANIFEST False" in r.stdout, r.stdout[-300:] + r.stderr[-300:])

        # Docs round 4 (adversarial R2, R12-R15, R20, R21): installer path handling.
        payload = lambda c: sorted(p for p in c.rglob("*") if p.is_file() and "backups" not in p.parts)
        cfg9 = tmp / "claude9"
        run(work, cfg9, *inst, "--apply")
        before9 = payload(cfg9)
        spellings = []
        if os.name == "nt":
            spellings.append(("a differently-cased spelling", str(cfg9)[0].swapcase() + str(cfg9)[1:].upper()))
        spellings.append(("a '..' spelling", str(tmp / "x" / ".." / "claude9")))
        for label, spelt in spellings:
            r = run_env(work, {"CLAUDE_CONFIG_DIR": spelt}, *inst, "--apply")
            rs = run(work, cfg9, *inst, "--status")
            check(f"re-installing with {label} of the config folder retires nothing and keeps every file",
                  r.returncode == 0 and "retire   " not in r.stdout and payload(cfg9) == before9 and rs.returncode == 0,
                  r.stdout[-300:] + r.stderr[-300:])
        if os.name != "nt":
            skip(1, "case-spelling test needs a case-insensitive file system (Windows)")
        r1 = run_env(tmp, {"CLAUDE_CONFIG_DIR": "relcfg"}, str(work / "tools" / "install_harness.py"), "--apply")
        r2 = run_env(tmp, {"CLAUDE_CONFIG_DIR": "relcfg"}, str(work / "tools" / "install_harness.py"), "--status")
        check("a relative CLAUDE_CONFIG_DIR installs and then still reads its own manifest",
              r1.returncode == 0 and r2.returncode == 0 and "UNSAFE" not in r2.stdout, r2.stdout[-300:] + r2.stderr[-200:])
        m9 = cfg9 / "claude-eng-harness.manifest.json"
        good_m9 = m9.read_text(encoding="utf-8")
        dirbad = json.loads(good_m9)
        dirbad["files"][str(cfg9 / "skills" / "claude-eng-audit")] = "0" * 64
        m9.write_text(json.dumps(dirbad), encoding="utf-8")
        r = run(work, cfg9, *inst, "--uninstall", "--apply")
        check("a manifest entry naming a folder is refused before anything is removed",
              r.returncode != 0 and "UNSAFE" in r.stdout and "not a regular file" in r.stdout and payload(cfg9) == before9,
              r.stdout[-300:] + r.stderr[-200:])
        m9.write_text(good_m9, encoding="utf-8")
        cfg10 = tmp / "claude10"
        cfg10.mkdir()
        outside_skills = tmp / "dotfiles-skills"
        outside_skills.mkdir()
        if make_link(cfg10 / "skills", outside_skills):
            r = run(work, cfg10, *inst, "--apply")
            check("an install refuses a linked skills folder up front and writes nothing through it",
                  r.returncode != 0 and "UNSAFE" in r.stdout and not any(outside_skills.iterdir())
                  and not (cfg10 / "claude-eng-harness.manifest.json").exists(), r.stdout[-300:] + r.stderr[-200:])
        else:
            check("linked-folder test could not create a link (not run)", False)
        # Redo audit R09: a linked folder inside a payload folder, pointing at another folder in the config.
        cfg11 = tmp / "claude11"
        (cfg11 / "skills" / "user-owned").mkdir(parents=True)
        (cfg11 / "skills" / "user-owned" / "mine.txt").write_text("the user's own file\n", encoding="utf-8")
        if make_link(cfg11 / "skills" / "claude-eng-doctor", cfg11 / "skills" / "user-owned"):
            r = run(work, cfg11, *inst, "--apply")
            check("an install refuses a skill folder that is a link to another folder inside the config (R09)",
                  r.returncode != 0 and "UNSAFE" in r.stdout and "linked folder" in r.stdout
                  and sorted(p.name for p in (cfg11 / "skills" / "user-owned").iterdir()) == ["mine.txt"]
                  and not (cfg11 / "claude-eng-harness.manifest.json").exists(), r.stdout[-400:] + r.stderr[-200:])
        else:
            check("internal-link test could not create a link (not run)", False)
        mine = cfg9 / "rules" / "claude-engineering.md.claude-eng-tmp"
        mine.write_text("the user's own file\n", encoding="utf-8")
        src_rule9 = work / "harness" / "rules" / "claude-engineering.md"
        good_rule9 = src_rule9.read_text(encoding="utf-8")
        src_rule9.write_text(good_rule9 + "\n", encoding="utf-8")
        r = run(work, cfg9, *inst, "--apply")
        src_rule9.write_text(good_rule9, encoding="utf-8")
        check("an install never overwrites or deletes a user's file that happens to end in .claude-eng-tmp",
              r.returncode == 0 and mine.exists() and mine.read_text(encoding="utf-8") == "the user's own file\n",
              r.stdout[-300:] + r.stderr[-200:])
        mine.unlink()
        run(work, cfg9, *inst, "--apply")
        # Two installs in the same second share a backup folder: the second backup of a read-only file must not fail.
        import importlib.util as ilu
        old_cfg_env = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(cfg9)
        try:
            ispec = ilu.spec_from_file_location("install_under_test", work / "tools" / "install_harness.py")
            im = ilu.module_from_spec(ispec)
            ispec.loader.exec_module(im)
            victim = cfg9 / "rules" / "backup-victim.md"
            victim.write_text("first\n", encoding="utf-8")
            os.chmod(victim, stat.S_IREAD)  # the copy keeps the read-only flag, as in the flaky case
            shared = cfg9 / "backups" / "same-second"
            try:
                im.backup(victim, shared)
                im.backup(victim, shared)
                made = sorted(p.name for p in (shared / "rules").iterdir())
                err = ""
            except OSError as exc:
                made, err = [], str(exc)
            check("two backups of one file in the same second both succeed and keep both copies",
                  made == ["backup-victim.md", "backup-victim.md.1"], f"{made} {err}")
            os.chmod(victim, stat.S_IREAD | stat.S_IWRITE)
            for p in (shared / "rules").glob("*"):
                os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
            victim.unlink()
        finally:
            if old_cfg_env is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old_cfg_env
        if os.name == "nt":
            stuck = cfg9 / "rules" / "stuck-rule.md"
            stuck.write_text("# Retired and read-only\n", encoding="utf-8")
            d9 = json.loads(m9.read_text(encoding="utf-8"))
            d9["files"][str(stuck)] = hashlib.sha256(stuck.read_bytes()).hexdigest()
            m9.write_text(json.dumps(d9), encoding="utf-8")
            os.chmod(stuck, stat.S_IREAD)
            r = run(work, cfg9, *inst, "--apply")
            listed = nk(stuck) in json.loads(m9.read_text(encoding="utf-8"))["files"]
            check("a retired file that cannot be removed is reported, kept in the manifest, and the install fails",
                  r.returncode != 0 and "FAILED" in r.stdout and stuck.exists() and listed and "Traceback" not in r.stderr,
                  r.stdout[-300:] + r.stderr[-300:])
            os.chmod(stuck, stat.S_IREAD | stat.S_IWRITE)
            r = run(work, cfg9, *inst, "--apply")
            check("once it can be removed, the retry retires it cleanly", r.returncode == 0 and not stuck.exists(),
                  r.stdout[-300:] + r.stderr[-200:])
        else:
            skip(2, "read-only retirement tests need Windows (elsewhere a read-only file can still be deleted)")

        # Skill scripts: secrets scanner and hook tester, on throwaway projects with spaces in their names.
        scan = work / "harness" / "skills" / "claude-eng-audit" / "scripts" / "secrets_scan.py"
        hook = work / "harness" / "skills" / "claude-eng-setup" / "scripts" / "test_hook.py"
        secret = "Qx7mP2vL9sK4tR8wN3bJ6hF1Zc5"
        if not shutil.which("git"):
            check("secrets scanner tests need git (not run)", False)
        else:
            proj = tmp / "sample project"
            proj.mkdir()
            git = lambda *a: subprocess.run(["git", "-C", str(proj), *a], capture_output=True, text=True)
            git("init", "-q")
            git("config", "user.email", "t@example.invalid")
            git("config", "user.name", "test")
            (proj / "settings.json").write_text(json.dumps({"api_key": secret}), encoding="utf-8")
            git("add", "settings.json")
            git("commit", "-q", "-m", "add settings")
            (proj / ".gitignore").write_text("settings.json\n", encoding="utf-8")
            (proj / ".env").write_text(f"SERVICE_TOKEN={secret}\n", encoding="utf-8")
            (proj / "app.py").write_text('key = os.environ["API_KEY"]\n', encoding="utf-8")
            r = run(work, cfg, str(scan), str(proj))
            check("secrets scanner finds a committed-then-gitignored key file and marks it TRACKED",
                  r.returncode == 1 and "settings.json:1" in r.stdout and "TRACKED in git" in r.stdout, r.stdout[-400:])
            check("secrets scanner finds an untracked .env value", ".env:1" in r.stdout, r.stdout[-400:])
            check("secrets scanner never prints a secret in full", secret not in r.stdout and secret not in r.stderr)
            check("secrets scanner ignores values read from the environment", "app.py" not in r.stdout, r.stdout[-400:])
            # Final-check cases: tracked keys in skipped folders, nested repos, encodings, sizes, credential forms.
            for sub, fname, body in ((".vscode", "launch.json", '{"env": {"K": "sk-ant-' + secret + '"}}'),
                                     ("build", "bundle.js", 'var t = "ghp_' + "A" * 36 + '";'),
                                     ("node_modules", "vendored-config.js", 'module.exports = {apiKey: "' + secret + '"};')):
                (proj / sub).mkdir(exist_ok=True)
                (proj / sub / fname).write_text(body, encoding="utf-8")
                git("add", "-f", f"{sub}/{fname}")
            git("commit", "-q", "-m", "more")
            nested = proj / "vendor lib"
            nested.mkdir()
            gn = lambda *a: subprocess.run(["git", "-C", str(nested), *a], capture_output=True, text=True)
            gn("init", "-q")
            (nested / "conf.yml").write_text(f"api_key: {secret}\n", encoding="utf-8")
            gn("add", "conf.yml")
            gn("-c", "user.email=t@example.invalid", "-c", "user.name=test", "commit", "-q", "-m", "x")
            (proj / "résumé ✓ notes.txt").write_text(f"token = {secret}\n", encoding="utf-8")
            (proj / "ps51 out.txt").write_bytes(("﻿" + f"SECRET_KEY={secret}\n").encode("utf-16-le"))
            (proj / "big.log").write_bytes(b"a" * 2_100_000)
            (proj / "creds.env").write_text("DB_PASSWORD=p@ss!w0rd#2024\n"
                                            "DATABASE_URL=postgres://app:S3cretPassw0rd@db.local/app\n"
                                            "HEADER=Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ=\n", encoding="utf-8")
            (proj / ".netrc").write_text("machine api.example.invalid login me password hunter2pass\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(proj))
            out = r.stdout
            check("scanner scans tool folders such as .vscode and build",
                  ".vscode/launch.json:1" in out and "build/bundle.js:1" in out, out[-500:])
            check("scanner still scans a git-tracked file inside a folder the walk skips (node_modules)",
                  any("node_modules/vendored-config.js:1" in l and "TRACKED in git" in l for l in out.splitlines()),
                  out[-500:])
            check("scanner marks a key committed in a nested repository as TRACKED",
                  any("vendor lib/conf.yml:1" in l and "TRACKED in git" in l for l in out.splitlines()), out[-500:])
            check("scanner copes with a non-ASCII file name and still exits 1, not 2",
                  r.returncode == 1 and "résumé ✓ notes.txt:1" in out, out[-300:] + r.stderr[-200:])
            check("scanner reads UTF-16 files", "ps51 out.txt:1" in out, out[-400:])
            check("scanner lists a file it skipped for size", "SKIPPED  big.log" in out, out[-400:])
            check("scanner finds a password with symbols, URL credentials, Basic auth and .netrc",
                  all(f"creds.env:{n}" in out for n in (1, 2, 3)) and ".netrc:1" in out, out[-600:])
            check("scanner still never prints a secret in full",
                  all(s not in out for s in (secret, "p@ss!w0rd#2024", "S3cretPassw0rd", "hunter2pass")))

            # Verify-round cases: false positives in code, masking of short values, placeholders, skipped files.
            fp = tmp / "false positive project"
            fp.mkdir()
            (fp / "app.py").write_text(
                "import os, getpass\n"
                "pwd = os.getcwd()\n"
                "password = getpass.getpass()\n"
                "api_key = os.environ['API_KEY']\n"
                "token = request.headers.get('Authorization')\n"
                "secret_name = settings.SECRET_NAME_FOR_VAULT\n", encoding="utf-8")
            (fp / "db.env").write_text("DATABASE_URL=postgres://app:${DB_PASSWORD}@db/app\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(fp))
            check("scanner does not flag variables, calls or placeholders as secrets",
                  r.returncode == 0 and "FINDING" not in r.stdout, r.stdout[-500:])
            (fp / "fmt.py").write_text('url = f"postgres://app:{db_pass}@db/app"\nold = "postgres://app:%(pw)s@db/app"\n',
                                       encoding="utf-8")
            r = run(work, cfg, str(scan), str(fp))
            check("scanner ignores f-string and %() placeholders in URLs", r.returncode == 0 and "fmt.py" not in r.stdout,
                  r.stdout[-400:])
            sh = tmp / "shell secret project"
            sh.mkdir()
            (sh / "deploy.sh").write_text(f"export DB_PASSWORD=Pa55w0rd!xyz\nexport API_TOKEN={secret}\n", encoding="utf-8")
            (sh / "main.go").write_text(f'apiKey := "{secret}"\n', encoding="utf-8")
            (sh / "conf.py").write_text(f'password: str = "Pa55w0rd!xyz"\n', encoding="utf-8")
            r = run(work, cfg, str(scan), str(sh))
            check("scanner finds unquoted secrets in shell scripts", "deploy.sh:1" in r.stdout and "deploy.sh:2" in r.stdout,
                  r.stdout[-400:])
            check("scanner finds Go := and annotated Python assignments", "main.go:1" in r.stdout and "conf.py:1" in r.stdout,
                  r.stdout[-400:])
            ctxp = tmp / "context project"
            ctxp.mkdir()
            (ctxp / "docker-compose.yml").write_text(
                "    environment:\n      POSTGRES_PASSWORD: devPassw0rd99  # UNRECOGNISEDTOKEN1234567890abc\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(ctxp))
            check("scanner names the variable and column but prints no part of the source line",
                  "docker-compose.yml:2 col " in r.stdout and "assignment to POSTGRES_PASSWORD" in r.stdout
                  and "line:" not in r.stdout and "devPassw0rd99" not in r.stdout
                  and "UNRECOGNISEDTOKEN1234567890abc" not in r.stdout and "environment" not in r.stdout,
                  r.stdout[-400:])
            # Docs round 4 (adversarial R1): lines that leaked a neighbouring value through the old line context.
            leaky = tmp / "leaky context project"
            leaky.mkdir()
            leak_values = ["Pa55wd1", "Winter2024", "Summer99", "Tr0ub4dor", "c2VjcmV0cGFzcw==", "Qw3rtyZ",
                           "Winterpass", "Zz9secret", "Ab12cd34"]
            key = f"sk-ant-{secret}"
            (leaky / "notes.txt").write_text(
                f"login as admin pw Pa55wd1 (temp) then {key}\n"
                f"old one password: Winter2024 (expired)  API = \"{key}\"\n"
                f"if pw == Summer99: client = make(\"{key}\")\n"
                f"Tr0ub4dor:x {key}\n"
                f"hash of c2VjcmV0cGFzcw== {key}\n"
                f"user is Qw3rtyZ = admin, {key}\n"
                f"run = tool -Winterpass ; {key}\n"
                f"s = \"unterminated  Zz9secret: {key}\n"
                f"PASSWORDS = {{\"Ab12cd34\": \"x\", \"k\": \"{key}\"}}\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(leaky))
            check("scanner prints none of nine neighbouring values that leaked through the old line context",
                  r.returncode == 1 and r.stdout.count("FINDING") >= 9 and all(v not in r.stdout for v in leak_values),
                  [v for v in leak_values if v in r.stdout])
            loot = tmp / "loot project"
            loot.mkdir()
            nt = "31d6cfe0d16ae931b73c59d7e0c089c0"
            loot_lines = {
                "ntlm.txt": f"Administrator:500:aad3b435b51404eeaad3b435b51404ee:{nt}:::",
                "netntlm.txt": "alice::CORP:1122334455667788:0123456789ABCDEF0123456789ABCDEF:0101000000000000AAAABBBBCCCCDDDD",
                "kerb.txt": "$krb5tgs$23$*svc_sql$CORP.LOCAL$MSSQLSvc/db01*$" + "ab" * 30,
                "shadow.txt": "root:$6$saltsalt$" + "Ab1/" * 21 + "xy:19000:0:99999:7:::",
                "bcrypt.txt": "$2b$12$" + "R9h/cIPz0gi.URNNX3kh2O" + "PST9/PgBkqquzi.Ss7KIUgO2t0jWMUW",
                "argon.txt": "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA",
            }
            for fname, line in loot_lines.items():
                (loot / fname).write_text(line + "\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(loot))
            check("scanner finds NTLM, NetNTLMv2, Kerberos, crypt, bcrypt and Argon2 hashes",
                  r.returncode == 1 and all(f"{f}:1" in r.stdout for f in loot_lines), r.stdout[-600:])
            check("scanner never prints a captured hash in full", nt not in r.stdout and "0123456789ABCDEF0123456789ABCDEF" not in r.stdout,
                  r.stdout[-300:])
            short = tmp / "short secret project"
            short.mkdir()
            (short / "conn.env").write_text("DATABASE_URL=postgres://app:Zq9!@db/app\nDB_PASSWORD=Pa55w0rd!\n",
                                            encoding="utf-8")
            r = run(work, cfg, str(scan), str(short))
            check("scanner shows no characters of a short secret",
                  r.returncode == 1 and "Zq9!" not in r.stdout and "Pa55" not in r.stdout and "**** (" in r.stdout,
                  r.stdout[-400:])
            once = tmp / "one key project"
            once.mkdir()
            (once / "k.txt").write_text("sk-ant-" + secret + secret + "\n", encoding="utf-8")  # long enough for both patterns
            r = run(work, cfg, str(scan), str(once))
            check("scanner reports an Anthropic key once, not twice", r.stdout.count("FINDING") == 1, r.stdout[-300:])
            big = tmp / "big file project"
            big.mkdir()
            (big / "dump.sql").write_bytes(b"x" * 2_100_000)
            r = run(work, cfg, str(scan), str(big))
            check("scanner exits 1 when it had to skip a file, so a skipped file is never a pass",
                  r.returncode == 1 and "SKIPPED" in r.stdout, r.stdout[-300:])

            # Team audit 2026-10-15 (F01, F12) and docs round 3: neighbouring values, staged copies,
            # skipped folders, more loot formats and secrets inside code strings.
            nb = tmp / "neighbour project"
            nb.mkdir()
            (nb / "app.py").write_text(f'connect("Pa55w0rd!", api_key="sk-ant-{secret}")\n'
                                       f'login(Hunter2xyz, "sk-ant-{secret}")\n', encoding="utf-8")
            r = run(work, cfg, str(scan), str(nb))
            check("scanner never prints an unrecognised value on the same line as a finding",
                  r.returncode == 1 and "Pa55w0rd!" not in r.stdout and "Hunter2xyz" not in r.stdout
                  and secret not in r.stdout and secret[:4] not in r.stdout, r.stdout[-400:])
            st = tmp / "staged project"
            st.mkdir()
            gs = lambda *a: subprocess.run(["git", "-C", str(st), *a], capture_output=True, text=True)
            gs("init", "-q")
            (st / "config.py").write_text(f'api_key = "sk-ant-{secret}"\n', encoding="utf-8")
            gs("add", "config.py")
            (st / "config.py").write_text("api_key = None\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(st))
            check("scanner finds a key that is staged even after the working copy was cleaned",
                  r.returncode == 1 and "config.py (staged copy):1" in r.stdout and "STAGED" in r.stdout, r.stdout[-400:])
            sk = tmp / "skipped folder project"
            (sk / "node_modules" / "pkg").mkdir(parents=True)
            (sk / "node_modules" / "pkg" / "stash.txt").write_text("x\n", encoding="utf-8")
            (sk / "venv" / "Scripts").mkdir(parents=True)
            (sk / "venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
            (sk / "venv" / ".env").write_text("x\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(sk))
            check("scanner lists skipped folders and how many untracked files in them it did not scan, and exits 1",
                  r.returncode == 1 and "SKIPDIR  node_modules  1 untracked files" in r.stdout
                  and "SKIPDIR  venv  2 untracked files" in r.stdout
                  and "3 untracked files in skipped folders not scanned" in r.stdout, r.stdout[-400:])
            check("scanner still lists a sensitive file name inside a skipped folder",
                  "venv/.../.env  sensitive file name inside a skipped folder" in r.stdout, r.stdout[-400:])
            fake_venv = tmp / "planted venv project"
            (fake_venv / "loot").mkdir(parents=True)
            (fake_venv / "loot" / "pyvenv.cfg").write_text("", encoding="utf-8")
            (fake_venv / "loot" / "creds.txt").write_text(f"api_key = sk-ant-{secret}\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(fake_venv))
            check("an empty planted pyvenv.cfg does not hide a folder from the scan (adversarial R10)",
                  "loot/creds.txt:1" in r.stdout and "SKIPDIR  loot" not in r.stdout, r.stdout[-400:])
            more = tmp / "more loot project"
            more.mkdir()
            more_lines = {
                "cached.txt": "$DCC2$10240#jsmith#" + "a1" * 16,
                "pot.txt": "b2" * 16 + ":Winter2026Corp!",
                "hashes.txt": "jsmith:" + "c3" * 16,
                "run.ps1": '$p = ConvertTo-SecureString "Qz8wPlmK2026Corp!" -AsPlainText -Force',
                "cli.sh": "tool --password Qz8wPlmK2026Corp! --host db01",
                "conn.py": 'CONN = "Server=db01;User Id=sa;Password=Qz8wPlmK2026Corp!;"',
            }
            for fname, line in more_lines.items():
                (more / fname).write_text(line + "\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(more))
            check("scanner finds DCC2, potfile lines, user:hash lists, SecureString, password arguments and "
                  "a password inside a code string",
                  r.returncode == 1 and all(f"{f}:1" in r.stdout for f in more_lines), r.stdout[-700:])
            check("scanner prints none of those values", all(v not in r.stdout for v in
                  ("Winter2026Corp!", "Qz8wPlmK2026Corp!", "a1" * 16, "c3" * 16)), r.stdout[-400:])
            fp2 = tmp / "argument false positive project"
            fp2.mkdir()
            (fp2 / "cli.py").write_text('parser.add_argument("--password", help="the password")\n'
                                        'msg = "password=%s" % pw\n'
                                        'print(f"token={token_value}")\n', encoding="utf-8")
            r = run(work, cfg, str(scan), str(fp2))
            check("scanner does not flag argument definitions or format placeholders",
                  r.returncode == 0 and "FINDING" not in r.stdout, r.stdout[-400:])

            # Docs round 4 (end-user 1-2): the credential forms testers use on command lines, and real cracked
            # passwords that only look like placeholders.
            engage = tmp / "engagement scripts project"
            engage.mkdir()
            engage_lines = {
                "a.sh": "curl -u admin:Qz8wPlmK2026 https://10.0.0.5/",
                "b.sh": "sshpass -p 'Qz8wPlmK2026' ssh admin@10.0.0.5",
                "c.sh": "nxc smb 10.0.0.0/24 -u admin -p 'Qz8wPlmK2026'",
                "d.sh": "evil-winrm -i 10.0.0.5 -u admin -p Qz8wPlmK2026",
                "e.sh": "mysql -u root -pQz8wPlmK2026 -h db01",
                "f.sh": "secretsdump.py corp.local/admin:Qz8wPlmK2026@10.0.0.5",
                "g.sh": "export SMB_PASS=Qz8wPlmK2026",
                "h.sh": "xfreerdp /u:admin /p:Qz8wPlmK2026 /v:10.0.0.5",
                "pot1.txt": "b2" * 16 + ":Changeme123!",
                "pot2.txt": "b2" * 16 + ":Test@1234",
                "pot3.txt": "$NT$" + "b2" * 16 + ":Example#2026",
                "pot4.txt": "d4" * 20 + ":Winter2026",
                "pot5.txt": "e5" * 16 + ":changeme",  # a real cracked password that is exactly a placeholder word
                "conf.env": "ADMIN_PASSWORD=Changeme123!",
            }
            for fname, line in engage_lines.items():
                (engage / fname).write_text(line + "\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(engage))
            check("scanner finds -p, /p:, curl -u, user:pass@host, *_PASS, $NT$ and SHA-1 potfile lines, and cracked "
                  "passwords that start with a placeholder word",
                  r.returncode == 1 and all(f"{f}:1" in r.stdout for f in engage_lines),
                  [f for f in engage_lines if f"{f}:1" not in r.stdout])
            check("scanner prints none of those values", all(v not in r.stdout for v in
                  ("Qz8wPlmK2026", "Changeme123!", "Test@1234", "Example#2026", "Winter2026")), r.stdout[-300:])
            quiet = tmp / "ordinary commands project"
            quiet.mkdir()
            (quiet / "ops.sh").write_text("mkdir -p build/out\nssh -l admin -p 2222 host\npython -m pip install -U pip\n"
                                          "mysql -u root -p\nexport DB_PASSWORD=changeme\nexport PASS=$SVC_PASS\n",
                                          encoding="utf-8")
            (quiet / "app.js").write_text('const key = "user-profile-cache-key";\n', encoding="utf-8")
            (quiet / "conf.yml").write_text("auth: oauth2-client-credentials-flow\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(quiet))
            check("scanner does not flag ports, prompts, exact placeholders, variables or hyphenated identifiers",
                  r.returncode == 0 and "FINDING" not in r.stdout, r.stdout[-500:])
            sw = tmp / "hidden staged project"
            sw.mkdir()
            gw = lambda *a: subprocess.run(["git", "-C", str(sw), *a], capture_output=True, text=True)
            gw("init", "-q")
            gw("-c", "user.email=t@example.invalid", "-c", "user.name=test", "commit", "-q", "--allow-empty", "-m", "x")
            for fname, flag in (("a.py", "--skip-worktree"), ("b.py", "--assume-unchanged")):
                (sw / fname).write_text(f'api_key = "sk-ant-{secret}"\n', encoding="utf-8")
                gw("add", fname)
                gw("update-index", flag, fname)
                (sw / fname).write_text("api_key = None\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(sw))
            check("scanner finds staged keys in skip-worktree and assume-unchanged files (adversarial R8)",
                  "a.py (staged copy):1" in r.stdout and "b.py (staged copy):1" in r.stdout, r.stdout[-400:])
            dead = tmp / "unreadable git project"
            (dead / ".git").mkdir(parents=True)
            (dead / ".git" / "HEAD").write_text("not a ref\n", encoding="utf-8")
            (dead / "main.py").write_text("print('hello')\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(dead))
            check("scanner exits 1 and says so when git cannot read the repository (adversarial R9)",
                  r.returncode == 1 and "git is missing or cannot read the repository" in r.stdout, r.stdout[-400:])
            jproj = tmp / "junction project"
            (jproj / "root").mkdir(parents=True)
            (jproj / "outside").mkdir()
            (jproj / "outside" / "leak.env").write_text(f"TOKEN=sk-ant-{secret}\n", encoding="utf-8")
            if make_link(jproj / "root" / "linked", jproj / "outside"):
                r = run(work, cfg, str(scan), str(jproj / "root"))
                check("scanner lists a file reached through a link to outside the project as SKIPPED, not a crash",
                      r.returncode == 1 and "outside the project" in r.stdout and "NOT RUN" not in r.stdout,
                      r.stdout[-400:])
            else:
                check("junction scanner test could not create a link (not run)", False)

            # Redo audit R01: a nested repository git cannot read must not hide a staged key in another one.
            nest = tmp / "nested repos"
            (nest / "good").mkdir(parents=True)
            (nest / "broken").mkdir()
            ngit = lambda *a: subprocess.run(["git", "-C", str(nest / "good"), *a], capture_output=True, text=True)
            ngit("init", "-q")
            ngit("config", "user.email", "t@example.invalid")
            ngit("config", "user.name", "test")
            (nest / "good" / "app.py").write_text(f'KEY = "sk-ant-{secret}"\n', encoding="utf-8")
            ngit("add", "app.py")
            (nest / "good" / "app.py").write_text("KEY = None\n", encoding="utf-8")  # working copy clean, index not
            r = run(work, cfg, str(scan), str(nest))
            check("scanner finds a staged key in a nested repository (control for R01)",
                  r.returncode == 1 and "good/app.py (staged copy)" in r.stdout, r.stdout[-400:])
            (nest / "broken" / ".git").write_text("gitdir: " + str(nest / "no-such-dir") + "\n", encoding="utf-8")
            (nest / "broken" / "x.txt").write_text("hello\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(nest))
            check("scanner still finds the staged key when a sibling repository is unreadable (R01)",
                  "good/app.py (staged copy)" in r.stdout, r.stdout[-400:])
            check("scanner lists the unreadable repository as SKIPPED and exits 1 (R01)",
                  r.returncode == 1 and "SKIPPED" in r.stdout and "cannot read this repository" in r.stdout
                  and "broken" in r.stdout, r.stdout[-400:])
            (nest / "good" / ".git").rename(nest / "good" / ".git-off")
            r = run(work, cfg, str(scan), str(nest))
            check("scanner exits 1 when the only unreadable item is a nested repository (R01)",
                  r.returncode == 1 and "cannot read this repository" in r.stdout, r.stdout[-400:])

            # Redo audit R02: a binary file is a file that was not scanned, so the scan is not clean.
            binp = tmp / "binary project"
            binp.mkdir()
            (binp / "blob.dat").write_bytes(b"\0\1\2 sk-ant-" + secret.encode() * 2 + b"\n")
            r = run(work, cfg, str(scan), str(binp))
            check("scanner lists a binary file as SKIPPED and exits 1, never 0 (R02)",
                  r.returncode == 1 and "SKIPPED  blob.dat" in r.stdout and "binary" in r.stdout, r.stdout[-400:])
            check("scanner prints no part of a secret from a binary file (R02)", secret not in r.stdout)

            # Redo audit R10: one very long line must not stall the scan, and a key inside it is still found.
            longp = tmp / "long line project"
            longp.mkdir()
            # Fillers with and without a credential word: the word-free ones need the cheap pre-check, the others the
            # bounded patterns; "key=..." pairs in a code file need the one-pass string state.
            for i, filler in enumerate(("_" * 150_000, "a." * 75_000, "a-" * 75_000, "key=abcdefgh " * 12_000,
                                        "x:" * 75_000, "http://" * 20_000, "a" * 150_000, "_" * 150_000 + "key",
                                        "a." * 75_000 + " token", "a:" * 75_000 + "pass", "x" * 150_000 + "::")):
                (longp / f"line{i}.txt").write_text(filler + "\n", encoding="utf-8")
                (longp / f"line{i}.py").write_text(filler + "\n", encoding="utf-8")
            (longp / "hidden.txt").write_text("_" * 60_000 + f" api_key=sk-ant-{secret}" + "_" * 60_000 + "\n",
                                              encoding="utf-8")
            t0 = time.monotonic()
            r = run(work, cfg, str(scan), str(longp))
            took = time.monotonic() - t0
            check("scanner finishes 150 KB lines of hostile filler in under 30 seconds (R10)",
                  took < 30 and "NOT RUN" not in r.stdout, f"{took:.1f}s " + r.stdout[-300:])
            check("scanner still finds a key in the middle of a very long line (R10)",
                  "hidden.txt:1" in r.stdout, r.stdout[-400:])
            # The time limit, run in-process with the limit already passed (a real 30-second wait would slow the suite).
            import contextlib, importlib.util, io
            spec = importlib.util.spec_from_file_location("secrets_scan_under_test", scan)
            ss = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ss)
            with contextlib.redirect_stdout(io.StringIO()):
                done_ok = ss.scan_text("x.txt", f"KEY = 'sk-ant-{secret}'\n", "untracked", False, False)
                ss.SCAN_SECONDS = -1
                done_late = ss.scan_text("x.txt", f"KEY = 'sk-ant-{secret}'\n", "untracked", False, False)
            check("scan_text reports a complete scan as complete and a late one as incomplete (R10)",
                  done_ok == (1, True) and done_late == (0, False), str((done_ok, done_late)))
            # Mutation findings: the cheap pre-check and the chunking are performance guards, so test them directly.
            class NoRegex:  # stands in for ASSIGNMENT; any use of it is a failure
                def finditer(self, _line):
                    raise AssertionError("ASSIGNMENT was used on a line with no credential word")
            real_assignment = ss.ASSIGNMENT
            ss.ASSIGNMENT = NoRegex()
            try:
                word_free = ss.scan_line("_" * 5000 + " plain text " + "a." * 500, False, False)
                precheck_ok = word_free == []
            except AssertionError as exc:
                precheck_ok = False
            finally:
                ss.ASSIGNMENT = real_assignment
            check("scanner does not run the assignment pattern on a line with no credential word (R10)", precheck_ok)
            seen_lengths = []
            real_scan_line = ss.scan_line
            ss.scan_line = lambda line, a, b: (seen_lengths.append(len(line)), real_scan_line(line, a, b))[1]
            try:
                edge = ss.CHUNK - 10  # a key that straddles the first chunk boundary
                long_line = "_" * edge + f" api_key=sk-ant-{secret}" + "_" * (3 * ss.CHUNK)
                hits = ss.scan_chunks(long_line, False, False)
            finally:
                ss.scan_line = real_scan_line
            check("a line longer than CHUNK is scanned in pieces no longer than CHUNK (R10)",
                  seen_lengths and max(seen_lengths) <= ss.CHUNK and len(seen_lengths) > 1, str(seen_lengths))
            check("a key that straddles a chunk boundary is still found, once (R10)",
                  sum(1 for h in hits if h[0] == "Anthropic key") == 1, str(hits))

            out, code = io.StringIO(), None
            sys_argv = sys.argv
            late_proj = tmp / "late project"
            late_proj.mkdir()
            (late_proj / "a.txt").write_text("hello\n", encoding="utf-8")
            try:
                sys.argv = ["secrets_scan.py", str(late_proj)]
                with contextlib.redirect_stdout(out):
                    try:
                        ss.main()
                    except SystemExit as exc:
                        code = exc.code
            finally:
                sys.argv = sys_argv
            check("a scan that ran out of time lists the file as SKIPPED and exits 1 (R10)",
                  code == 1 and "scan stopped after" in out.getvalue(), f"{code} {out.getvalue()[-300:]}")

            # Redo audit R02, staged side: a binary file that is only staged is not scanned either.
            sb = tmp / "staged binary project"
            sb.mkdir()
            sbgit = lambda *a: subprocess.run(["git", "-C", str(sb), *a], capture_output=True, text=True)
            sbgit("init", "-q")
            (sb / "blob.bin").write_bytes(b"\0\1 sk-ant-" + secret.encode() * 2 + b"\n")
            sbgit("add", "blob.bin")
            (sb / "blob.bin").write_text("now plain text\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(sb))
            check("scanner lists a staged binary copy as SKIPPED and exits 1 (R02)",
                  r.returncode == 1 and "blob.bin (staged copy)  binary file" in r.stdout, r.stdout[-400:])

            clean = tmp / "clean project"
            clean.mkdir()
            (clean / "main.py").write_text("print('hello')\n", encoding="utf-8")
            r = run(work, cfg, str(scan), str(clean))
            check("secrets scanner exits 0 on a clean project", r.returncode == 0, r.stdout[-300:])

        hp = tmp / "hook project"
        (hp / ".claude" / "hooks").mkdir(parents=True)
        (hp / ".claude" / "hooks" / "block_rm.py").write_text(
            "import json, sys\n"
            "e = json.load(sys.stdin)\n"
            "if 'rm -rf' in e.get('tool_input', {}).get('command', ''):\n"
            "    print('Blocked: rm -rf', file=sys.stderr); sys.exit(2)\n", encoding="utf-8")
        (hp / ".claude" / "hooks" / "deny_json.py").write_text(
            "import json, sys\n"
            "e = json.load(sys.stdin)\n"
            "if 'curl' in e.get('tool_input', {}).get('command', ''):\n"
            "    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',\n"
            "        'permissionDecision': 'deny', 'permissionDecisionReason': 'no curl'}}))\n", encoding="utf-8")
        py = pathlib.Path(sys.executable).as_posix()
        settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": sys.executable, "args": ["-I", "${CLAUDE_PROJECT_DIR}/.claude/hooks/block_rm.py"]},
            {"type": "command", "command": f'"{py}" -I "${{CLAUDE_PROJECT_DIR}}/.claude/hooks/deny_json.py"'}]}]}}
        (hp / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        ev = lambda cmd: json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}})
        r = run(work, cfg, str(hook), "--project", str(hp), "--event-json", ev("rm -rf /"), "--expect", "block")
        check("hook tester: an exit-2 hook in exec form blocks (path with a space)", r.returncode == 0, r.stdout[-400:])
        r = run(work, cfg, str(hook), "--project", str(hp), "--event-json", ev("curl x"), "--expect", "block")
        check("hook tester: a JSON deny in shell form counts as a block", r.returncode == 0, r.stdout[-400:])
        r = run(work, cfg, str(hook), "--project", str(hp), "--event-json", ev("ls"), "--expect", "allow")
        check("hook tester: a harmless command is allowed", r.returncode == 0, r.stdout[-400:])
        r = run(work, cfg, str(hook), "--project", str(hp), "--event-json", ev("ls"), "--expect", "block")
        check("hook tester: reports FAIL when the outcome is not the one expected", r.returncode == 1, r.stdout[-400:])
        settings["hooks"]["PreToolUse"][0]["hooks"].append({"type": "command", "command": "no-such-tool-xyz"})
        (hp / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        r = run(work, cfg, str(hook), "--project", str(hp), "--event-json", ev("rm -rf /"), "--expect", "block")
        check("hook tester: a hook that errors (missing tool) fails the test instead of passing silently",
              r.returncode == 1 and "error" in r.stdout, r.stdout[-400:])

        # Final-check cases for the hook tester.
        def hook_case(label, hooks, event, expect, want_rc, must="", **extra_settings):
            (hp / ".claude" / "settings.json").write_text(json.dumps({"hooks": hooks, **extra_settings}), encoding="utf-8")
            res = run(work, cfg, str(hook), "--project", str(hp), "--event-json", json.dumps(event), "--expect", expect)
            check(f"hook tester: {label}", res.returncode == want_rc and must in res.stdout and "Traceback" not in res.stderr,
                  res.stdout[-300:] + res.stderr[-200:])
        hd = hp / ".claude" / "hooks"
        (hd / "utf8.py").write_text("import sys\nsys.stdout.buffer.write('\u274c done'.encode('utf-8'))\n", encoding="utf-8")
        (hd / "array.py").write_text("print('[1, 2]')\n", encoding="utf-8")
        (hd / "reprdict.py").write_text("print(\"{'decision': 'block'}\")\n", encoding="utf-8")
        (hd / "exit2.py").write_text("import sys\nprint('stop', file=sys.stderr)\nsys.exit(2)\n", encoding="utf-8")
        (hd / "exit1.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        pre = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
        post = {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": "x"}}
        prompt = {"hook_event_name": "UserPromptSubmit", "prompt": "hi"}
        py_hook = lambda name, **extra: dict({"type": "command", "command": sys.executable,
                                               "args": ["-I", "${CLAUDE_PROJECT_DIR}/.claude/hooks/" + name]}, **extra)
        hook_case("UTF-8 output does not crash it", {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("utf8.py")]}]},
                  pre, "allow", 0)
        hook_case("non-object JSON stdout counts as allow", {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("array.py")]}]},
                  pre, "allow", 0)
        hook_case("stdout that looks like JSON but does not parse is an error",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("reprdict.py")]}]}, pre, "allow", 1, "not valid JSON")
        hook_case("a handler with no command is an error, not a crash",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command"}]}]}, pre, "allow", 1, "no command")
        hook_case("exit 2 on PostToolUse is feedback, not a block",
                  {"PostToolUse": [{"matcher": "Write", "hooks": [py_hook("exit2.py")]}]}, post, "block", 1, "feedback")
        hook_case("exit 2 on PostToolUse passes when feedback is expected",
                  {"PostToolUse": [{"matcher": "Write", "hooks": [py_hook("exit2.py")]}]}, post, "feedback", 0)
        hook_case("an interpreter that cannot open its script is an error, not a block",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("missing.py")]}]}, pre, "block", 1, "could not start")
        hook_case("onFailure: block turns an error into a block on PreToolUse",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("exit1.py", onFailure="block")]}]}, pre, "block", 0)
        # Redo audit R05: onFailure "block" does what exit 2 does on the event: PostToolUse feedback (docs, v2.1.295+).
        hook_case("onFailure: block on PostToolUse acts as exit 2: feedback, not an error",
                  {"PostToolUse": [{"matcher": "Write", "hooks": [py_hook("exit1.py", onFailure="block")]}]}, post, "feedback", 0,
                  "acts as exit 2 on PostToolUse")
        hook_case("onFailure: block on PostToolUse is not a PreToolUse-style block",
                  {"PostToolUse": [{"matcher": "Write", "hooks": [py_hook("exit1.py", onFailure="block")]}]}, post, "block", 1,
                  "got feedback")
        hook_case("without onFailure, a failing PostToolUse hook stays an error",
                  {"PostToolUse": [{"matcher": "Write", "hooks": [py_hook("exit1.py")]}]}, post, "feedback", 1,
                  "error    ")  # the outcome label itself, not text inside the detail
        hook_case("onFailure: continue on PostToolUse stays an error",
                  {"PostToolUse": [{"matcher": "Write", "hooks": [py_hook("exit1.py", onFailure="continue")]}]}, post, "feedback", 1,
                  "error    ")
        # Redo audit R04: the deprecated top-level decision on PreToolUse (docs: "approve" = allow, "block" = deny).
        (hd / "legacy_block.py").write_text("print('{\"decision\": \"block\"}')\n", encoding="utf-8")
        (hd / "legacy_approve.py").write_text("print('{\"decision\": \"approve\"}')\n", encoding="utf-8")
        (hd / "legacy_conflict.py").write_text(
            "print('{\"decision\": \"block\", \"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", "
            "\"permissionDecision\": \"allow\"}}')\n", encoding="utf-8")
        (hd / "legacy_agree.py").write_text(
            "print('{\"decision\": \"block\", \"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", "
            "\"permissionDecision\": \"deny\"}}')\n", encoding="utf-8")
        hook_case("a deprecated PreToolUse decision: block is read as a deny",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("legacy_block.py")]}]}, pre, "block", 0, "deprecated")
        hook_case("a deprecated PreToolUse decision: block does not pass an allow expectation",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("legacy_block.py")]}]}, pre, "allow", 1, "got block")
        hook_case("a deprecated PreToolUse decision: approve is read as allow",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("legacy_approve.py")]}]}, pre, "allow", 0)
        hook_case("a deprecated decision that disagrees with permissionDecision is an error, not a pass",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("legacy_conflict.py")]}]}, pre, "allow", 1, "disagree")
        hook_case("a deprecated decision that agrees with permissionDecision is fine",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("legacy_agree.py")]}]}, pre, "block", 0)
        # Redo audit R03: output is read when the hook process exits; leftover processes are not trusted.
        deny_text = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}})
        pidfile = tmp / "leftover.pid"
        # The child records its process id, and the parent waits for that before exiting, so the leftover is certain.
        sleeper = ("import os, subprocess, sys, time\n"
                   f"pidfile = {str(pidfile)!r}\n"
                   "subprocess.Popen([sys.executable, '-I', '-c', 'import os, sys, time; "
                   "open(sys.argv[1], \"w\").write(str(os.getpid())); time.sleep(30)', pidfile])\n"
                   "for _ in range(100):\n"
                   "    if os.path.exists(pidfile) and os.path.getsize(pidfile):\n"
                   "        break\n"
                   "    time.sleep(0.05)\n")
        child_code = f"import time; time.sleep(30); print({deny_text!r}, flush=True)"
        (hd / "late_child.py").write_text(  # the parent prints nothing; its child prints a deny much later
            "import subprocess, sys\n"
            f"subprocess.Popen([sys.executable, '-I', '-c', {child_code!r}])\n", encoding="utf-8")
        (hd / "allow_then_bg.py").write_text("print('{}', flush=True)\n" + sleeper, encoding="utf-8")
        (hd / "block_then_bg.py").write_text(f"print({deny_text!r}, flush=True)\n" + sleeper, encoding="utf-8")
        (hd / "quiet_bg.py").write_text(
            "import subprocess, sys\n"
            "subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n", encoding="utf-8")
        t0 = time.monotonic()
        hook_case("a deny printed later by a leftover child is NOT RUN, never a passing block",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("late_child.py")]}]}, pre, "block", 2, "left a background process")
        hook_case("a late child deny is not certified as an allow either",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("late_child.py")]}]}, pre, "allow", 2, "left a background process")
        hook_case("an allow followed by a background process is NOT RUN (suspect capture)",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("allow_then_bg.py")]}]}, pre, "allow", 2, "suspect capture")
        hook_case("a background process with redirected streams is still NOT RUN, not a pass",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("quiet_bg.py")]}]}, pre, "allow", 2, "left a background process")
        pidfile.unlink(missing_ok=True)
        hook_case("a deny printed before a background process starts still blocks",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("block_then_bg.py")]}]}, pre, "block", 0)

        def pid_alive(pid):
            if os.name == "nt":  # os.kill(pid, 0) would terminate the process on Windows
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
                return str(pid) in out
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            return True
        child_pid = int(pidfile.read_text()) if pidfile.exists() and pidfile.read_text().strip() else None
        time.sleep(1)  # let the operating system finish ending the process
        check("hook tester: the background process a hook leaves behind is ended, not left running",
              child_pid is not None and not pid_alive(child_pid), f"pid {child_pid}")
        check("hook tester: leftover processes do not hold the tests up",
              time.monotonic() - t0 < 120, f"{time.monotonic() - t0:.1f}s")
        hook_case('a handler with an "if" condition is refused, not run unconditionally',
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("exit2.py", **{"if": "Bash(git push *)"})]}]},
                  dict(pre, tool_input={"command": "rm -rf /"}), "block", 2, '"if" condition')
        hook_case("events outside PreToolUse/PostToolUse are refused, not guessed (UserPromptSubmit)",
                  {"UserPromptSubmit": [{"hooks": [py_hook("exit2.py")]}]}, prompt, "block", 2, "out of scope")
        hook_case("events outside PreToolUse/PostToolUse are refused, not guessed (PermissionRequest)",
                  {"PermissionRequest": [{"matcher": "Bash", "hooks": [py_hook("exit2.py")]}]},
                  dict(pre, hook_event_name="PermissionRequest"), "block", 2, "out of scope")
        # Team audit 2026-10-15 (F02): behaviour Claude Code documents that a guard test must not pass.
        deny_out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}
        (hd / "deny.py").write_text(f"print({json.dumps(json.dumps(deny_out))})\n", encoding="utf-8")
        (hd / "nohen.py").write_text("print('{\"hookSpecificOutput\": {\"permissionDecision\": \"deny\"}}')\n", encoding="utf-8")
        (hd / "wronghen.py").write_text(
            "print('{\"hookSpecificOutput\": {\"hookEventName\": \"PostToolUse\", \"permissionDecision\": \"deny\"}}')\n",
            encoding="utf-8")
        (hd / "stop.py").write_text("print('{\"continue\": false, \"stopReason\": \"synthetic stop\"}')\n", encoding="utf-8")
        (hd / "stopdeny.py").write_text(
            "print('{\"continue\": false, \"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", "
            "\"permissionDecision\": \"deny\"}}')\n", encoding="utf-8")
        deny_hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny.py")]}]}
        hook_case("the deny fixture blocks when run normally (baseline for the cases below)", deny_hooks, pre, "block", 0)
        hook_case("an async deny hook is not a block (async hooks cannot block)",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny.py", **{"async": True})]}]}, pre, "block", 1,
                  "async")
        hook_case("an asyncRewake deny hook counts as allow",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny.py", asyncRewake=True)]}]}, pre, "allow", 0)
        hook_case("disableAllHooks: true means the guard does not block", deny_hooks, pre, "block", 1, "disableAllHooks",
                  disableAllHooks=True)
        hook_case("a deny without hookEventName is an error, not a block",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("nohen.py")]}]}, pre, "block", 1, "hookEventName")
        hook_case("a deny with the wrong hookEventName is an error, not a block",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("wronghen.py")]}]}, pre, "block", 1, "hookEventName")
        hook_case("continue: false is stop, not allow",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("stop.py")]}]}, pre, "allow", 1, "got stop")
        hook_case("continue: false passes when stop is expected",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("stop.py")]}]}, pre, "stop", 0)
        hook_case("continue: false takes precedence over a deny in the same output",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("stopdeny.py")]}]}, pre, "stop", 0)
        hook_case("a stop from one handler outranks a block from another",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny.py"), py_hook("stop.py")]}]}, pre, "stop", 0)
        # Docs round 4 (adversarial R3, R4, R6, R7, R22, R23): follow the hooks docs' exit-code table, and report
        # anything the script does not model as NOT RUN.
        (hd / "stopnohen.py").write_text(
            "print('{\"continue\": false, \"hookSpecificOutput\": {\"permissionDecision\": \"deny\"}}')\n", encoding="utf-8")
        (hd / "deny_exit1.py").write_text(f"import sys\nprint({json.dumps(json.dumps(deny_out))})\nsys.exit(1)\n",
                                          encoding="utf-8")
        (hd / "badenum.py").write_text(
            "print('{\"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", \"permissionDecision\": \"nope\"}}')\n",
            encoding="utf-8")
        (hd / "badtype.py").write_text(
            "print('{\"continue\": \"yes\", \"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", "
            "\"permissionDecision\": \"deny\"}}')\n", encoding="utf-8")
        (hd / "trailing.py").write_text(f"print({json.dumps(json.dumps(deny_out))})\nprint('done')\n", encoding="utf-8")
        hook_case("continue: false in output that fails validation is an error, not a stop",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("stopnohen.py")]}]}, pre, "stop", 1, "hookEventName")
        hook_case("exit 1 with a valid deny is a block (the JSON decides; the exit code is ignored)",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny_exit1.py")]}]}, pre, "block", 0)
        hook_case("a permissionDecision outside the documented values is an error",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("badenum.py")]}]}, pre, "block", 1, "permissionDecision")
        hook_case("a known field with the wrong type is an error, not a block",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("badtype.py")]}]}, pre, "block", 1, "continue must be")
        hook_case("JSON followed by another line is plain text (allow), not a parse error",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("trailing.py")]}]}, pre, "allow", 0)
        hook_case("an async value that is not true or false is NOT RUN",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny.py", **{"async": "false"})]}]}, pre, "block", 2,
                  "must be true or false")
        hook_case("a disableAllHooks value that is not true or false is NOT RUN", deny_hooks, pre, "block", 2,
                  "must be true or false", disableAllHooks="true")
        hook_case("an http handler is NOT RUN, not skipped",
                  {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("deny.py"),
                                                                 {"type": "http", "url": "https://example.invalid"}]}]},
                  pre, "block", 2, "cannot be run by this script")
        local = hp / ".claude" / "settings.local.json"
        local.write_text(json.dumps({"disableAllHooks": True}), encoding="utf-8")
        hook_case("disableAllHooks in settings.local.json makes the test NOT RUN, not a pass", deny_hooks, pre, "block", 2,
                  "settings precedence")
        local.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [py_hook("stop.py")]}]}}),
                         encoding="utf-8")
        hook_case("hooks in another settings file are listed as running live too", deny_hooks, pre, "block", 0,
                  "also run in a live session")
        local.unlink()
        user_settings = cfg / "settings.json"
        user_settings.write_text(json.dumps({"disableAllHooks": False}), encoding="utf-8")
        hook_case("disableAllHooks in the user settings makes the test NOT RUN", deny_hooks, pre, "block", 2,
                  "settings precedence")
        user_settings.unlink()
        drv = tmp / "wsl_driver.py"
        drv.write_text(
            "import importlib.util, sys\n"
            "s = importlib.util.spec_from_file_location('th', sys.argv[1]); m = importlib.util.module_from_spec(s)\n"
            "s.loader.exec_module(m)\n"
            "m.shutil.which = lambda c: r'C:\\Windows\\System32\\bash.exe'\n"
            "m.os.name = 'nt'\n"
            "class Done:\n"
            "    returncode, stdout, stderr = 0, '', ''\n"
            "m.subprocess.run = lambda *a, **k: Done()  # never start a real process: only the guard can say 'error'\n"
            "print(m.run_handler({'command': 'bash', 'args': ['x.sh']}, m.pathlib.Path('.'), {}, 'PreToolUse')[0])\n",
            encoding="utf-8")
        r = run(work, cfg, str(drv), str(hook))
        check("hook tester: exec-form bash that resolves to the WSL launcher is an error",
              r.stdout.strip() == "error", r.stdout[-200:] + r.stderr[-300:])

    print(f"\n{sum(results)}/{len(results)} passed"
          + (f"; {sum(n for n, _ in skipped)} not run (SKIPPED above)" if skipped else ""))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
