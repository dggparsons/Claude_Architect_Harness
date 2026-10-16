"""Scan a project for committed or stray secrets, printing masked values only.

Usage:  python -I secrets_scan.py [project-path]

What it reads
- Every file under the project, including gitignored ones (an ignored file can still be tracked if it
  was committed before it was ignored). The walk skips .git, node_modules, real virtual environments
  (a folder with a pyvenv.cfg that has a "home =" line and a bin/ or Scripts/ folder) and tool caches,
  but every file git tracks is scanned wherever it is. Each skipped folder is listed as SKIPDIR with the
  number of untracked files in it that were not scanned, and sensitive file names inside it are still
  listed. Unscanned files make the exit code 1: they were not checked.
- The staged (index) copy of every tracked file whose content differs from the working tree, compared
  by blob id, so skip-worktree and assume-unchanged files are covered too. It does not read older commits.
- Files whose real location is outside the project (reached through a link or junction) are listed as
  SKIPPED, not followed.
- Nested repositories and submodules: each file's tracked status comes from the nearest repository.

What it recognises (and nothing else)
- Key formats: Anthropic, OpenAI-style, GitHub, AWS access key IDs, Slack, Bearer and Basic headers,
  private key blocks; credentials in URLs (scheme://user:pass@host).
- Command-line credentials: --password/--passwd/--pass/--pwd, -Password, ConvertTo-SecureString "...",
  -p after -u/-l on the same line or in an sshpass command (attached, as in mysql -pSecret, or
  separate), /p: and /password: (xfreerdp, rdesktop), curl -u/--user user:pass, and
  [domain/]user:pass@host targets (impacket style).
- Assignments to names that look like credentials (key, token, secret, auth, password, pwd, pass): in
  source code only when the value is quoted or inside a string; in config, .env, JSON and YAML also unquoted.
- Loot: NTLM in secretsdump form, user:NThash lists, DCC2, NetNTLMv2, Kerberos roasts, Unix crypt,
  bcrypt, Argon2, cracked hash:password potfile lines (32, 40 or 64 hex, optionally $NT$) and .netrc.
- Not recognised: credentials written as free text ("the admin password is ..."), other formats not
  listed here, and files outside the folder. Keep engagement loot out of tool repositories.
- Values that are obviously placeholders are skipped: variable references ($VAR, ${VAR}, %VAR%, {x},
  os.environ, process.env, getenv), <...>, and values that are exactly a placeholder word (changeme,
  example, placeholder, dummy, fake, test, redacted, a run of x or *, your-... or ...-here). A real password
  that merely starts with one of those words (Changeme123!) is reported. A PowerShell value starting
  with $ is treated as a variable even in single quotes.

What it prints
- Never a secret, and never the source line: each finding gives the file, line and column, what kind of
  secret it looks like (with the variable name for assignments) and the value's length only.
- Sensitive file names (key files, .env, private keys) with their git status; files it could not scan
  (over 2 MB, unreadable, outside the project, staged copies git could not read) as SKIPPED.

Exit codes: 0 no findings and everything scanned, 1 findings or anything not scanned (including binary files,
repositories git cannot read, and files that took more than SCAN_SECONDS), 2 the scan could not run.
Hits in documentation, tests or fixtures may be deliberate examples; a person judges each one.
"""
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

