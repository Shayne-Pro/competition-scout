#!/usr/bin/env python3
"""Check current distributable files, without reading or printing secret values.

Uses Git's tracked and non-ignored files when available; also works in an
extracted source archive. This is a basic guard, not a full history audit.
"""
from pathlib import Path, PurePosixPath
import re
import subprocess

BASE = Path(__file__).resolve().parent
PRIVATE_DIRS = {".workbuddy", ".codex", ".scout", ".kaggle", ".venv", "venv"}
PRIVATE_NAMES = {"notified.json", "runs-log.jsonl", "kaggle.json"}
SECRET_PATTERNS = {
    "GitHub token": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "private key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "cloud access ID": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
    "API token": rb"\bsk-[A-Za-z0-9_-]{24,}",
}
LOCAL_PATH = re.compile(rb'''(?<![A-Za-z0-9:./])(?:/(?:Users|home)/[^/\s"']+/|[A-Za-z]:\\Users\\[^\\\s"']+\\)''')


def forbidden_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return "path outside project"
    if set(path.parts) & PRIVATE_DIRS:
        return "local state or environment"
    if path.name in PRIVATE_NAMES or path.name.endswith((".pem", ".key", ".p12", ".pfx")):
        return "local log or credential file"
    if path.name.startswith(".env") and path.name != ".env.example":
        return "environment secrets file"
    if path.name.endswith(".json") and path.name.startswith(("spa_snapshot", "secondary_snapshot")):
        return "generated browser snapshot"
    return None


def project_files(base):
    try:
        top = subprocess.check_output(["git", "-C", str(base), "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True).strip()
        if Path(top).resolve() == base.resolve():
            listing = subprocess.check_output(["git", "-C", str(base), "ls-files", "--cached", "--others", "--exclude-standard", "-z"], text=True)
            return sorted(set(filter(None, listing.split("\0"))))
    except (OSError, subprocess.CalledProcessError):
        pass
    ignored = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}
    return sorted(str(p.relative_to(base).as_posix()) for p in base.rglob("*")
                  if not set(p.relative_to(base).parts) & ignored and (p.is_file() or p.is_symlink()))


def scan_files(base, names):
    errors = []
    for name in names:
        reason = forbidden_path(name)
        if reason:
            errors.append(f"{name}: {reason}")
            continue
        path = base / name
        if path.is_symlink():
            errors.append(f"{name}: symbolic link")
            continue
        if not path.is_file():
            continue
        body = path.read_bytes()
        if LOCAL_PATH.search(body):
            errors.append(f"{name}: machine-specific home path")
        for label, pattern in SECRET_PATTERNS.items():
            if re.search(pattern, body):
                errors.append(f"{name}: possible {label} (value withheld)")
    return errors


def main():
    names = project_files(BASE)
    errors = scan_files(BASE, names)
    for name in ("README.md", "LICENSE", "NOTICE.md"):
        if name not in names:
            errors.append(f"missing {name}")
    for error in errors:
        print("FAIL:", error)
    if not errors:
        print(f"PASS: {len(names)} current release files; no blocked local files, home paths or known token patterns. Git history not audited.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
