# P6 synthetic onboarding interviews — test fixture, NOT real customer evidence

Purpose: Provide deterministic, privacy-safe source notes for validating
the **ported** `synthesize-research` → `write-spec` →
`roadmap-update` skill chain. Entirely fictional; dates, personas and
statements are invented. No statistics about actual users may be inferred.

**Task constraint:** Use the eight notes as the entire evidence base. Cite
interview IDs in each finding. Avoid making up user counts beyond those
eight interviews. Unmeasured KPI targets must be explicitly labeled
proposals/hypotheses, not observed baselines.

## I01 — New individual user, 10-minute onboarding

"I created an account but didn't understand the workspace selector. I
left the tab and came back only after a teammate sent the link again."

Observed from note: workspace selection unclear; needed outside help.

## I02 — Team administrator, creating workspace

"I didn't know whether inviting coworkers would send emails immediately,
so I skipped it. The invitation preview would have helped."

Observed from note: invitation side-effect uncertainty.

## I03 — New invited teammate, first login

"The email link opened an empty page. I had to search for a sign-in
button and wasn't sure the invitation had been accepted."

Observed from note: invitation and login state ambiguous.

## I04 — Researcher, first project setup

"I clicked Create Project twice because the screen didn't indicate
anything was happening. Later I found two projects."

Observed from note: missing progress and duplicate action risk.

## I05 — Returning user after three days

"I wasn't sure if I'd finished the onboarding checklist, or what the
next required step was. I had to ask support."

Observed from note: progress persistence and status clarity gap.

## I06 — Mobile user on a slow connection

"The account form submitted but kept spinning. I retried and got a
message that my email already existed."

Observed from note: unclear form state on slow network.

## I07 — Team administrator, invitation management

"After I sent invitations, I couldn't tell who had received them or
which ones were still pending. I sent one twice."

Observed from note: invite delivery/status visibility gap.

## I08 — New user who completed onboarding

"The short checklist helped, but I didn't know what 'Ready' meant.
I wanted to see one example project before entering my own data."

Observed from note: successful checklist but missing contextual guidance.

## Expected evidence-based synthesis, not a scripted answer

- One or more themes from invitation and workflow-status uncertainty
  should be traceable to source IDs.
- Identify observations versus proposed fixes explicitly.
- Proposed PRD should prioritize a minimal viable improvement and
  include user stories, acceptance tests, and non-goals.
- Proposed roadmap should list dependency order, Now/Next/Later
  commitments as **recommendations**, not facts from the interviews.
- No reliance on Slack, Linear, Notion, analytics, external identity
  providers or other unconnected source plugin MCPs.

## Output evidence requested from the live Hermes run

- `research-synthesis.md`: themes and direct evidence-ID grounding
- `onboarding-prd.md`: proposal, user stories, testable criteria
- `onboarding-roadmap.md`: dependency-aware staged plan
- `RUN_RECEIPT.json`: exact imported Skill IDs, call order, approvals,
  source plugin sha and all three output hashes
