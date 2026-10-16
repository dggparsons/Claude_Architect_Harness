"""Check that the Claude engineering harness is installed and intact, and that a project is set up.

Usage:  python -I doctor.py [project-path]

Harness: reads the install manifest in the Claude config folder (CLAUDE_CONFIG_DIR, else ~/.claude)
and checks every file in its inventory (all the files the install should have, including ones that
were already there and so are not owned by the installer) is present and unchanged. A malformed or
empty manifest is a FAIL. Reports the source folder and, if it is a git repository, its last commit
and whether it has uncommitted changes.
Project (default: current folder): checks the basics a well-set-up project has - CLAUDE.md
(under 200 lines), PLAN.md, a review folder, .claude/settings.json that parses, and (git
repositories only) that git really ignores the local Claude files, using git check-ignore, and
does not already track them.
Read-only: changes nothing.

Exit codes: 0 everything ready, 1 something needs attention, 2 the check could not run.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys


# Every file the install should have. Each must be present, non-empty and listed in the manifest with its
# hash, whatever else the manifest says, so a damaged or cut-down manifest cannot hide a missing part.
# tools/build_harness.py (lint) fails if this list and the files under harness/ ever differ.
REQUIRED = ("rules/claude-engineering.md", "rules/claude-code-config.md",
            "skills/claude-engineering/SKILL.md", "skills/claude-eng-setup/SKILL.md",
            "skills/claude-eng-audit/SKILL.md", "skills/claude-eng-doctor/SKILL.md",
            "skills/claude-eng-audit/scripts/secrets_scan.py", "skills/claude-eng-setup/scripts/test_hook.py",
            "skills/claude-eng-doctor/scripts/doctor.py",
            "skills/claude-engineering/references/claude-code-current-spec.md",
            "skills/claude-engineering/references/domain-1-agentic-architecture.md",
            "skills/claude-engineering/references/domain-2-tool-design-mcp.md",
            "skills/claude-engineering/references/domain-3-claude-code-config.md",
            "skills/claude-engineering/references/domain-4-prompt-engineering.md",
            "skills/claude-engineering/references/domain-5-context-reliability.md",
            "skills/claude-engineering/references/verification.md",
            "skills/claude-engineering/references/working-practice.md",
            "agents/reviewer-facts.md", "agents/reviewer-consistency.md", "agents/reviewer-end-user.md",
            "agents/reviewer-standards.md")


def norm(p):
    return os.path.normcase(os.path.realpath(p))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(folder, *args):
    try:
        r = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def check_harness(claude_dir, report):
    manifest = claude_dir / "claude-eng-harness.manifest.json"
    if not manifest.exists():
        report("FAIL", "harness", f"not installed: no {manifest}")
        return
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report("FAIL", "harness", f"manifest unreadable: {exc}")
        return
    if not isinstance(data, dict) or not isinstance(data.get("files", {}), dict) \
            or not isinstance(data.get("inventory", {}), dict):
        report("FAIL", "harness", f"{manifest} is not a harness manifest (reinstall from the harness source)")
        return
    # The inventory lists every file the install should have, including ones that were already there
    # with identical content (not owned by the installer); older manifests have only the owned files.
    files = data.get("inventory") or data.get("files", {})
    if not data.get("inventory"):
        report("WARN", "harness", "manifest from an older installer: only files it wrote are checked "
               "(reinstall to record the full inventory)")
    if not files:
        report("FAIL", "harness", f"{manifest} lists no installed files (reinstall from the harness source)")
        return
    root = norm(claude_dir)
    outside = [p for p in files if not norm(p).startswith(root + os.sep)]
    if outside:
        report("FAIL", "harness", f"{len(outside)} manifest entries point outside {claude_dir}, e.g. {outside[0]} "
               "(the manifest is damaged or from another folder; reinstall)")
    missing = [p for p in files if not pathlib.Path(p).exists()]
    changed = [p for p in files if pathlib.Path(p).exists() and sha(pathlib.Path(p)) != files[p]]
    if missing:
        report("FAIL", "harness", f"{len(missing)} installed files are missing, e.g. {missing[0]}")
    if changed:
        report("WARN", "harness", f"{len(changed)} installed files were edited by hand, e.g. {changed[0]} "
               "(edit the source and reinstall instead)")
    if not missing and not changed:
        report("PASS", "harness", f"{len(files)} files installed and unchanged (installed {data.get('updated', '?')})")
    absent = [n for n in REQUIRED if not (claude_dir / n).is_file()]
    if absent:
        report("FAIL", "harness", f"{len(absent)} required harness files are missing from {claude_dir}, e.g. {absent[0]} "
               "(reinstall from the harness source)")
    empty = [n for n in REQUIRED if (claude_dir / n).is_file() and (claude_dir / n).stat().st_size == 0]
    if empty:
        report("FAIL", "harness", f"{len(empty)} required harness files are empty, e.g. {empty[0]} "
               "(reinstall from the harness source)")
    if data.get("inventory"):  # every required file must be covered by a recorded hash, not just present
        listed = {norm(p) for p in files}
        uncovered = [n for n in REQUIRED if norm(claude_dir / n) not in listed]
        if uncovered:
            report("FAIL", "harness", f"the manifest does not list {len(uncovered)} files the install should have, "
                   f"e.g. {uncovered[0]} (the manifest is damaged or cut down, so those files were not checked; "
                   "reinstall from the harness source)")
        # Files the installer owns that this version no longer ships. The installer keeps one that was edited
        # by hand and warns; while it is still there it keeps loading, so this must not read as READY.
        retired = [p for p in data.get("files", {}) if norm(p) not in listed and pathlib.Path(p).exists()]
        if retired:
            report("FAIL", "harness", f"{len(retired)} installed file(s) are no longer part of the harness but still "
                   f"load, e.g. {retired[0]} (the installer keeps a retired file you edited; remove it by hand or "
                   "reinstall with --force)")
    source = pathlib.Path(data.get("source", ""))
    if not source.is_dir():
        report("WARN", "source", f"harness source folder not found: {source}")
        return
    last = git(source, "log", "-1", "--format=%cs %h %s")
    if last is None:
        report("INFO", "source", f"{source} (not a git repository, so updates come from this folder only)")
        return
    dirty = git(source, "status", "--porcelain")
    report("INFO", "source", f"{source}; last commit {last}" + ("; has uncommitted changes" if dirty else ""))


def check_project(project, report):
    claude_md = next((p for p in (project / "CLAUDE.md", project / ".claude" / "CLAUDE.md") if p.exists()), None)
    if claude_md is None:
        report("FAIL", "project", "no CLAUDE.md (run /claude-eng-setup)")
    else:
        lines = len(claude_md.read_text(encoding="utf-8", errors="replace").splitlines())
        report("PASS" if lines < 200 else "WARN", "project", f"{claude_md.relative_to(project)} has {lines} lines"
               + ("" if lines < 200 else " (over 200: move part-of-the-code rules to .claude/rules/)"))
    report("PASS" if (project / "PLAN.md").exists() else "WARN", "project",
           "PLAN.md present" if (project / "PLAN.md").exists() else "no PLAN.md (the working practice asks for one before substantial work)")
    reviews = [d for d in ("_project/review", "qa", "review", "docs/reviews") if (project / d).is_dir()]
    report("PASS" if reviews else "WARN", "project",
           f"review folder: {reviews[0]}" if reviews else "no review folder (_project/review/)")
    settings = project / ".claude" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            deny = len((data.get("permissions") or {}).get("deny", []))
            hooks = sum(len(g.get("hooks", [])) for groups in (data.get("hooks") or {}).values() for g in groups)
            report("PASS", "project", f".claude/settings.json parses ({deny} deny rules, {hooks} hooks)")
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            report("FAIL", "project", f".claude/settings.json does not parse: {exc}")
    else:
        report("WARN", "project", "no .claude/settings.json (no deny rules or hooks guard this project)")
    top = git(project, "rev-parse", "--show-toplevel")
    if top is None:
        if any((d / ".git").exists() for d in [project, *project.parents]):
            report("FAIL", "project", "a git repository is here but git is missing or cannot read it, "
                   "so the ignore and tracked-file checks did not run")
        else:
            report("INFO", "project", "not a git repository (gitignore checks skipped)")
        return
    # Ask git itself (comments, negation, broader patterns and parent folders all count as git counts them).
    probes = {"CLAUDE.local.md": "CLAUDE.local.md", ".claude/settings.local.json": ".claude/settings.local.json",
              ".claude/worktrees/": ".claude/worktrees/probe"}
    missing = [name for name, probe in probes.items() if git(project, "check-ignore", "-q", "--no-index", probe) is None]
    tracked = [name for name, probe in probes.items()
               if git(project, "ls-files", "--", probe if not name.endswith("/") else name)]
    # A rule only in the user's global ignore file or .git/info/exclude does not protect a teammate who clones.
    personal = []
    for name, probe in probes.items():
        if name in missing:
            continue
        out = git(project, "check-ignore", "-v", "--no-index", probe) or ""
        source = out.split("\t", 1)[0].rsplit(":", 2)[0] if "\t" in out else ""
        src = pathlib.Path(source) if pathlib.Path(source).is_absolute() else pathlib.Path(top) / source
        if src.name != ".gitignore" or not norm(src).startswith(norm(top) + os.sep):
            personal.append(f"{name} (by {source or 'an unknown rule'})")
    report("PASS" if not missing else "WARN", "project",
           "git ignores the local Claude files" if not missing else f"git does not ignore: {', '.join(missing)} (add them to .gitignore)")
    if personal:
        report("WARN", "project", f"ignored only outside the project's .gitignore, so a teammate who clones is not "
               f"protected: {', '.join(personal)} (add them to the project's .gitignore)")
    if tracked:
        report("FAIL", "project", f"git already tracks local Claude files: {', '.join(tracked)} "
               "(ignoring does not untrack them: git rm --cached, and check them for secrets)")


def main():
    ap = argparse.ArgumentParser(description="Check the harness install and a project's setup (read-only).")
    ap.add_argument("project", nargs="?", default=".", help="project folder (default: current folder)")
    args = ap.parse_args()
    project = pathlib.Path(args.project).resolve()
    if not project.is_dir():
        print(f"NOT RUN: {project} is not a folder")
        sys.exit(2)
    claude_dir = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
    results = []

    def report(level, area, message):
        results.append(level)
        print(f"{level:5s} {area:8s} {message}")

    print(f"Harness: {claude_dir}")
    check_harness(claude_dir, report)
    print(f"\nProject: {project}")
    check_project(project, report)
    bad = "FAIL" in results
    warn = "WARN" in results
    print("\nVerdict: " + ("NOT READY - fix the FAIL lines (for a new project: /claude-eng-setup)" if bad
                          else "READY with warnings" if warn else "READY"))
    sys.exit(1 if bad or warn else 0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"NOT RUN: {type(exc).__name__}: {exc}")
        sys.exit(2)
