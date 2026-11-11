# UVP v0.5 — deterministic routing core (experimental)

## Current delivered slice

`uvp_routing.py` implements a **pure, read-only routing recommendation**.
The routing *core* does not execute tools, import or install plugins, infer
executable compatibility, grant permissions or call an LLM. Starting with the
P2 preview, the plugin also registers `/uvp` and the `uvp_route` tool as
**advisory-only** entrances. Existing v0.4.3 porting functionality remains.

1. **Domain identification:** bounded keyword candidate filter for research,
   coding, data, browser and documents, including Korean terms. It is not a
   semantic classifier. More than two domains requires review.
2. **Domain defaults:** operator-configured preferred and fallback capability IDs.
3. **Registry:** operator-maintained *attestations* referencing runtime evidence.
   An arbitrary imported manifest, README or Capability Passport is **not**
   authorization, and must not be copied into this registry as an approval.
4. **Gap handling:** propose vanilla/native fallback if no approved candidate.
   Two eligible domains produce a proposed composition, **not an execution**.
5. **Permissions:** only read-only, operator-approved and runtime-attested
   capabilities can enter a ready plan; write/network/execute/send requires
   an explicit approval mechanism that is **not yet implemented**.

A `PLAN_READY` status means the *routing metadata* passed its gates. It does
not prove the downstream task will succeed or that source and target semantics
are equivalent. `execution_performed` is always `false`.

## Input examples

- `examples/uvp-routing-policy.json` — sample user preferences, no executable
  plugin bindings.
- `examples/uvp-routing-registry.json` — intentionally **empty**; no capability
  is authorized by default.

Minimal offline usage:

```python
from pathlib import Path
from uvp_routing import load_policy, load_registry, route_request

policy = load_policy(Path("examples/uvp-routing-policy.json"))
registry = load_registry(Path("examples/uvp-routing-registry.json"))
report = route_request("논문을 조사하고 코드를 구현해줘", policy, registry)
print(report["status"], report["domains"], report["execution_performed"])
# PLAN_INCOMPLETE ['research', 'coding'] False
```

From a cloned project folder, if relative package imports interfere, run
the tests with:

```powershell
python -m unittest discover -s tests -p "test_uvp_routing.py" -v
```

## Operator registry requirement

For an approved capability, the operator must record: an ID, domain, kind,
invocation descriptor, explicit approval, verified runtime evidence digest
and precise permissions. The SHA-256 is **a reference to evidence**, not a
signature, runtime proof, or protection against a malicious registry editor.

No untrusted plugin file may edit or enroll itself in the registry.

## Not yet implemented (next slices)

- Enforced AGENTS.md invocation: current AGENTS example is guidance, not a guaranteed trigger.
- Safe host capability discovery and binding live registration to the
  operator registry, including version and source-digest revalidation.
- Natural-language ambiguity handling via bounded model escalation.
- Actual multi-skill orchestration and verified input/output handoff.
- Explicit approvals for write/network/exec/send; no implicit policy bypass.
- Cross-host runtime Witness and permission-safe selective porting.
- Regression E2E against the existing v0.4.3 `/summarize` fixture.

**No background execution or installation is performed.**

## P1: Hermes Skill discovery snapshot audit

`uvp_discovery.parse_skills_list` consumes the official Hermes `skills_list()`
JSON result. It records **only visible Skill names**, discarding source
instructions/descriptions. The caller must obtain the listing from the correct
Hermes profile; an imported or user-edited JSON file is not proof of active
registration. `audit_skill_route` can remove an approved route if the
selected Skill is missing. **It never turns a discovered Skill into an
approved capability.** Non-Skill tools and adapters still require an
independent live binding check.

The standalone CLI can audit a saved (non-sensitive) snapshot:

```powershell
python uvp_route_cli.py --prompt "논문을 조사하고 코드를 구현해줘" --skills-list .\\saved-skills-list.json
```

