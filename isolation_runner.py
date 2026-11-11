"""P6.10 real OS-level isolation runner (Linux namespaces in a disposable WSL distro).

Runs a workload script inside:
  - a new mount namespace with a tmpfs root containing ONLY: the Python runtime
    (/usr/lib + the python binary, read-only), the input dir (read-only) and a
    work dir (read-write). No /bin/sh, no /etc, no /home, no /mnt (no Windows drives).
  - a new network namespace (loopback only, down): no egress, no host services.
  - a new PID namespace, as uid/gid 65534 (nobody) with RLIMIT_NPROC=1 so the
    workload cannot fork or spawn processes.

It is used only with harmless fixtures and UVP-owned workloads. It does NOT
isolate Hermes Skill execution: Hermes is not run inside it (Safebox remains
POLICY_ONLY / NOT_ISOLATED for Hermes).

Requirements: Windows host with WSL, a DISPOSABLE distro where the default user
is root (default `ae2e-t01`), and the util-linux tools `unshare`, `chroot`, `prlimit`.
Nothing is installed.
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import tarfile
import uuid
from pathlib import Path

if __package__:
    from .port_core import PortError
else:
    from port_core import PortError

DEFAULT_DISTRO = "ae2e-t01"
SCHEMA = "universal-port.isolation-run/1"

_SCRIPT = r"""
set -eu
ID="$1"; MODE="$2"
B="/tmp/uvp-iso-$ID"
mkdir -p "$B/in" "$B/work"
printf '%s' "$UVP_PAYLOAD" | base64 -d > "$B/bundle.tgz"
tar -xzf "$B/bundle.tgz" -C "$B/in"
chmod -R a+rX "$B/in"; chmod 0777 "$B/work"
PY="$(readlink -f /usr/bin/python3)"
# Host-side loopback listener so the network probe has a real target outside the sandbox.
python3 -c 'import socket,time;s=socket.socket();s.bind(("127.0.0.1",48712));s.listen(5);time.sleep(30)' &
LPID=$!
sleep 0.5
if [ "$MODE" = control ]; then
  ( cd "$B/in" && UVP_ISO_INPUT="$B/in" UVP_ISO_WORK="$B/work" python3 -I "$B/in/workload.py" ) > "$B/out.json" 2>"$B/err.txt" || true
else
  unshare --mount --net --pid --fork --mount-proc=/proc /bin/bash -c '
    set -eu
    B="$1"; PY="$2"; R="$B/root"
    mount --make-rprivate /
    mkdir -p "$R"; mount -t tmpfs -o size=64m,mode=0755 tmpfs "$R"
    mkdir -p "$R/usr/lib" "$R/usr/bin" "$R/input" "$R/work" "$R/tmp" "$R/proc"
    mount --bind /usr/lib "$R/usr/lib"; mount -o remount,bind,ro "$R/usr/lib"
    [ -d /usr/lib64 ] && { mkdir -p "$R/usr/lib64"; mount --bind /usr/lib64 "$R/usr/lib64"; mount -o remount,bind,ro "$R/usr/lib64"; ln -s usr/lib64 "$R/lib64"; }
    ln -s usr/lib "$R/lib"
    touch "$R/usr/bin/python3"; mount --bind "$PY" "$R/usr/bin/python3"; mount -o remount,bind,ro "$R/usr/bin/python3"
    mount --bind "$B/in" "$R/input"; mount -o remount,bind,ro "$R/input"
    mount --bind "$B/work" "$R/work"
    chmod 1777 "$R/tmp"
    mount -t proc proc "$R/proc"
    cd /
    UVP_ISO_INPUT=/input UVP_ISO_WORK=/work prlimit --nproc=1:1 chroot --userspec=65534:65534 "$R" /usr/bin/python3 -I /input/workload.py
  ' _ "$B" "$PY" > "$B/out.json" 2>"$B/err.txt" || true
