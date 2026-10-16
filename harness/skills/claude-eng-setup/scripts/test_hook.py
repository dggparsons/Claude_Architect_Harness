"""Run a project's hooks against a sample event, as Claude Code would, and check the outcome.

Usage:
  python -I test_hook.py --project <root> --event-json '<json>' --expect block|ask|allow|feedback|stop [--settings <file>]
  (In Windows PowerShell 5.1 the quoted JSON argument is mangled: run from Git Bash or pwsh 7.)

Running a hook runs the project's own code: only test hooks you have read, on a project you trust.

Scope. It models the documented rules below and nothing more. Anything outside them is reported as
NOT RUN (exit 2), never as a pass: test those hooks live in a Claude Code session.
- Events: PreToolUse (guards) and PostToolUse (formatters, linters, loggers) only.
- Settings: reads the hooks for the event from <root>/.claude/settings.json (or --settings). It also
  looks at <root>/.claude/settings.local.json and the user settings ($CLAUDE_CONFIG_DIR/settings.json,
  else ~/.claude/settings.json): if any of them sets "disableAllHooks", the result depends on settings
  precedence, so the test is NOT RUN; hooks they define for the same event are listed as running live
  too, but are not run here. Managed (organisation) settings are not read.
- Handlers: only "command" handlers run; http, mcp_tool, prompt and agent handlers are listed and the
  test is NOT RUN. A handler with an "if" condition is NOT RUN (the script does not evaluate it).
  "async" and "asyncRewake" must be true or false (anything else is NOT RUN); an async hook runs in the
  background and cannot block or control Claude, so it is not run and counts as allow.
  "disableAllHooks" must be true or false; true means no hook runs and every handler counts as allow.
- Running: exec form when "args" is set (no shell; ${CLAUDE_PROJECT_DIR} substituted as plain text);
  otherwise shell form (Git Bash on Windows, found via CLAUDE_CODE_GIT_BASH_PATH or next to git.exe
  and never the System32 WSL launcher; sh elsewhere; PowerShell when "shell": "powershell" or Git Bash
  is missing; that path is best effort, so prefer exec form: "command": "powershell.exe", "args":
  ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "<script>"]). CLAUDE_PROJECT_DIR is set and the
  event JSON is sent on stdin. The matcher is compared with tool_name (empty or "*" = all; only
  letters, digits, _, -, spaces, commas and | = exact names; otherwise a regular expression).
- Stdout, as the hooks docs define it: JSON only when the whole output is one JSON object (it starts
  with { and ends with }); otherwise plain text. Something that starts with { and ends with } but is not
  valid JSON is a parse failure. A JSON object also fails validation when hookSpecificOutput lacks a
  hookEventName equal to the event, or a known field has the wrong type (continue and suppressOutput
  true/false; stopReason, systemMessage, reason, permissionDecisionReason and additionalContext text;
  permissionDecision one of allow, deny, ask, defer; decision "block" or "approve"; updatedInput an object).
- Outcomes, following the docs' exit-code table:
  exit 2: PreToolUse block, PostToolUse feedback (the tool has already run), whatever the JSON says;
          valid JSON with continue: false makes it stop.
  exit 0: valid JSON: its fields decide; JSON that fails to parse or validate: error; plain text: allow.
  other exit codes: valid JSON: its fields decide (the exit code is ignored); otherwise error.
  Fields: continue: false = stop (Claude stops processing; it outranks every decision). PreToolUse:
  permissionDecision deny = block, ask = ask, allow or defer = allow. PostToolUse: decision "block" =
  feedback. Also error: an interpreter that could not open its script, a timeout, exec-form bash that
  resolves to the WSL launcher, a handler with no command.
  On PreToolUse a handler with "onFailure": "block" turns a failure (an error, or any exit code other
  than 0 or 2, even with JSON that allows) into a block. On PostToolUse it does what exit 2 does there:
  feedback only, because the tool has already run. The docs say onFailure needs Claude Code v2.1.295 or later.
  PreToolUse also accepts the deprecated top-level decision ("approve" = allow, "block" = deny); when it
  disagrees with hookSpecificOutput.permissionDecision the docs do not say which wins, so that is an error.
- Background processes. Claude Code finishes reading a hook's output shortly after the hook's own process
  exits, so a deny that a leftover process prints later does not block; and an allow followed by a background
  process that kept the hook's output streams open is refused as a "suspect capture". The script reads the
  output when the hook process exits and then checks whether anything the hook started is still running (a
  job object on Windows, a process group elsewhere). If so, only a block or stop that was already printed
  stands; anything else is NOT RUN, because whether the leftover process holds the streams cannot be told
  from here. Test such hooks live. The check is best effort: a process started in the first few
  milliseconds, before the script attaches the job, is not seen.
- The result is stop if any handler stops, else block, else ask, else feedback, else allow. Any error
  fails the test, because the hook did not do its job. Confirm important guards once in a live session.

Exit codes: 0 outcome as expected, 1 not as expected, 2 the test could not run.
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile

EXACT = re.compile(r"^[A-Za-z0-9_\- ,|]*$")
SUPPORTED = {"PreToolUse", "PostToolUse"}
CAN_BLOCK = {"PreToolUse"}
WSL_LAUNCHER = re.compile(r"(?i)\\(system32|windowsapps)\\bash\.exe$")
COULD_NOT_START = re.compile(r"(?i)can't open file|no such file or directory|cannot find the (file|path)|"
                             r"is not recognized as|command not found|cannot be loaded because")
BOOL_FIELDS = ("continue", "suppressOutput")
TEXT_FIELDS = ("stopReason", "systemMessage", "reason")
HSO_TEXT_FIELDS = ("permissionDecisionReason", "additionalContext")
DECISIONS = {"allow", "deny", "ask", "defer"}


def matches(matcher, tool_name):
    if matcher in (None, "", "*"):
        return True
    if EXACT.match(matcher):
        names = [n.strip() for n in re.split(r"[|,]", matcher) if n.strip()]
        return tool_name in names
    return re.search(matcher, tool_name or "") is not None


def git_bash():
    """Find Git Bash on Windows. Never the System32/WindowsApps bash.exe, which is the WSL launcher."""
    explicit = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if explicit and pathlib.Path(explicit).is_file():
        return explicit
    candidates = []
    on_path = shutil.which("bash")
    if on_path and not WSL_LAUNCHER.search(on_path):
        candidates.append(pathlib.Path(on_path))
    git = shutil.which("git")
    if git:
        g = pathlib.Path(git).resolve()
        candidates += [g.parent.parent / "bin" / "bash.exe", g.parent / "bash.exe", g.parent.parent / "usr" / "bin" / "bash.exe"]
    candidates.append(pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe")
    return next((str(c) for c in candidates if c.is_file()), None)


def shell_argv(command, shell):
    if shell == "powershell":
        exe = shutil.which("pwsh") or shutil.which("powershell")
        return [exe, "-NoProfile", "-Command", command] if exe else None
    if os.name == "nt":
        bash = git_bash()
        if bash:
            return [bash, "-c", command]
        exe = shutil.which("pwsh") or shutil.which("powershell")
        return [exe, "-NoProfile", "-Command", command] if exe else None
    sh = shutil.which("sh")
    return [sh, "-c", command] if sh else None


def parse_stdout(text):
    """('plain', None) | ('json', dict) | ('bad', reason), following the hooks docs' rules for stdout."""
    s = (text or "").strip()
    if not (s.startswith("{") and s.endswith("}")):
        return "plain", None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        lines = [l for l in s.splitlines() if l.strip()]
        parsed = []
        for l in lines:
            try:
                parsed.append(json.loads(l))
            except json.JSONDecodeError:
                return "bad", "stdout starts with { and ends with } but is not valid JSON"
        known = set(BOOL_FIELDS + TEXT_FIELDS + ("decision", "hookSpecificOutput"))
        if any(isinstance(p, dict) and known & set(p) for p in parsed):
            return "bad", "stdout is several JSON lines, one of them a hook output object"
        return "plain", None
    if not isinstance(obj, dict):
        return "plain", None
    return "json", obj