SCAN_SECONDS = 30  # per file; a file that takes longer is reported as not fully scanned
CHUNK = 20_000  # a longer line is scanned in pieces of this many characters, overlapping by OVERLAP
OVERLAP = 512
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
MAX_BYTES = 2_000_000
# (label, pattern, filter_placeholders, needs): group 1, when present, is the value; needs is an optional
# second pattern the same line must also match.
KNOWN = [
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), False, None),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}"), False, None),
    ("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}"), False, None),
    ("AWS access key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), False, None),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), False, None),
    ("Bearer token", re.compile(r"Bearer [A-Za-z0-9._~+/-]{30,}"), False, None),
    ("Basic auth header", re.compile(r"\bBasic [A-Za-z0-9+/]{16,}={0,2}"), False, None),
    ("Credentials in a URL", re.compile(r"\b[a-z][a-z0-9+.-]{0,40}://[^/\s:@'\"]{1,256}:([^@\s/'\"]{4,})@", re.I), True, None),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), False, None),
    # Password hashes and captured responses, the usual loot from a test: never filtered as placeholders
    ("NTLM hash (secretsdump format)", re.compile(r"^[^:\s]+:\d+:[a-fA-F0-9]{32}:([a-fA-F0-9]{32}):::", re.M), False, None),
    ("DCC2 hash (cached domain credentials)", re.compile(r"\$DCC2\$\d+#[^#\s]+#[a-fA-F0-9]{32}", re.I), False, None),
    ("NetNTLMv2 response", re.compile(r"[^:\s]{1,256}::[^:\s]{1,256}:([a-fA-F0-9]{16}:[a-fA-F0-9]{32}:[a-fA-F0-9]{16,})"), False, None),
    ("Kerberos hash (roast)", re.compile(r"\$krb5(?:tgs|asrep|pa)\$[^\s]{20,}"), False, None),
    ("Unix crypt hash", re.compile(r"\$(?:1|5|6|y)\$[^$\s]{1,32}\$[./A-Za-z0-9]{20,}"), False, None),
    ("bcrypt hash", re.compile(r"\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}"), False, None),
    ("Argon2 hash", re.compile(r"\$argon2(?:id|i|d)\$v=\d+\$[^\s]+\$[^\s]+"), False, None),
    ("Cracked hash (potfile line)",
     re.compile(r"^\s*(?:\$NT\$)?(?:[a-fA-F0-9]{64}|[a-fA-F0-9]{40}|[a-fA-F0-9]{32}):(\S.*?)\s*$", re.M), False, None),
    ("NT hash list (user:hash)", re.compile(r"^\s*[^:\s]+:([a-fA-F0-9]{32})\s*$", re.M), False, None),
    # Credentials on command lines
    ("Plain-text SecureString", re.compile(r"ConvertTo-SecureString\s+(?:-String\s+)?[\"']([^\"']{4,})[\"']", re.I), True, None),
    ("Password argument", re.compile(r"(?:^|\s)--?(?:password|passwd|pass|pwd)(?:\s+|=)[\"']?([^\s\"']{4,})", re.I), True, None),
    ("Password argument (-p)",  # a value of up to five digits is a port (ssh -l user -p 2222), not a password
     re.compile(r"(?:^|\s)-p(?:\s+[\"']?|[\"']?(?=[^\s\"'-]))(?!\d{1,5}(?:[\s\"']|$))([^\s\"']{3,})"), True,
     re.compile(r"(?:^|\s)-[ulU](?:\s+|(?=\S))\S|\bsshpass\b")),
    ("Password argument (/p:)", re.compile(r"(?:^|\s)/p(?:ass(?:word)?)?:[\"']?([^\s\"']{3,})", re.I), True, None),
    ("Credentials in -u user:pass", re.compile(r"(?:^|\s)(?:-u|--user)\s+[\"']?[^\s:\"']+:([^\s\"'@]{3,})"), True, None),
    ("Credentials in a user:pass@host target",
     re.compile(r"(?:^|[\s\"'])(?:[\w.-]+/)?[\w.$-]+:([^\s@\"'/:]{3,})@[\w.-]+"), True, None),
]
# name = value, where the name looks like a credential; group 2 is the opening quote (if any)
ASSIGNMENT = re.compile(r"""(?ix)
    (?<![A-Za-z0-9])([a-z0-9_.-]{0,60}(?:api[_-]?key|apikey|secret|token|passw(?:or)?d|pwd|pass|auth|key))
    ["']?\s*(?::=|:\s*[\w\[\], ]+\s*=|[:=])\s*(["'`]?)   # =, :, Go :=, annotated "name: str ="
    ([^\s"'`,;]{8,})
    """)
CREDENTIAL_WORD = re.compile(r"(?i)key|secret|token|pass|pwd|auth")  # every name ASSIGNMENT accepts contains one
# In source code a hard-coded secret is a literal; an unquoted value outside a string is a variable or call.
CODE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".java", ".cs", ".rb", ".php",
                 ".rs", ".kt", ".swift", ".c", ".cpp", ".h"}  # not .sh/.ps1: shell secrets are often unquoted
STRONG_NAME = re.compile(r"(?i)(passw|pwd|secret|(?:^|[_.-])pass$)")  # these names flag shorter values
# References to a value held elsewhere, recognised by how they start
VARIABLE_REF = re.compile(r"(?i)^(\$\{|\$[A-Z_(]|%[A-Z_]+%|%\(|\{|<|os\.environ|process\.env|getenv|env\()")
# Values that are exactly a placeholder word, not values that merely start with one
PLACEHOLDER = re.compile(r"(?i)^(changeme|change[_-]me|example|placeholder|dummy|fake|test|redacted|none|null|true|false"
                         r"|x{3,}|\*{3,}|your[_-][\w-]*|[\w-]*[_-]here)$")
