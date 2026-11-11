"""P6.12 WP7: build a clean public-release snapshot (LOCAL ONLY; never pushes or publishes).

  python scripts/make_public_snapshot.py <commit> <new-output-dir>

- Exports the tree at <commit> with `git archive` (no .git history, no old identities).
- Applies only the declared SANITIZE rules (personal account names, machine host name),
  recording every changed file in SANITIZATION_MANIFEST.json with the private and public
  SHA-256 and the rule, so no sanitized file is ever presented as byte-identical.
- Scans the result for e-mails, account/machine identifiers, secrets, env files and
  committed bytecode/binaries, and writes PUBLIC_RELEASE_AUDIT.json. Any finding = HOLD.
- Creates a single local commit with a noreply identity so the exact public SHA is
  known for the catalog pin. Creating or pushing a remote repository is NOT done here.
"""
import hashlib
import os
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NOREPLY = "friendly-neighborhood-coding-man <132266321+friendly-neighborhood-coding-man@users.noreply.github.com>"
# Personal identifiers are NOT stored in this repository. They come from the operator's
# environment: UVP_PRIVATE_ACCOUNT (Windows account name) and UVP_PRIVATE_HOST (machine name).
_ACCOUNT = os.environ.get("UVP_PRIVATE_ACCOUNT", "")
_HOST = os.environ.get("UVP_PRIVATE_HOST", "")
SANITIZE = []
SCAN = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("secret", re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|"
                          r"-----BEGIN [A-Z ]*PRIVATE KEY")),
]
if _ACCOUNT:
    SANITIZE.append(("windows-user-path", re.compile(r"(?i)(C:(?:\\\\|\\|/)Users(?:\\\\|\\|/))" + re.escape(_ACCOUNT) + r"\b"), r"\1<user>"))
    SCAN.append(("personal-account", re.compile(r"(?i)\b" + re.escape(_ACCOUNT) + r"\b")))
if _HOST:
    SANITIZE.append(("machine-hostname", re.compile(r"\b" + re.escape(_HOST) + r"\b(?![0-9]*@)"), "<host>"))
    SCAN.append(("hostname", re.compile(r"\b" + re.escape(_HOST) + r"\b(?![0-9]*@)")))
EMAIL_OK = {"132266321+friendly-neighborhood-coding-man@users.noreply.github.com", "noreply@anthropic.com"}
FORBIDDEN_NAMES = re.compile(r"(^|/)(\.env(\..*)?|auth\.json|.*\.pem|.*\.pyc|.*\.pyo|state\.db.*)$")
BINARY_MAGIC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\x00asm")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(commit, out):
    if not (_ACCOUNT and _HOST):
        raise SystemExit("Set UVP_PRIVATE_ACCOUNT and UVP_PRIVATE_HOST so personal identifiers can be redacted and scanned")
    out = Path(out)
    if out.exists():
        raise SystemExit("Refusing: output exists")
    full = subprocess.run(["git", "-C", str(REPO), "rev-parse", commit], capture_output=True, text=True, check=True).stdout.strip()
    raw = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", full], capture_output=True, check=True).stdout
    out.mkdir(parents=True)
    changed, findings = [], []
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            data = tar.extractfile(m).read()
            rel = m.name
            new = data
            rules = []
            if b"\x00" not in data[:4096]:
                text = data.decode("utf-8", "surrogateescape")
                for rid, rx, rep in SANITIZE:
                    t2 = rx.sub(rep, text)
                    if t2 != text:
                        rules.append(rid)
                        text = t2
                new = text.encode("utf-8", "surrogateescape")
            if rules:
                changed.append({"path": rel, "private_sha256": sha(data), "public_sha256": sha(new), "rules": rules})
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new)
            if FORBIDDEN_NAMES.search(rel):
                findings.append({"path": rel, "kind": "forbidden-file"})
            if new[:4] in BINARY_MAGIC or new[:2] == b"MZ":
                findings.append({"path": rel, "kind": "binary"})
            if b"\x00" not in new[:4096]:
                s = new.decode("utf-8", "replace")
                for kind, rx in SCAN:
                    for hit in rx.findall(s):
                        h = hit if isinstance(hit, str) else hit[0]
                        if kind == "email" and (h in EMAIL_OK or h.endswith("@example.com") or h.endswith(".invalid")):
                            continue
                        findings.append({"path": rel, "kind": kind, "match": h[:60]})
    note = ("# Sanitized public snapshot\n\nExported from private commit `%s` with `git archive` (no history).\n"
            "Files listed in `SANITIZATION_MANIFEST.json` had personal identifiers (Windows account name, machine host name)\n"
            "replaced; their SHA-256 differs from the private originals and is recorded there. All other files are byte-identical\n"
            "to the private commit.\n" % full)
    (out / "SANITIZATION_NOTE.md").write_text(note, encoding="utf-8")
    (out / "SANITIZATION_MANIFEST.json").write_text(json.dumps({"private_commit": full, "rules": [r[0] for r in SANITIZE],
                                                                "changed_files": changed}, indent=2) + "\n", encoding="utf-8")
    audit = {"private_commit": full, "files": sum(1 for p in out.rglob("*") if p.is_file()), "findings": findings,
             "verdict": "CLEAN" if not findings else "HOLD"}
    (out / "PUBLIC_RELEASE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "friendly-neighborhood-coding-man", "GIT_COMMITTER_NAME": "friendly-neighborhood-coding-man",
           "GIT_AUTHOR_EMAIL": NOREPLY.split("<")[1][:-1], "GIT_COMMITTER_EMAIL": NOREPLY.split("<")[1][:-1]}
    e = {**os.environ, **env}
    subprocess.run(["git", "init", "-q", "-b", "main", str(out)], check=True, env=e)
    subprocess.run(["git", "-C", str(out), "-c", "core.autocrlf=false", "add", "-A"], check=True, env=e)
    subprocess.run(["git", "-C", str(out), "commit", "-q", "-m",
                    "Universal Plugin Port v0.6.0 public snapshot (from private %s)" % full[:12]], check=True, env=e)
    pub = subprocess.run(["git", "-C", str(out), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    ident = subprocess.run(["git", "-C", str(out), "log", "--format=%an <%ae>|%cn <%ce>"], capture_output=True, text=True).stdout.strip()
    print(json.dumps({"public_commit": pub, "identity": ident, "sanitized_files": len(changed), "audit": audit["verdict"],
                      "findings": findings[:10]}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
