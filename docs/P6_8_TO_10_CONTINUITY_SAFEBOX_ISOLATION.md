# P6.8–P6.10: Skill continuity, Safebox and isolation (2026-11-11)

| Feature | Status | What is demonstrated | What is NOT claimed |
|---|---|---|---|
| P6.8 Skill continuity (`skill_continuity.py`) | **EXPERIMENTAL** (callbacks; not registered by `register()`) | Contracts bind the Skill, source SHA, installed body SHA, version and mandatory obligations. The child context is classified PRESENT, STALE or MISSING, and the contract is reloaded through the host loader with a hash check. A compact block (obligations plus a reload pointer, no full text) is attached. Delegation fails closed when the contract cannot be restored. 10 unit tests. Runtime check with real Hermes `skill_view` in the disposable home: `docs/evidence/p6-runtime/continuity-001.json` (3/3 attached, 3/3 fail closed). | No live `delegate_task` session has run with the hook registered. Hermes is the only adapter. |
| P6.9 Safebox (`safebox.py`) | **EXPERIMENTAL**, **POLICY_ONLY / NOT_ISOLATED** | Default-deny grants bound to source SHA and contract ID, covering fs read/write roots (realpath, symlink-escape check), network, shell, credentials, process and Skill-admin permissions, plus a tool allow-list. Activating a Skill requires a grant. Denials are audited without logging argument values. 8 tests. | **Not a security boundary.** Checks run inside the Hermes process at tool dispatch. `bypass_report()` lists slash invocation, `-s` preload and actors outside the hook, and never claims enforcement. |
| P6.10 Isolation (`isolation_runner.py`) | **IMPLEMENTED** for UVP-owned workloads, in a disposable WSL2 distro | Linux mount, network and PID namespaces. The tmpfs root holds only a read-only Python runtime, a read-only input and a read-write work dir. It runs as `nobody` with `RLIMIT_NPROC=1`. The control run allows every probe; the isolated run denies 7/7 out-of-scope probes. Evidence: `docs/evidence/p6-10-isolation/probe-run-001.json`. | **Hermes Skill execution is not run inside it.** For Hermes, the Safebox stays POLICY_ONLY. Unsafe foreign execution stays disabled. |

## P6.10 probe results

Host: Windows 11 with WSL2 kernel `6.18.54.1-microsoft-standard-WSL2`. Distro: disposable `ae2e-t01` (Ubuntu 24.04), `util-linux 2.39.3`. Nothing was installed.

| Probe (harmless) | Control (no isolation) | Isolated |
|---|---|---|
| read the input fixture | allowed | allowed |
| write the work output | allowed | allowed |
| write into the read-only input | allowed | **denied** (`EROFS`) |
| read `/etc/hostname` | allowed | **denied** (absent) |
| list `/mnt/c` (Windows drive) | allowed | **denied** (absent) |
| list `/root` | allowed | **denied** (absent) |
| connect to a host loopback listener | allowed | **denied** (`ENETUNREACH`) |
| `fork()` | allowed | **denied** (`EAGAIN`, `RLIMIT_NPROC`) |
| `/bin/sh` present | yes | **no** |
| uid | 0 | 65534 |

The probes make no external network calls. The network probe targets a listener the runner starts on the host's loopback interface.

**Reproduce:**

```bash
python -m unittest discover -s tests -p test_isolation_runner.py
```

The live test skips when WSL or the distro is absent.

## Limits

- WSL2 is a lightweight VM shared with the Windows host. These namespaces isolate the workload *inside* the distro. They do not defend against a WSL or kernel escape.
- The runner needs root in a disposable distro, and it must never be pointed at a non-disposable distro.
- `/usr/lib` is visible read-only to the workload, so library code is readable.