This is an **offline snapshot check**, not an automatic live scan. Hermes
`skills_list()` itself may trigger the official plugin-discovery lifecycle,
so do not call it against a production profile just to run this preview.

An empty configured capability registry still returns `PLAN_INCOMPLETE`,
regardless of how many Skills the catalog reports.

### Suggested local checks

```powershell
python -m unittest discover -s tests -p "test_uvp_*.py" -v
python -m unittest discover -s tests -v
```

CI and local verification are separate: the new tests require an actual run.

## P2: live Hermes registration, still no execution

The plugin manifest version is now 0.5.0 and declares four tool names:
`port_probe`, `port_fetch`, `port_stage`, and `uvp_route`. The plugin
registers two slash commands: legacy `/universal-port` and new `/uvp`.

`/uvp <task>` returns a route plan from the bundled default policy and the
**empty** bundled registry. It never invokes the selected capability (even
if one is listed). `uvp_route({"prompt": "..."})` returns the same advisory JSON.
The `uvp_route` tool rejects unknown input fields, including attempts to
smuggle `approved=true`. Neither entrypoint contacts a model, discovers
live skills, mutates permissions, or performs porting.

Hermes's normal plugin lifecycle does execute trusted Python registration
code when loading this package. **Install only to a disposable Hermes home.**

1. Run `python -m unittest discover -s tests -v` and `hermes plugins doctor
   <worktree> --ci` against the updated branch.
2. If both pass, copy to `$env:HERMES_HOME\\plugins\\universal-plugin-port`
   excluding `.git`, `__pycache__`, `tests`, and build/cache folders.
3. Run `hermes plugins enable universal-plugin-port`, restart only the test
   profile gateway if needed, then invoke `/uvp 논문을 조사하고 코드를 구현해줘`.
4. Expected: `PLAN_INCOMPLETE`, two domains, zero selected capabilities,
   `execution_performed: false`.

No auto-dispatch, Skill composition, LLM classification or profile-scoped
user-override defaults are implemented yet. The P1 catalog audit remains an
**offline snapshot** check, not a Hermes live listing operation.

## P3 candidate discovery (review-only)

The user-supplied disposable Hermes profile listed 38 enabled builtin Skills
(0 local/hub-installed). Reviewed upstream metadata confirms:

- `arxiv`: research/paper discovery via arXiv and Semantic Scholar APIs;
  requires outbound network access.
- `grounded-citations`: citation-ledger workflow, may write profile files.
- `claude-code`, `codex`: coding delegation via separate CLIs with potential
  shell execution, network access and workspace writes.
- `codebase-inspection`: LOC and language breakdown via `pygount`, **not**
  a generic code implementation capability; depends on `pygount`.

**New opt-in command**: `/uvp --candidates 논문을 조사하고 코드를 구현해줘`.

It queries Hermes's built-in `skills_list` tool once through the plugin
dispatcher, validates and discards untrusted descriptions, and returns a
small reviewed list of *actually visible* candidate names. Any candidate
is marked `DISCOVERED_UNAPPROVED` and `executable: false`. It does NOT call
`skill_view` (which may preprocess and load dependencies), invoke a model,
read SKILL.md bodies, or execute a candidate. The host's `skills_list`
discovery lifecycle may initialize skill indexes/caches; do not characterize
it as a strictly side-effect-free filesystem operation.

The regular `/uvp <task>` and `uvp_route` outputs remain unchanged.
This is a limited Hermes builtin seed vocabulary for a first demo, **not**
general cross-host semantic compatibility. The approval Registry remains
empty; no permissions are granted.

### Further verification

Run `python -m unittest discover -s tests -p "test_uvp_*.py" -v`.
Run Hermes `plugins doctor` against this updated worktree, then test in the
same disposable HERMES_HOME after updating its installed plugin copy.
Observe the live candidate list and verify `execution_performed: false`.
No claim of P3 runtime PASS is made until that observation.
