# P6.14 clean-home E2E: Inspect → Adapt → Approve → Install → Verify → Demo → Undo

**Result: `CLEAN_HOME_E2E_PASS`.** Two runs, each in a brand-new disposable workspace and Hermes home:
- E2E-001 ran on `2b50a84`. It found one review-file defect, which was fixed in `3172adf`.
- E2E-002 ran on `3172adf` and is the gate run.

Driver: `scripts/p614_clean_home_e2e.py`. Each step is a separate `python uvp_guided.py <step>` process; there was no manual preparation and no manual filesystem operation.

| Item | E2E-002 (gate run) |
|---|---|
| Environment | Windows 11, Python 3.14, Hermes Agent v0.22.7 (`b200f5bc60e3`), new `HERMES_HOME` created by `init` |
| Source pin | `anthropics/knowledge-work-plugins` @ `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3`, `product-management/`; 14 source files hashed in `INSPECT_REPORT.json` |
| Inspect | 8 Skills supported. Unsupported: 16 MCP connectors and 1 command (`brainstorm.md`); no hooks or agents |
| Adapt | Separate candidate. Rules: R-C001 and RES-LOCAL-1. 14 files changed or added (7 SKILL.md rewritten, 7 `CONNECTORS.md` added), each with exact spans. 14 originals identical to the stage. The stage digest is unchanged by adaptation. |
| Candidate digest | `6a57ae419ccef2d2cf0df6da797307ebc86ae18950b30050e87ded48c0ae8b1a` (35 files) |
| Approval | **SIMULATED_BY_TEST_DRIVER**: the driver read the digest from `CANDIDATE_REVIEW.json` and passed `--candidate-digest`. This was not a live operator decision. |
| Installed digest | `6a57ae41…8b1a`, equal to the approved digest (`INSTALL_RECEIPT.json`, 35 files listed) |
| Runtime discovery | 8 of 8 Skills registered as `ported-product-management:*` |
| Invocation (3 pilot Skills) | The documented usage line, e.g. `/ported-product-management:write-spec <feature or problem statement>`, resolves through Hermes's `resolve_skill_command_key`. `build_skill_invocation_message` delivers the probe argument. |
| Resource | `skill_view(..., file_path="CONNECTORS.md")` succeeds, and the file states the connectors are **NOT connected** |
| Demo | **Prepared only.** It printed a three-Skill prompt and the command to run it; no model was called. |
| Undo | See below |
| Model calls | 0 |
| Wall time | 228 s total (`init` 105 s, `install` 93 s) |

The candidate digest differs between runs (`02679eb2…` in E2E-001) because `ADAPTATION_MANIFEST.json` records the workspace's own stage path.

## Before / after (same Hermes v0.22.7)

**BEFORE** comes from a separate fresh home with the **verbatim** stage installed (`docs/evidence/p6-14/before-verbatim-fresh-home-001.json`, `scripts/p6_before_after.py`). For all 3 pilot Skills:
- The documented token (`/write-spec`, …) does not resolve, and no argument is delivered.
- The `../../CONNECTORS.md` link fails with `Path traversal ('..') is not allowed.`

**AFTER** is the candidate UVP actually installed in E2E-002: all of the above pass, as shown in the table.

- Source preservation: `original/` is byte-identical to the stage and matches `SOURCE_HASHES.json`. Install refuses any mismatch.
- Connector status: the 16 connectors stay inactive and are listed in `CANDIDATE_REVIEW.md`.

Both failures were reproduced in a new home, not copied from earlier evidence.

## Rollback residual diff (R4 closure)

Before `install`, UVP records an inventory of every path in the home: type, size, mtime, a SHA-256 for every regular file outside `installs/`, and link targets. That came to 27,410 entries; the file's SHA-256 is in `PREINSTALL_INVENTORY.sha256.json`. After `undo`, the exact diff is classified (`UNDO_RECEIPT.json`):

| Class | Count | Paths |
|---|---|---|
| UVP_CREATED_AND_REMOVED | 35 | every installed plugin file |
| EXISTING_DATA_PRESERVED | 27,409 | unchanged entries |
| EXPECTED_AUDIT_BACKUP | 3 | `.uvp-backups/…/config.yaml` (UVP's pre-install backup) |
| HERMES_CREATED_BACKUP | 1 | `backups/config/config.yaml.good.<timestamp>`, a Hermes "last known good" config copy (`hermes_cli/config_backups.py`), written during the CLI runs that changed `config.yaml` |
| HERMES_RUNTIME_STATE | 4 | `logs/update_receipts/latest.json` and `pm_…-sync-….json`, written by Hermes's package-manager sync on CLI runs; `skills/.usage.json` and its `.lock` (see below) |
| UNEXPECTED_RESIDUAL | 0 | |
| UNATTRIBUTED | 0 | |

`config.yaml` is byte-identical to the pre-install state.

`skills/.usage.json` is Hermes's skill-usage ledger. Hermes writes it when a Skill is used, and `verify` used the three pilot Skills, so it now keeps usage rows for Skills that no longer exist. UVP does not remove it, because the same file holds the user's skill locks (`tools/skill_lock.py`). In E2E-001 this file was still `UNATTRIBUTED`; it was attributed after inspecting its content and Hermes's source.

**The home is not byte-identical after undo** (`full_home_byte_identical: false`). Undo restores what UVP's installation contract covers: the plugin directory and `config.yaml`.

## Measurements (E2E-002)

| Metric | Value |
|---|---|
| Commands | 11 (10 steps + `status`) |
| Human decisions | 5: workspace, fetch approval, SKILLS_ONLY_PARTIAL acceptance, candidate digest, install approval |
| Automatic operations | 26, as counted by `status` |
| Setup | `init` 105 s (Hermes first-run bootstrap) |
| Model calls | 0 |
| Manual filesystem operations | 0 |

Historical note: the P6 run-001 three-Skill **model** execution was run before this flow existed. It is not a run of this guided installation.