def schema_problem(obj, event_name):
    """Why a JSON output object fails validation, or None."""
    for f in BOOL_FIELDS:
        if f in obj and not isinstance(obj[f], bool):
            return f"{f} must be true or false, got {obj[f]!r}"
    for f in TEXT_FIELDS:
        if f in obj and not isinstance(obj[f], str):
            return f"{f} must be text, got {obj[f]!r}"
    if "decision" in obj and obj["decision"] not in ("block", "approve"):
        return f"decision must be \"block\" or \"approve\", got {obj['decision']!r}"
    if "hookSpecificOutput" in obj:
        hso = obj["hookSpecificOutput"]
        if not isinstance(hso, dict):
            return "hookSpecificOutput must be an object"
        if hso.get("hookEventName") != event_name:
            return f"hookSpecificOutput needs hookEventName {event_name!r}, got {hso.get('hookEventName')!r}"
        if "permissionDecision" in hso and hso["permissionDecision"] not in DECISIONS:
            return f"permissionDecision must be one of {sorted(DECISIONS)}, got {hso['permissionDecision']!r}"
        for f in HSO_TEXT_FIELDS:
            if f in hso and not isinstance(hso[f], str):
                return f"{f} must be text, got {hso[f]!r}"
        if "updatedInput" in hso and not isinstance(hso["updatedInput"], dict):
            return "updatedInput must be an object"
    return None