fi
kill $LPID 2>/dev/null || true
printf '%s' '@@UVP-ISO-BEGIN@@'; cat "$B/out.json"; printf '%s' '@@UVP-ISO-END@@'
printf '%s' '@@UVP-ISO-ERR@@'; head -c 2000 "$B/err.txt" || true
ls -la "$B/work" > "$B/worklist.txt" 2>&1 || true
printf '%s' '@@UVP-ISO-WORK@@'; cat "$B/worklist.txt"
printf '%s' '@@UVP-ISO-OUT@@'; ( cd "$B/work" && find . -maxdepth 1 -type f -size -256k -print0 | tar --null -T - -czf - 2>/dev/null | base64 -w0 ) || true
printf '%s' '@@UVP-ISO-DONE@@'
rm -rf "$B"
"""


def _bundle(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def run(workload: bytes, inputs: dict | None = None, *, mode: str = "isolated",
        distro: str = DEFAULT_DISTRO, timeout: int = 120, run_id_override: str | None = None) -> dict:
    if mode not in ("isolated", "control"):
        raise PortError("mode must be isolated or control")
    files = {"workload.py": workload, **(inputs or {})}
    if any(("/" in n.strip("/") and ".." in n) or n.startswith("/") for n in files):
        raise PortError("Unsafe bundle member name")
    run_id = run_id_override or uuid.uuid4().hex[:12]
    payload = base64.b64encode(_bundle(files))
    # Script and payload travel on stdin (LF only); WSL re-quotes argv, so no script in argv.
    script = ("UVP_PAYLOAD='" + payload.decode("ascii") + "'\n" + _SCRIPT).encode("utf-8").replace(b"\r\n", b"\n")
    try:
        proc = subprocess.run(["wsl", "-d", distro, "--", "bash", "-s", "--", run_id, mode],
                              input=script, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        cleanup(run_id, distro)
        raise PortError("Isolated run timed out; workspace cleaned up")
    except OSError as exc:
        raise PortError("Isolation runner unavailable: " + type(exc).__name__)
    if proc.returncode != 0 and b"@@UVP-ISO-BEGIN@@" not in proc.stdout:
        raise PortError("Isolation runner unavailable (distro %s): %s" % (distro, proc.stderr.decode("utf-16-le", "replace")[-300:].strip() or proc.returncode))
    out = proc.stdout.decode("utf-8", "replace")
    if "@@UVP-ISO-BEGIN@@" not in out:
        raise PortError("Isolation runner produced no result: " + proc.stderr.decode("utf-8", "replace")[-500:])
    body = out.split("@@UVP-ISO-BEGIN@@", 1)[1]
    result_txt, rest = body.split("@@UVP-ISO-END@@", 1)
    err, work = rest.split("@@UVP-ISO-ERR@@", 1)[1].split("@@UVP-ISO-WORK@@", 1)
    outputs = {}
    if "@@UVP-ISO-OUT@@" in work:
        work, packed = work.split("@@UVP-ISO-OUT@@", 1)
        packed = packed.split("@@UVP-ISO-DONE@@", 1)[0].strip()
        if packed:
            with tarfile.open(fileobj=io.BytesIO(base64.b64decode(packed)), mode="r:gz") as tar:
                for m in tar.getmembers():
                    name = m.name[2:] if m.name.startswith("./") else m.name
                    if m.isfile() and "/" not in name and "\\" not in name and name not in ("", ".", ".."):
                        outputs[name] = tar.extractfile(m).read()
    try:
        result = json.loads(result_txt) if result_txt.strip() else None
    except ValueError:
        result = None
    return {"schema": SCHEMA, "mode": mode, "distro": distro, "run_id": run_id, "returncode": proc.returncode,
            "result": result, "stderr_tail": err.strip()[-1500:], "work_listing": work.strip(), "outputs": outputs}


def cleanup(run_id: str, distro: str = DEFAULT_DISTRO) -> bool:
    """Remove a run's workspace after an interrupted run. Returns True if it is gone."""
    if not run_id.isalnum():
        raise PortError("bad run id")
    subprocess.run(["wsl", "-d", distro, "--", "rm", "-rf", "/tmp/uvp-iso-" + run_id], capture_output=True, timeout=60)
    chk = subprocess.run(["wsl", "-d", distro, "--", "test", "-e", "/tmp/uvp-iso-" + run_id], capture_output=True, timeout=60)
    return chk.returncode != 0


PROBE_WORKLOAD = rb'''
import json, os, socket
inp, work = os.environ["UVP_ISO_INPUT"], os.environ["UVP_ISO_WORK"]
r = {}
def attempt(name, fn):
    try:
        v = fn(); r[name] = {"ok": True, "detail": str(v)[:120]}
    except BaseException as e:
        r[name] = {"ok": False, "error": type(e).__name__ + ": " + str(e)[:120]}
attempt("read_input_fixture", lambda: open(os.path.join(inp, "fixture.txt")).read())
attempt("write_work_output", lambda: open(os.path.join(work, "out.txt"), "w").write("ok"))
attempt("write_input_readonly", lambda: open(os.path.join(inp, "tamper.txt"), "w").write("x"))
attempt("read_etc_hostname", lambda: open("/etc/hostname").read())
attempt("list_windows_drive", lambda: len(os.listdir("/mnt/c")))
attempt("list_root_home", lambda: len(os.listdir("/root")))
attempt("connect_host_loopback_listener", lambda: socket.create_connection(("127.0.0.1", 48712), timeout=2).close())
attempt("fork_process", lambda: (lambda pid: (os._exit(0) if pid == 0 else os.waitpid(pid, 0)))(os.fork()))
attempt("shell_binary_present", lambda: os.stat("/bin/sh"))
attempt("uid", lambda: os.getuid())
print(json.dumps(r, sort_keys=True))
'''