NETRC_PASSWORD = re.compile(r"\bpassword\s+(\S{4,})")
SENSITIVE_NAMES = re.compile(r"(?i)(^\.env(\..+)?$|local_ai\.json$|credentials?\.json$|\.pem$|\.p12$|\.pfx$|^id_(rsa|ed25519|ecdsa)$|secrets?\.(json|ya?ml|toml)$|^[._]netrc$)")
HYPHEN_WORDS = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")  # user-profile-cache-key: an identifier, not a secret


def placeholder(value):
    v = value.strip("\"'`")
    return bool(VARIABLE_REF.search(v) or PLACEHOLDER.match(v))


def mask(value):
    # ASCII only, safe on any console; no characters of the value are shown, only its length
    return f"**** ({len(value)} chars)"


def run_git(*args, stdin=None):
    try:
        r = subprocess.run(["git", *args], capture_output=True, timeout=120, input=stdin)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r if r.returncode == 0 else None


def has_git_dir(root):
    return any((p / ".git").exists() for p in [root, *root.parents])


def find_repos(root):
    """Return {repo_root: set of tracked paths relative to that repo}, or None if git is unusable.
    A repository git cannot read maps to None instead of a set, so it is reported and never hides the others."""
    if not shutil.which("git"):
        return None
    repos = {}
    top = run_git("-C", str(root), "rev-parse", "--show-toplevel")
    if top is not None:
        repos[pathlib.Path(top.stdout.decode("utf-8", "replace").strip()).resolve()] = None
    elif has_git_dir(root):
        return None  # a repository exists but git cannot read it: status unknown
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames or ".git" in filenames:  # nested repository or submodule
            repos.setdefault(pathlib.Path(dirpath).resolve(), None)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for repo in list(repos):
        out = run_git("-C", str(repo), "ls-files", "-z")
        if out is None:
            continue  # stays None: this repository is unreadable; main() reports it, the others are still scanned
        repos[repo] = {p for p in out.stdout.decode("utf-8", "replace").split("\0") if p}
    return repos


def staged_to_scan(repo):
    """[(path relative to repo, blob id or None for a conflict)] for index entries whose content differs from
    the working tree (or whose working file is gone), compared by blob id; None if git fails."""
    out = run_git("-C", str(repo), "-c", "core.quotepath=off", "ls-files", "-s", "-z")
    if out is None:
        return None
    entries, conflicts = {}, set()
    for rec in out.stdout.decode("utf-8", "replace").split("\0"):
        if not rec:
            continue
        meta, _, path = rec.partition("\t")
        mode, blob, stage = meta.split()
        if mode == "160000":  # a submodule: its own repository is scanned separately
            continue
        if stage != "0":
            conflicts.add(path)
        else:
            entries[path] = blob
    present = [p for p in entries if (repo / p).is_file()]
    hashed = {}
    if present:
        h = run_git("-C", str(repo), "hash-object", "--stdin-paths", stdin="\n".join(present).encode("utf-8"))
        if h is None:
            return None
        hashed = dict(zip(present, h.stdout.decode("ascii", "replace").split()))
    result = [(p, b) for p, b in entries.items() if hashed.get(p) != b]
    return result + [(p, None) for p in sorted(conflicts)]


def status_of(path, repos):
    if repos is None:
        return "git status unknown (git missing or failing)"
    owners = [r for r in repos if r == path.parent or r in path.parents]
    if not owners:
        return "not in a git repo"
    repo = max(owners, key=lambda r: len(r.parts))  # the nearest repository wins
    if repos[repo] is None:
        return "git status unknown (repository unreadable)"
    rel = path.relative_to(repo).as_posix()
    return "TRACKED in git" if rel in repos[repo] else "untracked"


def is_venv(folder):
    cfg = folder / "pyvenv.cfg"
    if not cfg.is_file() or not ((folder / "bin").is_dir() or (folder / "Scripts").is_dir()):
        return False
    try:
        return re.search(r"(?m)^\s*home\s*=", cfg.read_text(encoding="utf-8", errors="replace")) is not None
    except OSError:
        return False