def from_fields(obj, event_name):
    if obj.get("continue") is False:
        return "stop", "continue: false; Claude stops processing"
    hso = obj.get("hookSpecificOutput") or {}
    if event_name in CAN_BLOCK:
        decision = hso.get("permissionDecision")
        legacy = {"approve": "allow", "block": "deny"}.get(obj.get("decision"))  # deprecated for PreToolUse
        if decision is None and legacy is not None:
            decision, how = legacy, f"deprecated decision {obj['decision']!r}, read as {legacy}"
        else:
            how = f"permissionDecision {decision}"
            if decision is not None and legacy is not None and decision != legacy:
                return "error", (f"decision {obj['decision']!r} and permissionDecision {decision!r} disagree, "
                                 "and the docs do not say which wins")
        if decision == "deny":
            return "block", how
        if decision == "ask":
            return "ask", how
        return "allow", "no blocking decision"
    if obj.get("decision") == "block":
        return "feedback", "decision block (the tool has already run; this only gives Claude feedback)"
    return "allow", "no blocking decision"


class ProcessGroup:
    """Tracks everything a hook starts, so a process left running after the hook exits can be seen and ended."""

    def __init__(self):
        self.job = None
        self.attached = os.name != "nt"  # on POSIX the process group is made at start (start_new_session)
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            self.k = ctypes.WinDLL("kernel32", use_last_error=True)
            self.k.CreateJobObjectW.restype = wintypes.HANDLE
            self.k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
            self.k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            self.k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                                         wintypes.DWORD, wintypes.LPVOID]
            self.k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.k.CloseHandle.argtypes = [wintypes.HANDLE]
            self.job = self.k.CreateJobObjectW(None, None)

            class Accounting(ctypes.Structure):  # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION
                _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                            ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                            ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                            ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]
            self.Accounting = Accounting

    def popen_kwargs(self):
        return {} if os.name == "nt" else {"start_new_session": True}

    def attach(self, proc):
        if os.name == "nt":
            self.attached = bool(self.job) and bool(self.k.AssignProcessToJobObject(self.job, int(proc._handle)))

    def leftover(self, proc):
        """True if something the hook started is still running, False if not, None if that cannot be told."""
        if not self.attached:
            return None
        if os.name == "nt":
            import ctypes
            info = self.Accounting()
            if not self.k.QueryInformationJobObject(self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                return None
            return info.ActiveProcesses > 0
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return None
        return True

    def end(self, proc):
        if os.name == "nt":
            if self.job:
                self.k.TerminateJobObject(self.job, 1)
                self.k.CloseHandle(self.job)
                self.job = None
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass


def capture(argv, event, root, env, timeout):
    """Run a hook and read its output when its own process exits, as Claude Code does (the docs: it finishes
    reading shortly after the hook process exits). Returns (exit code, stdout, stderr, leftover)."""
    group = ProcessGroup()
    with tempfile.TemporaryFile() as fin, tempfile.TemporaryFile() as fout, tempfile.TemporaryFile() as ferr:
        fin.write(json.dumps(event).encode("utf-8"))
        fin.seek(0)
        proc = subprocess.Popen(argv, stdin=fin, stdout=fout, stderr=ferr, cwd=root, env=env, **group.popen_kwargs())
        try:
            group.attach(proc)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
            leftover = group.leftover(proc)
            texts = []
            for f in (fout, ferr):
                f.seek(0)
                texts.append(f.read().decode("utf-8", "replace"))
        finally:
            group.end(proc)
    return proc.returncode, texts[0], texts[1], leftover


def run_handler(handler, root, event, event_name):
    """(outcome, detail, failed): failed is what onFailure counts (an error, or an exit code other than 0 or 2)."""
    if not handler.get("command"):
        return "error", "handler has no command", True
    if handler.get("if"):
        return "not run", (f"handler has an \"if\" condition ({handler['if']!r}), which this script does not evaluate; "
                           "test this hook live in a Claude Code session"), False
    for f in ("async", "asyncRewake"):
        if f in handler and not isinstance(handler[f], bool):
            return "not run", f"{f} must be true or false, got {handler[f]!r} (a settings error; test live)", False
    if handler.get("async") or handler.get("asyncRewake"):
        return "allow", "async hook: runs in the background and cannot block or control Claude, so it was not run", False
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    sub = lambda s: str(s).replace("${CLAUDE_PROJECT_DIR}", str(root))
    if handler.get("args") is not None:
        exe = shutil.which(sub(handler["command"]))
        if not exe:
            return "not run", f"executable {handler['command']!r} not found on PATH", False
        if os.name == "nt" and WSL_LAUNCHER.search(exe):
            return "error", (f"{handler['command']!r} resolves to the WSL launcher {exe}, not Git Bash; "
                             "use python/node/powershell.exe in exec form, or shell form for bash scripts"), True
        argv = [exe] + [sub(a) for a in handler["args"]]
    else:
        argv = shell_argv(handler["command"], handler.get("shell"))
        if not argv:
            return "not run", "no suitable shell found", False
    try:
        code, stdout, stderr, leftover = capture(argv, event, root, env, handler.get("timeout", 600))  # docs' default
    except subprocess.TimeoutExpired:
        return "error", "timed out", True
    outcome, detail, failed = judge(code, stdout, stderr, event_name)
    # A process the hook left running can change what Claude Code does with the output (see the docstring).
    if outcome not in ("block", "stop", "error"):
        if leftover is None:
            return "not run", detail + (" (could not check whether the hook left a background process running; "
                                        "test this hook live)"), False
        if leftover:
            return "not run", detail + (" (the hook exited but left a background process running. Claude Code reads "
                                        "the output shortly after the hook exits, so a later deny does not block, and "
                                        "an allow whose background process kept the output streams open is refused as "
                                        "a suspect capture. Which applies cannot be told from here; test this hook "
                                        "live)"), False
    return outcome, detail, failed


def judge(returncode, stdout, stderr, event_name):
    """(outcome, detail, failed) from what a hook exit code and captured output mean, per the hooks docs."""
    stderr = (stderr or "").strip()
    detail = f"exit {returncode}; stderr: {stderr[:200]!r}"
    other_exit = returncode not in (0, 2)
    if returncode != 0 and COULD_NOT_START.search(stderr):
        return "error", detail + " (the hook could not start)", True
    kind, obj = parse_stdout(stdout)
    problem = obj if kind == "bad" else (schema_problem(obj, event_name) if kind == "json" else None)
    if returncode == 2:  # blocks whatever the JSON says; valid JSON is still read
        if kind == "json" and not problem and obj.get("continue") is False:
            return "stop", detail + " (exit 2 with continue: false)", False
        if event_name in CAN_BLOCK:
            return "block", detail, False
        return "feedback", detail + " (the tool has already run; this only gives Claude feedback)", False
    if problem:
        return "error", detail + f" ({problem}: a non-blocking error, so the action goes ahead)", True
    if kind == "json":
        outcome, why = from_fields(obj, event_name)
        if outcome == "error":
            return "error", detail + f" ({why}: a non-blocking error, so the action goes ahead)", True
        return outcome, detail + f" ({why}" + ("; the exit code is ignored)" if other_exit else ")"), other_exit
    if other_exit:
        return "error", detail + " (non-blocking error: the action goes ahead)", True
    return "allow", detail, False


def other_settings(root, settings):
    """Settings files besides the one under test that also apply in a live session (managed settings not read)."""
    user_dir = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
    candidates = [root / ".claude" / "settings.json", root / ".claude" / "settings.local.json", user_dir / "settings.json"]
    seen, out = {settings.resolve()}, []
    for c in candidates:
        if c.exists() and c.resolve() not in seen:
            seen.add(c.resolve())
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser(description="Test a project's hooks against a sample event.")
    ap.add_argument("--project", required=True, help="project root (where .claude/ lives)")
    ap.add_argument("--settings", help="settings file (default: <project>/.claude/settings.json)")
    ap.add_argument("--event-json", required=True, help='event JSON, e.g. {"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /"}}')
    ap.add_argument("--expect", required=True, choices=["block", "ask", "allow", "feedback", "stop"])
    args = ap.parse_args()

    root = pathlib.Path(args.project).resolve()
    settings = pathlib.Path(args.settings) if args.settings else root / ".claude" / "settings.json"
    try:
        config = json.loads(settings.read_text(encoding="utf-8"))
        hooks = config.get("hooks", {})
        event = json.loads(args.event_json)
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        print(f"NOT RUN: {exc}")
        sys.exit(2)
    name = event.get("hook_event_name") if isinstance(event, dict) else None
    if not name:
        print("NOT RUN: the event JSON needs hook_event_name (for example PreToolUse)")
        sys.exit(2)
    if name not in SUPPORTED:
        print(f"NOT RUN: {name} hooks are out of scope for this script (PreToolUse and PostToolUse only); test them live")
        sys.exit(2)
    if "disableAllHooks" in config and not isinstance(config["disableAllHooks"], bool):
        print(f"NOT RUN: disableAllHooks in {settings} must be true or false, got {config['disableAllHooks']!r}")
        sys.exit(2)
    for other in other_settings(root, settings):
        try:
            data = json.loads(other.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"NOT RUN: {other} also applies in a live session but cannot be read ({exc})")
            sys.exit(2)
        if not isinstance(data, dict):
            continue
        if "disableAllHooks" in data:
            print(f"NOT RUN: {other} sets disableAllHooks, so whether these hooks run depends on settings precedence; "
                  "test this guard live")
            sys.exit(2)
        live = [h for g in (data.get("hooks") or {}).get(name, []) if matches(g.get("matcher"), event.get("tool_name"))
                for h in g.get("hooks", [])]
        if live:
            print(f"NOTE     {len(live)} more {name} hook(s) in {other} also run in a live session; not run here")
    groups = [g for g in hooks.get(name, []) if matches(g.get("matcher"), event.get("tool_name"))]
    others = [h for g in groups for h in g.get("hooks", []) if h.get("type") != "command"]
    if others:
        print(f"NOT RUN: {len(others)} matching handler(s) of type {sorted({str(h.get('type')) for h in others})} "
              "cannot be run by this script; test them live")
        sys.exit(2)
    handlers = [h for g in groups for h in g.get("hooks", [])]
    if not handlers:
        print(f"NOT RUN: no command hooks for {name} match tool {event.get('tool_name')!r} in {settings}")
        sys.exit(2)

    disabled = config.get("disableAllHooks") is True
    if disabled:
        print(f"disableAllHooks is true in {settings}: Claude Code runs none of these hooks")
    outcomes = []
    for h in handlers:
        outcome, detail, failed = ("allow", "not run: disableAllHooks", False) if disabled else run_handler(h, root, event, name)
        if failed and h.get("onFailure") == "block":
            if name in CAN_BLOCK:
                outcome, detail = "block", detail + " (onFailure: block; needs Claude Code v2.1.295 or later)"
            else:  # a failure does what exit 2 does on that event: PostToolUse feedback, the tool already ran
                outcome = "feedback"
                detail += " (onFailure: block acts as exit 2 on PostToolUse, feedback only; needs Claude Code v2.1.295 or later)"
        outcomes.append(outcome)
        print(f"{outcome:8s} {h.get('command')} {' '.join(str(a) for a in h.get('args') or [])}  ({detail})")
    if "not run" in outcomes:
        print("NOT RUN: at least one hook could not be started or is outside what this script models (see above)")
        sys.exit(2)
    result = next(o for o in ("stop", "block", "ask", "feedback", "allow") if o in outcomes or o == "allow")
    ok = result == args.expect and "error" not in outcomes
    print(f"\nExpected {args.expect}, got {result}" + (" with errors" if "error" in outcomes else "")
          + (": PASS" if ok else ": FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # any crash means the test did not run, never a pass or a fail
        print(f"NOT RUN: {type(exc).__name__}: {exc}")
        sys.exit(2)
