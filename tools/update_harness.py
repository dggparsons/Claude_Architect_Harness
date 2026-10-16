"""Bring this machine's Claude engineering harness up to date in one step.

Usage:  python -I tools/update_harness.py            pull, test, then install
        python -I tools/update_harness.py --no-pull  test and install the folder as it is

1. If this folder is a git repository: `git pull --ff-only` (stops if the pull cannot fast-forward,
   for example because of local commits or uncommitted changes to tracked files).
2. Runs tools/test_harness_scripts.py; stops if any test fails.
3. Runs tools/install_harness.py --apply (rebuild, lint, back up anything replaced, install).
Stops at the first failure and says which step failed; nothing is installed if the pull, the tests or the lint fail.
"""
import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def step(title, argv):
    print(f"\n== {title}: {' '.join(argv)}", flush=True)
    r = subprocess.run(argv, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"\nStopped: {title} failed (exit {r.returncode}). Nothing further was done.")


def main():
    ap = argparse.ArgumentParser(description="Pull, test and install the Claude engineering harness.")
    ap.add_argument("--no-pull", action="store_true", help="skip git pull")
    args = ap.parse_args()
    is_repo = shutil.which("git") and subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                                                     capture_output=True).returncode == 0
    if args.no_pull:
        print("Skipping git pull (--no-pull).")
    elif is_repo:
        step("git pull", ["git", "-C", str(ROOT), "pull", "--ff-only"])
    else:
        print(f"{ROOT} is not a git repository: skipping git pull and installing this folder as it is.")
    step("tests", [sys.executable, "-I", str(ROOT / "tools" / "test_harness_scripts.py")])
    step("install", [sys.executable, "-I", str(ROOT / "tools" / "install_harness.py"), "--apply"])
    print("\nUpdated. Start a new Claude Code session to load the new rules and skills, then run /claude-eng-doctor.")


if __name__ == "__main__":
    main()
