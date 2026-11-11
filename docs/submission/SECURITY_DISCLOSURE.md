# Security disclosure: Universal Plugin Port v0.6.0 (P6)

**Status: draft for release notes and the catalog PR.** This is a self-assessment by the implementing agent, not an external audit.

## Trust model

- Foreign plugin source is **untrusted data**. UVP never imports or executes it during inspection or staging.
  - **Exception:** OpenClaw JavaScript inspection runs through a local `node` sidecar, and only after a separate explicit `run_foreign_code` consent. **That path is not sandboxed.**
- The generated Hermes package registers foreign Skill Markdown through a static, UVP-generated `__init__.py`. Foreign code is never on the import path.
  - Inline-shell syntax (`!` followed by a backtick snippet) is refused at staging. With Hermes's `skills.inline_shell` enabled, viewing such a Skill would execute it.
- Model output is never applied automatically.
  - Every AI proposal is an immutable review candidate.
  - Applying a candidate needs the exact candidate SHA-256, operator approval, independent post-proposal checks (host syntax, catalog resolution of slash commands, resource references, new network/credential/shell tokens, frontmatter changes) and a rejected-candidate ledger check.
- The deterministic rule registry cannot carry code, regexes, permissions, network access, execution or side effects. The loader refuses the whole registry otherwise.

## Known limitations and residual risks

| # | Risk | Severity | Mitigation / status |
|---|---|---|---|
| S1 | During P6 E2E run 001, Hermes `write_file` could have written anywhere not on Hermes's credential denylist: `HERMES_WRITE_SAFE_ROOT` was unset and the turn ran in the disposable gateway. The model wrote only inside the run directory. | Medium (disposable profile) | Runbook §8: set `HERMES_WRITE_SAFE_ROOT` in the gateway's environment for any rerun. Verified by local probe that the variable blocks out-of-root writes. |
| S2 | `skill_manage` (Skill create/edit) was available to the E2E model through the `skills` toolset. | Low–Medium | Not called; the post-run drift check was clean. Disclosed. |
| S3 | OpenClaw `run_foreign_code` executes foreign JS unsandboxed. | High when used | Off by default; separate explicit consent; disclosed in the tool schema and README. Not used in P6. |
| S4 | The disposable `HERMES_HOME` is not an OS sandbox. | Informational | Documented. Use a throwaway OS user or VM for untrusted sources. |
| S5 | Hermes control files such as `config.yaml` are writable by the agent's file tools. | Informational (a Hermes design choice) | The post-run drift check covers `config.yaml`. |
| S6 | `hermes plugins validate` on UVP reports `dangerous` for detection regexes and descriptive strings that contain inline-shell text. They cannot execute: they are Python string literals. | Resolved (`3bd461d`) | Regexes now use `[!]` and strings say "bang-backtick"; detection behavior unchanged (equivalence test). The scanner was not modified or bypassed. Pre-fix FAIL output is kept. |
| S7 | Semantic equivalence of ported Skills is not established. | Correctness, not security | Reported as `SKILLS_ONLY_PARTIAL` and `NOT_ESTABLISHED`. |
| S8 | P6.9 Safebox is tool-dispatch policy inside Hermes; slash invocation and `-s` preload bypass it. | Informational | Classified POLICY_ONLY / NOT_ISOLATED; not registered in this release. |
| S9 | P6.10 isolation runner needs root in a disposable WSL distro; WSL2 shares a kernel VM with the host. | Informational | Used only for UVP-owned harmless workloads; never point it at a non-disposable distro. |
| S10 | Host finding (Hermes v0.22.7): `ctx.llm` drops a plugin's `max_tokens` on the native `anthropic` provider (`agent/auxiliary_client._forwards_max_tokens`), so the Anthropic adapter sends the model's 128,000-token output ceiling. A plugin cannot bound its own output cost through `ctx.llm` on that route. | Medium (cost control) | Found by the P6.13 spending firewall in a mock run, at $0. The P6.13 experiment used a single non-retrying request with `max_tokens=600` instead. To be reported to Hermes maintainers; not patched here. |

## Not claimed

UVP does not claim any of the following:

- connector or OAuth compatibility;
- automatic full ecosystem migration;
- protection against malicious local processes;
- runtime parity with the source host.

## Reporting

Report security issues privately through GitHub security advisories on the repository. See `SECURITY.md`.