def files_under(folder):
    """Every file below folder, leaving out .git folders (a repository's own data is not project content)."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        found.update((pathlib.Path(dirpath) / f).resolve() for f in filenames)
    return found


def walk(root, repos, skipped_dirs):
    """Yield files to scan. Records each pruned folder in skipped_dirs as {folder: set of files under it}."""
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            full = pathlib.Path(dirpath) / d
            if d in SKIP_DIRS or is_venv(full):
                if d != ".git":
                    skipped_dirs[full] = files_under(full)
            else:
                keep.append(d)
        dirnames[:] = keep
        for name in filenames:
            p = (pathlib.Path(dirpath) / name).resolve()
            seen.add(p)
            yield p
    for repo, tracked in (repos or {}).items():  # tracked files inside skipped folders are still scanned
        for rel in tracked or ():
            p = (repo / rel).resolve()
            if p not in seen and p.is_file() and (p == root or root in p.parents):
                seen.add(p)
                yield p
    for folder, files in skipped_dirs.items():  # what remains is what was not scanned
        files -= seen


def read_text(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8-sig", "replace")


def string_state(line):
    """A bytearray with 1 at each position that is inside a quoted string, found in one pass that honours
    backslash escapes (so a long line costs linear time, however many matches it has)."""
    state = bytearray(len(line) + 1)
    quote, i, n = None, 0, len(line)
    while i < n:
        state[i] = quote is not None
        c = line[i]
        if quote and c == "\\":
            if i + 1 < n:
                state[i + 1] = 1
            i += 2
            continue
        if quote is None and c in "\"'`":
            quote = c
        elif c == quote:
            quote = None
        i += 1
    state[n] = quote is not None
    return state


def scan_line(line, is_netrc, is_code):
    """[(label, value, column)] for each secret on the line; overlapping matches count once."""
    hits, spans = [], []

    def overlaps(a, b):
        return any(a < y and x < b for x, y in spans)

    for label, pattern, filtered, needs in KNOWN:  # ordered most specific first
        if needs is not None and not needs.search(line):
            continue
        for m in pattern.finditer(line):
            value = m.group(1) if pattern.groups else m.group(0)
            start = m.start(1) if pattern.groups else m.start()
            if overlaps(*m.span()) or (filtered and placeholder(value)):
                continue
            spans.append(m.span())
            hits.append((label, value, start + 1))
    in_string = None
    for m in (ASSIGNMENT.finditer(line) if CREDENTIAL_WORD.search(line) else ()):  # cheap check before the costly pattern
        name, quote, value = m.group(1), m.group(2), m.group(3)
        if overlaps(*m.span(3)) or placeholder(value):
            continue
        if is_code and not quote:
            if in_string is None:
                in_string = string_state(line)
            if not in_string[m.start(1)]:
                continue
        strong = STRONG_NAME.search(name)
        if (len(value) < 16 and not strong) or (not strong and HYPHEN_WORDS.fullmatch(value)):
            continue
        spans.append(m.span(3))
        hits.append((f"assignment to {name}", value, m.start(3) + 1))
    if is_netrc:
        hits += [(".netrc password", m.group(1), m.start(1) + 1) for m in NETRC_PASSWORD.finditer(line)
                 if not placeholder(m.group(1))]
    return hits


def scan_chunks(line, is_netrc, is_code):
    """scan_line over a long line in overlapping pieces, so no single regex call has unbounded work."""
    if len(line) <= CHUNK:
        return scan_line(line, is_netrc, is_code)
    seen, hits = set(), []
    for start in range(0, len(line), CHUNK - OVERLAP):
        for label, value, col in scan_line(line[start:start + CHUNK], is_netrc, is_code):
            key = (label, col + start)
            if key not in seen:
                seen.add(key)
                hits.append((label, value, col + start))
    return hits


def scan_text(rel, text, status, is_netrc, is_code):
    """(number of findings, True if the whole text was scanned within SCAN_SECONDS)."""
    found = 0
    deadline = time.monotonic() + SCAN_SECONDS
    for n, line in enumerate(text.splitlines(), start=1):
        if time.monotonic() > deadline:
            return found, False
        for label, value, col in scan_chunks(line, is_netrc, is_code):
            found += 1
            print(f"FINDING  {rel}:{n} col {col}  {label}  value {mask(value)}  [{status}]")
    return found, True


def main():
    ap = argparse.ArgumentParser(description="Scan a project for secrets; prints masked values only.")
    ap.add_argument("project", nargs="?", default=".", help="project folder (default: current folder)")
    args = ap.parse_args()
    root = pathlib.Path(args.project).resolve()
    if not root.is_dir():
        print(f"NOT RUN: {root} is not a folder")
        sys.exit(2)
    repos = find_repos(root)
    state = "git status UNKNOWN: tracked/untracked not checked" if repos is None else (
        f"{len(repos)} git repositor{'y' if len(repos) == 1 else 'ies'}" if repos else "not a git repository")
    print(f"Secrets scan of {root} ({state})")
    findings = sensitive = skipped = binary = staged = 0
    tracked_sensitive = False
    if repos is None and has_git_dir(root):
        skipped += 1
        print("SKIPPED  git status and staged copies: git is missing or cannot read the repository, so tracked "
              "files and staged copies were not checked")
    for repo in sorted(r for r, tracked in (repos or {}).items() if tracked is None):
        skipped += 1
        print(f"SKIPPED  {repo}  git cannot read this repository, so its tracked files and staged copies were "
              "not checked")
    skipped_dirs = {}
    for path in walk(root, repos, skipped_dirs):
        if not (path == root or root in path.parents):
            skipped += 1
            print(f"SKIPPED  {path}  outside the project (reached through a link), not scanned")
            continue
        rel = path.relative_to(root).as_posix()
        status = status_of(path, repos)
        if SENSITIVE_NAMES.search(path.name):
            sensitive += 1
            tracked_sensitive |= status == "TRACKED in git"
            print(f"FILE     {rel}  sensitive file name  [{status}]")
        try:
            size = path.stat().st_size
            if size > MAX_BYTES:
                skipped += 1
                print(f"SKIPPED  {rel}  over 2 MB, not scanned  [{status}]")
                continue
            text = read_text(path.read_bytes())
        except OSError as exc:
            skipped += 1
            print(f"SKIPPED  {rel}  could not read ({exc.strerror})")
            continue
        if text is None:
            binary += 1
            skipped += 1
            print(f"SKIPPED  {rel}  binary file (contains NUL bytes), not scanned  [{status}]")
            continue
        n, complete = scan_text(rel, text, status, path.name.lower() in (".netrc", "_netrc"),
                                path.suffix.lower() in CODE_SUFFIXES)
        findings += n
        if not complete:
            skipped += 1
            print(f"SKIPPED  {rel}  scan stopped after {SCAN_SECONDS} seconds, rest of the file not scanned")
    # Staged copies that differ from the working tree: what the next commit would carry.
    for repo in [r for r, tracked in (repos or {}).items() if tracked is not None]:
        pending = staged_to_scan(repo)
        if pending is None:
            skipped += 1
            print(f"SKIPPED  staged copies in {repo}  git could not list or hash them, staged content not scanned")
            continue
        for relrepo, blob in sorted(pending, key=lambda t: t[0]):
            p = (repo / relrepo).resolve() if (repo / relrepo).exists() else repo / relrepo
            if not (p == root or root in p.parents):
                continue
            rel = p.relative_to(root).as_posix() + " (staged copy)"
            if blob is None:
                skipped += 1
                print(f"SKIPPED  {rel}  merge conflict, staged copy not scanned")
                continue
            data = run_git("-C", str(repo), "cat-file", "blob", blob)
            if data is None:
                skipped += 1
                print(f"SKIPPED  {rel}  could not read the staged copy")
                continue
            staged += 1
            if len(data.stdout) > MAX_BYTES:
                skipped += 1
                print(f"SKIPPED  {rel}  over 2 MB, not scanned  [STAGED in git]")
                continue
            text = read_text(data.stdout)
            if text is None:
                binary += 1
                skipped += 1
                print(f"SKIPPED  {rel}  binary file (contains NUL bytes), not scanned  [STAGED in git]")
                continue
            n, complete = scan_text(rel, text, "STAGED in git, differs from the working tree",
                                    p.name.lower() in (".netrc", "_netrc"), p.suffix.lower() in CODE_SUFFIXES)
            findings += n
            if not complete:
                skipped += 1
                print(f"SKIPPED  {rel}  scan stopped after {SCAN_SECONDS} seconds, rest of the file not scanned")
    unscanned = 0
    for folder, files in sorted(skipped_dirs.items()):
        if files:
            unscanned += len(files)
            try:
                shown = folder.relative_to(root).as_posix()
            except ValueError:
                shown = str(folder)
            print(f"SKIPDIR  {shown}  {len(files)} untracked files not scanned")
            for f in sorted(files):
                if SENSITIVE_NAMES.search(f.name):
                    sensitive += 1
                    print(f"FILE     {shown}/.../{f.name}  sensitive file name inside a skipped folder, not scanned")
    print(f"\n{findings} findings, {sensitive} sensitive files, {skipped} items not scanned (listed as SKIPPED; "
          f"{binary} of them binary files), {staged} staged copies scanned, "
          f"{unscanned} untracked files in skipped folders not scanned (listed as SKIPDIR). "
          "Judge each: a TRACKED or STAGED real key must be rotated and removed from history; examples in docs or tests are not findings. "
          "Anything SKIPPED or SKIPDIR was not checked: check it another way or record it as not run.")
    sys.exit(1 if findings or tracked_sensitive or skipped or unscanned else 0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # any crash means the scan did not run, never "no findings"
        print(f"NOT RUN: {type(exc).__name__}: {exc}")
        sys.exit(2)
