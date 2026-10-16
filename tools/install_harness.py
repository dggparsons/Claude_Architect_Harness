"""Install, check or remove the Claude engineering harness in ~/.claude.

Usage:  python -I tools/install_harness.py              dry run: build, lint, show what would change
        python -I tools/install_harness.py --apply      install
        python -I tools/install_harness.py --status     compare installed files with source
        python -I tools/install_harness.py --uninstall  show what would be removed (add --apply to remove)
        add --force to replace files that were changed after install or were not installed by the harness

Safety:
- Runs tools/build_harness.py first (rebuilds references from kb/ and lints); stops if it fails.
- Copies harness/rules -> ~/.claude/rules, harness/skills/<name> -> ~/.claude/skills/<name>,
  harness/agents -> ~/.claude/agents, plus its own manifest and backup folders. Touches nothing else
  (not CLAUDE.md, not settings.json). A dry run also rebuilds the generated references in harness/.
- Set CLAUDE_CONFIG_DIR to install into another folder (the tests use this to stay away from ~/.claude).
- Never overwrites, without --force, a file it did not install or one changed since it installed it.
- Backs up every file it replaces or removes to ~/.claude/backups/claude-eng-harness-<timestamp>/.
- Writes each file to a temporary file beside it, checks its hash, then renames it into place, so an
  interrupted copy never leaves a half-written file; the manifest is written the same way.
- Records in ~/.claude/claude-eng-harness.manifest.json what it owns ("files", with hashes; saved even
  if a copy fails part-way) and the full set of files the install should have ("inventory", which also
  lists files that already existed with identical content; those are left unowned, so uninstall
  never deletes them).
- Refuses a manifest that names a path outside rules/, agents/ or skills/ in the config folder, before
  changing anything.
- A file it installed earlier that is no longer in the source is retired: backed up and removed if
  unchanged; kept and reported if it was edited (use --force to remove it with a backup).
- Ends an install by checking the result against the source; any mismatch is an error.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "harness"
# Resolved once, so a relative, ".."-containing or differently-cased spelling of the same folder is one folder.
CLAUDE = pathlib.Path(os.path.realpath(os.path.abspath(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")))
MANIFEST = CLAUDE / "claude-eng-harness.manifest.json"
PAYLOAD_DIRS = ("rules", "agents", "skills")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def key(p):
    """The manifest key for a path: resolved and case-folded where the file system ignores case (Windows),
    so two spellings of one file are one key."""
    return os.path.normcase(os.path.realpath(p))


def planned():
    """Map destination path -> source path for every harness file."""
    pairs = {}
    for sub in ("rules", "agents"):
        for f in sorted((SRC / sub).glob("*.md")):
            pairs[CLAUDE / sub / f.name] = f
    for skill in sorted(p for p in (SRC / "skills").iterdir() if p.is_dir()):
        for f in sorted(skill.rglob("*")):
            if f.is_file() and not any(part.startswith(".references.") or part == "__pycache__" for part in f.parts):
                pairs[CLAUDE / "skills" / skill.name / f.relative_to(skill)] = f
    return pairs


def redirected(p):
    """True if p is a symlink or junction, or resolves somewhere other than where it is spelt."""
    if p.is_symlink() or getattr(os.path, "isjunction", lambda _: False)(p):
        return True
    return p.exists() and os.path.normcase(os.path.realpath(p)) != os.path.normcase(os.path.abspath(p))


def payload_problem(path_s):
    """Why a manifest path is not one this installer may touch, or None if it is fine."""
    root = CLAUDE.resolve()
    p = pathlib.Path(path_s)
    if not p.is_absolute():
        return "is not an absolute path"
    try:
        rel = p.resolve().relative_to(root)
    except ValueError:
        return f"is outside {root}"
    if p.is_symlink():
        return "is a link"
    for folder in p.parents:  # a linked folder above the file would send the write somewhere else inside the config
        if len(folder.parts) <= len(root.parts):
            break
        if redirected(folder):
            return f"is inside a linked folder ({folder})"
    if p.exists() and not p.is_file():
        return "is not a regular file"
    if len(rel.parts) < 2 or rel.parts[0] not in PAYLOAD_DIRS:
        return f"is not under {', '.join(PAYLOAD_DIRS)} in {root}"
    return None


def refuse_unsafe(paths):
    """Stop before any change if a path is not one this installer may touch."""
    problems = [f"{p} {why}" for p in paths if (why := payload_problem(p))]
    if problems:
        for pr in problems:
            print(f"UNSAFE   {pr}")
        sys.exit(f"Stopped: {MANIFEST} lists paths this installer must not touch; nothing changed. "
                 "Check the manifest by hand (it may have been edited or damaged).")


def load_manifest():
    """Return (owned files, inventory). Stops before any change if the manifest is malformed or unsafe."""
    if not MANIFEST.exists():
        return {}, {}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Stopped: {MANIFEST} cannot be read ({exc}); nothing changed.")
    files = data.get("files") if isinstance(data, dict) else None
    inventory = data.get("inventory", {}) if isinstance(data, dict) else None
    if not isinstance(files, dict) or not isinstance(inventory, dict):
        sys.exit(f"Stopped: {MANIFEST} is not a harness manifest (no files map); nothing changed.")
    bad_hash = [p for p, h in list(files.items()) + list(inventory.items()) if not (isinstance(h, str) and HEX64.match(h))]
    if bad_hash:
        sys.exit(f"Stopped: {MANIFEST} has entries without a valid hash (e.g. {bad_hash[0]}); nothing changed.")
    refuse_unsafe(list(files) + list(inventory))
    return {key(k): v for k, v in files.items()}, {key(k): v for k, v in inventory.items()}


def temp_beside(dst):
    """A new, uniquely named temporary file in dst's folder (never an existing file of the user's)."""
    fd, name = tempfile.mkstemp(dir=dst.parent, prefix="." + dst.name + ".", suffix=".claude-eng-tmp")
    os.close(fd)
    return pathlib.Path(name)


def write_atomic(dst, data):
    tmp = temp_beside(dst)
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def save_manifest(files, inventory):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    if not files and not inventory:
        MANIFEST.unlink(missing_ok=True)
        return
    write_atomic(MANIFEST, json.dumps({"updated": datetime.datetime.now().isoformat(timespec="seconds"),
                                       "source": str(ROOT), "files": files, "inventory": inventory},
                                      indent=2).encode("utf-8"))


def copy_atomic(src, dst):
    """Copy src to dst through a temporary file beside it; dst is either unchanged or complete."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_beside(dst)
    try:
        shutil.copy2(src, tmp)
        if sha(tmp) != sha(src):
            raise OSError(f"copy of {src} to {tmp} does not match the source")
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def backup(path, bdir):
    dest = bdir / pathlib.Path(key(path)).relative_to(pathlib.Path(key(CLAUDE)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    while dest.exists():  # an earlier run in the same second already backed this file up (possibly read-only)
        n += 1
        dest = dest.with_name(f"{dest.name}.{n}")
    shutil.copy2(path, dest)


def remove_empty_dirs(path):
    """Remove now-empty folders above a removed file, stopping at rules/, agents/ or skills/."""
    root = pathlib.Path(key(CLAUDE))
    stop = {root / d for d in PAYLOAD_DIRS}
    d = pathlib.Path(key(path)).parent
    while d not in stop and root in d.parents:
        try:
            d.rmdir()
        except OSError:
            return
        d = d.parent


def status(owned, quiet=False):
    pairs = planned()
    drift = 0
    for dst, src in pairs.items():
        state = "missing" if not dst.exists() else ("ok" if sha(dst) == sha(src) else "differs")
        drift += state != "ok"
        if not quiet or state != "ok":
            print(f"{state:8s} {dst}")
    for path in sorted(set(owned) - {key(p) for p in pairs}):
        print(f"stale    {path} (installed earlier, no longer in source)")
        drift += 1
    if not quiet:
        print(f"\n{len(pairs)} files, {drift} not matching source")
    return 1 if drift else 0


def uninstall(owned, apply, force, bdir):
    refuse_unsafe(owned)
    owned = {key(k): v for k, v in owned.items()}  # however the caller spelt them
    keep = {}
    for path_s, recorded in sorted(owned.items()):
        t = pathlib.Path(path_s)
        if not t.exists():
            print(f"gone     {t}")
            continue
        if sha(t) != recorded and not force:
            print(f"KEEP     {t} (changed since install; use --force to remove it with a backup)")
            keep[path_s] = recorded
            continue
        print(f"remove   {t}")
        if apply:
            backup(t, bdir)
            t.unlink()
            remove_empty_dirs(t)
    if apply:
        save_manifest(keep, {})
        print(f"\nUninstalled. Backup: {bdir}" + (f". {len(keep)} changed files kept and still listed in the manifest." if keep else ""))
    else:
        print("\nDry run. Add --apply to uninstall.")


def install(owned, apply, force, bdir):
    build = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "build_harness.py")])
    if build.returncode != 0:
        sys.exit("Install stopped: build_harness.py failed (see LINT FAIL / BUILD FAIL above).")
    refuse_unsafe(owned)
    owned = {key(k): v for k, v in owned.items()}  # however the caller spelt them

    actions, blocked = [], []
    plan = planned()
    # Every destination must be inside the config folder for real (not through a link) before anything is written.
    unsafe = [f"{d} {why}" for d in plan if (why := payload_problem(str(d)))]
    if unsafe:
        for u in unsafe:
            print(f"UNSAFE   {u}")
        sys.exit(f"Install stopped: nothing written. These destinations are not plain files inside {CLAUDE} "
                 "(a linked rules/, agents/ or skills/ folder, or a linked folder inside one, is not supported).")
    for dst, src in plan.items():
        k = key(dst)
        if not dst.exists():
            actions.append(("add", dst, src))
        elif sha(dst) == sha(src):
            actions.append(("same", dst, src))
        elif k in owned and sha(dst) == owned[k]:
            actions.append(("update", dst, src))
        elif force:
            actions.append(("replace", dst, src))
        elif k in owned:
            blocked.append(f"{dst} was changed after install")
        else:
            blocked.append(f"{dst} exists and was not installed by this harness")
    retire, kept_stale = [], []
    for path_s in sorted(set(owned) - {key(d) for d in plan}):  # never a planned file, however it is spelt
        t = pathlib.Path(path_s)
        if not t.exists():
            retire.append((t, "gone"))
        elif sha(t) == owned[path_s] or force:
            retire.append((t, "remove"))
        else:
            kept_stale.append(t)
    for kind, dst, _ in actions:
        print(f"{kind:8s} {dst}")
    for t, how in retire:
        print(f"retire   {t} (no longer in source; " + ("already gone)" if how == "gone" else "backed up and removed)"))
    for t in kept_stale:
        print(f"KEEP     {t} (no longer in source, but edited by hand; use --force to remove it with a backup)")
    if blocked:
        for b in blocked:
            print(f"BLOCKED  {b}")
        sys.exit("Install stopped: nothing written. Resolve the BLOCKED files, or rerun with --force "
                 "to back them up and replace them.")
    if not apply:
        print("\nDry run. Add --apply to install.")
        return

    files = dict(owned)
    inventory = {key(dst): sha(src) for dst, src in plan.items()}
    written, failed = 0, []
    try:
        for kind, dst, src in actions:
            if kind == "same":
                continue  # identical already; if not ours, leave it unowned so uninstall never deletes it
            if kind in ("update", "replace"):
                backup(dst, bdir)
            copy_atomic(src, dst)
            files[key(dst)] = sha(dst)
            written += 1
        for t, how in retire:
            if how == "remove":
                try:
                    backup(t, bdir)
                    t.unlink()
                except OSError as exc:
                    print(f"FAILED   {t} could not be retired ({exc}); it is kept and still listed in the manifest")
                    failed.append(t)
                    continue
                remove_empty_dirs(t)
            files.pop(key(t), None)
    finally:
        save_manifest(files, inventory)
    print(f"\nInstalled: {written} files written, {len(actions) - written} unchanged, {len(retire)} retired."
          + (f" Backup of replaced files: {bdir}" if bdir.exists() else ""))
    if failed:
        sys.exit(f"Install finished, but {len(failed)} retired file(s) could not be removed (see FAILED above); "
                 "rerun the install to try again.")
    if kept_stale:
        sys.exit(f"Install finished with {len(kept_stale)} retired file(s) kept because they were edited (see KEEP above): "
                 "they still load. Remove them by hand or rerun with --force.")
    if status(files, quiet=True):
        sys.exit("Install finished but the result does not match the source (see above).")


def main():
    ap = argparse.ArgumentParser(description="Install, check or remove the Claude engineering harness.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="compare installed files with source (read-only)")
    mode.add_argument("--uninstall", action="store_true", help="remove installed files (dry run unless --apply)")
    ap.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    ap.add_argument("--force", action="store_true", help="replace or remove files changed since install, with backup")
    args = ap.parse_args()
    if args.status and (args.apply or args.force):
        ap.error("--status is read-only; it cannot be combined with --apply or --force")

    owned, _ = load_manifest()
    bdir = CLAUDE / "backups" / f"claude-eng-harness-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    if args.status:
        sys.exit(status(owned))
    if args.uninstall:
        uninstall(owned, args.apply, args.force, bdir)
    else:
        install(owned, args.apply, args.force, bdir)


if __name__ == "__main__":
    main()
