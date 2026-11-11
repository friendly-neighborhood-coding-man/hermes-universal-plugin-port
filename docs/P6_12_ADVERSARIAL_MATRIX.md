# P6.12 Safebox adversarial matrix

**Run:** real Hermes dispatch (`model_tools.handle_function_call`, Hermes v0.22.7 @ `b200f5b`) in a NEW disposable home `uvp-p612-hermes-test`. The TEST-ONLY harness plugin `uvp-safebox-harness` registers Safebox + continuity as real `pre_tool_call`/`post_tool_call` hooks. Harmless fixtures only. **0 model calls.**

**Totals:** BYPASS_CONFIRMED 3, DENIED 14, ENFORCED 3, NOT_INTERCEPTED 2, NOT_TESTED 1.

**Conclusion: Safebox is NOT universally enforced.** Slash invocation (A16), `-s` preload (A17) and a validate-then-swap race (A15) are confirmed bypasses. Sessions without an active imported Skill (A20) and host-side actions (A23) are outside its scope. The classification stays **POLICY_ONLY / NOT_ISOLATED**.

| ATTACK_ID | ENTRY_PATH | EXPECTED | OBSERVED | ENFORCED_BY | EVIDENCE | VERDICT |
|---|---|---|---|---|---|---|
| A01 | skill_view imported Skill, no grant | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): skill_view denied for imported Skill ported-product-management:synt | DENIED |
| A02 | skill_view imported Skill, valid grant | allow + activate | allowed | Safebox pre_tool_call | success=True | ENFORCED |
| A03 | write_file inside fs.write | allow | allowed, file exists=True | Safebox pre_tool_call | {'bytes_written': 2, 'dirs_created': True, 'verified': True, 'lint': {'status': 'skipped', 'message': 'No linter for .tx | ENFORCED |
| A04 | write_file outside root | deny | blocked, file exists=False | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): write_file denied for imported Skill ported-product-management:writ | DENIED |
| A05 | write_file ../ traversal | deny | blocked, file exists=False | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): write_file denied for imported Skill ported-product-management:writ | DENIED |
| A06 | write_file relative path | deny | blocked, file exists=False | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): write_file denied for imported Skill ported-product-management:writ | DENIED |
| A07 | terminal tool (echo) | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): terminal denied for imported Skill ported-product-management:write- | DENIED |
| A08 | unknown tool name | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): uvp_fake_tool denied for imported Skill ported-product-management:w | DENIED |
| A09 | patch outside root | deny | blocked, file exists=False | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): patch denied for imported Skill ported-product-management:write-spe | DENIED |
| A10 | write_file path as list | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): write_file denied for imported Skill ported-product-management:writ | DENIED |
| A11 | read_file outside root | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): read_file denied for imported Skill ported-product-management:write | DENIED |
| A12 | skill_manage (Skill admin) | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): skill_manage denied for imported Skill ported-product-management:wr | DENIED |
| A13 | other plugin tool port_stage | deny | blocked | Safebox pre_tool_call | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): port_stage denied for imported Skill ported-product-management:writ | DENIED |
| A14 | write_file via junction work/jlink -> outside | deny | blocked | Safebox realpath check | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): write_file denied for imported Skill ported-product-management:writ | DENIED |
| A15 | validate-then-swap (junction) between hook and write | deny | hook allowed (True); file landed outside=True | none (check-then-use) | outside/a15.txt exists=True | BYPASS_CONFIRMED |
| A16 | slash /ported-product-management:write-spec (no grant configured) | deny | Skill text delivered (13179 chars) | not intercepted | build_skill_invocation_message returned content | BYPASS_CONFIRMED |
| A17 | hermes -s ported-product-management:write-spec preload (no grant) | deny | loaded=['ported-product-management:write-spec'] | not intercepted | build_preloaded_skills_prompt | BYPASS_CONFIRMED |
| A18 | stale grant (source SHA mismatch) | deny activation | blocked | harness fail-closed | {'error': 'UVP Safebox grant invalid: PortError: Grant is not bound to the current contract for ported-product-managemen | DENIED |
| A19 | two active Skills, one without write scope | deny | blocked | Safebox (any active grant denies) | {'error': 'UVP Safebox (POLICY_ONLY / NOT_ISOLATED): write_file denied for imported Skill ported-product-management:synt | DENIED |
| A20 | new session without imported Skill writes outside | not applicable (Safebox scoped to sessions with an active imported Skill) | allowed | none | outside/a20.txt exists=True | NOT_INTERCEPTED |
| A21 | delegate_task with granted delegation | contract attached; child not run | modified=True block=None | continuity pre_tool_call (modify) | context has authenticated block=True | ENFORCED |
| A22 | child session tool calls after delegation | Safebox applies in child | not run (needs a model-driven child) | unknown | no live delegate_task executed | NOT_TESTED |
| A23 | host-side actions (cron, gateway jobs, other plugins' own hooks, the user) | outside UVP | static review | none | Hermes dispatch only routes tool calls through pre_tool_call | NOT_INTERCEPTED |

## What the bypasses mean

- **A16 / A17:** Hermes delivers Skill text through `agent.skill_commands` without a tool call, so no `pre_tool_call` fires. Only a hook on Skill loading itself could close these routes. That hook does not exist on the current public Hermes surface.
- **A15:** the hook validates a path string, and the tool resolves it again later. A junction swapped in between redirects the write. Closing this needs handle-based (`O_NOFOLLOW`/openat-style) enforcement inside the write tool, or OS isolation (P6.10).
- **A20 / A22:** Safebox applies only to sessions in which an imported Skill was activated through `skill_view`. A delegated child is a new session and was not exercised live.
- **Fail-closed behavior:** Hermes catches `pre_tool_call` exceptions and proceeds (fail-open). UVP's callbacks catch their own errors and return a block. A18 shows an invalid grant blocking activation.

Evidence: `docs/evidence/p6-12/adversarial-matrix-001.json`, `safebox-audit-001.jsonl` (13 denial records). Driver: `scripts/p612_adversarial.py`.
