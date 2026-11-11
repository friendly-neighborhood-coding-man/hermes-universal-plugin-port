# Research Synthesis: Onboarding Friction (P6 fictional fixture)

Skill applied: ported-product-management:synthesize-research
Sole evidence source: inputs/p6-onboarding-interviews.md (8 fictional interview notes, I01-I08)

> FIXTURE NOTICE: All source notes are synthetic test data, not real customer
> evidence. Counts below are "n of 8 fictional notes" and must not be read as
> statistics about real users. No analytics, surveys, tickets or other
> sources were used.

---

## 1. Research Overview

- Methodology: Qualitative review of 8 short interview notes (one quote + one
  "observed from note" line each). Thematic analysis + affinity grouping.
  No methodological triangulation is possible (single method, single source file).
- Research question: Where do new and returning users experience friction or
  uncertainty during onboarding (account creation, workspace, invitations,
  first project, checklist)?
- Decisions informed: Scope of a minimal onboarding PRD and a staged roadmap.
- Timeframe: Not stated in the fixture (dates are fictional/unspecified).

Participants (context only, as stated in the fixture):

| ID  | Segment / context                          |
|-----|--------------------------------------------|
| I01 | New individual user, 10-minute onboarding  |
| I02 | Team administrator, creating workspace     |
| I03 | New invited teammate, first login          |
| I04 | Researcher, first project setup            |
| I05 | Returning user after three days            |
| I06 | Mobile user on a slow connection           |
| I07 | Team administrator, invitation management  |
| I08 | New user who completed onboarding          |

---

## 2. PART A — OBSERVATIONS (what the notes say; no interpretation of fixes)

### 2.1 Per-interview extraction

I01
- Said: "I created an account but didn't understand the workspace selector. I left the tab and came back only after a teammate sent the link again."
- Behavior: Abandoned the tab; returned only via an external prompt (teammate re-sent link).
- Pain point: Workspace selector not understood.
- Workaround: Relied on a teammate.

I02
- Said: "I didn't know whether inviting coworkers would send emails immediately, so I skipped it. The invitation preview would have helped."
- Behavior: Skipped the invite step.
- Pain point: Uncertain about the side effect (immediate email send) of inviting.
- Stated preference (not behavior): an invitation preview.

I03
- Said: "The email link opened an empty page. I had to search for a sign-in button and wasn't sure the invitation had been accepted."
- Behavior: Searched for a sign-in button.
- Pain point: Invite link landed on an empty page; invitation acceptance state unknown.

I04
- Said: "I clicked Create Project twice because the screen didn't indicate anything was happening. Later I found two projects."
- Behavior: Double-submitted; produced a duplicate project.
- Pain point: No progress indication after clicking Create Project.

I05
- Said: "I wasn't sure if I'd finished the onboarding checklist, or what the next required step was. I had to ask support."
- Behavior: Contacted support.
- Pain point: Checklist completion state and next required step unclear after returning (3-day gap).

I06
- Said: "The account form submitted but kept spinning. I retried and got a message that my email already existed."
- Behavior: Retried submission; received "email already exists" error.
- Context: Mobile, slow connection.
- Pain point: Form state unclear during slow submission; retry produced a confusing error.

I07
- Said: "After I sent invitations, I couldn't tell who had received them or which ones were still pending. I sent one twice."
- Behavior: Sent a duplicate invitation.
- Pain point: No visibility into invitation delivery / pending status.

I08
- Said: "The short checklist helped, but I didn't know what 'Ready' meant. I wanted to see one example project before entering my own data."
- Positive signal: The short checklist helped (only explicit positive signal in the set).
- Pain point: Meaning of the "Ready" status label unclear.
- Stated preference (not behavior): see one example project before entering own data.

### 2.2 Themes (observations grouped; frequency = number of the 8 notes)

Ordered by frequency x impact (impact judged from the consequence described in the note).

#### Finding F1 — Invitation lifecycle is opaque to both senders and recipients
- Statement: Admins cannot predict or see what invitations do, and invitees cannot tell whether an invitation was accepted.
- Evidence: I02 (unsure whether invite sends email immediately -> skipped inviting), I03 (invite link -> empty page; unsure invite accepted), I07 (couldn't tell who received / which pending; sent one twice).
- Frequency: 3 of 8 (I02, I03, I07); covers both sides of the flow (2 admins, 1 invitee).
- Impact: High — observed outcomes are a skipped invite step (I02), a stalled first login (I03) and a duplicate invite (I07).
- Confidence: Medium (consistent across 3 notes and both roles, but fictional single-source data).

#### Finding F2 — Actions give no in-progress feedback, and users repeat them, creating duplicates or errors
- Statement: When a submit action shows no clear progress or result, users retry, which produced duplicate objects or confusing errors.
- Evidence: I04 (no indication after Create Project -> clicked twice -> two projects), I06 (form kept spinning on slow mobile -> retried -> "email already existed"), I07 (sent one invitation twice — status gap rather than spinner, but same repeat-action outcome).
- Frequency: 2 of 8 direct (I04, I06); 3 of 8 if the I07 repeat action is included.
- Impact: High — produces real side effects (duplicate project, duplicate invite, error message on account creation).
- Confidence: Medium.

#### Finding F3 — Onboarding progress and status meaning are unclear
- Statement: Users cannot tell where they are in onboarding, what is next, or what a status label means.
- Evidence: I05 (unsure checklist finished / next required step after 3 days -> asked support), I08 ("didn't know what 'Ready' meant"), I03 (unsure whether invitation accepted — a status ambiguity, also in F1).
- Frequency: 2 of 8 direct (I05, I08); 3 of 8 including I03.
- Impact: Medium-High — I05 needed support to proceed; I08 completed onboarding despite the confusion.
- Confidence: Medium.

#### Finding F4 — Entry points and orientation (workspace selection, landing pages) are confusing
- Statement: At the first screens, users did not understand where they were or how to continue.
- Evidence: I01 (didn't understand workspace selector; left the tab), I03 (invite link opened an empty page; had to search for sign-in).
- Frequency: 2 of 8 (I01, I03).
- Impact: High per occurrence — I01 abandoned until a teammate re-sent the link.
- Confidence: Low-Medium (2 notes, different screens).

#### Finding F5 — Users fall back on people (teammate, support) to get unstuck
- Statement: When onboarding state was unclear, users relied on outside human help.
- Evidence: I01 (teammate re-sent the link), I05 (had to ask support).
- Frequency: 2 of 8.
- Impact: Medium — an indirect cost signal (support load / dependence on others); no volume data exists.
- Confidence: Low-Medium. This is a consequence of F3/F4, not a separate root cause.

#### Finding F6 — A short checklist works; contextual examples are a desired extra
- Statement: The one user who completed onboarding found the short checklist helpful but wanted an example project for context.
- Evidence: I08 only.
- Frequency: 1 of 8.
- Impact: Low-Medium (user succeeded anyway).
- Confidence: Low (single note; "example project" is a stated preference, not observed behavior).

### 2.3 Priority matrix (based on 8 fictional notes)

- High frequency + high impact: F1 (invitation lifecycle), F2 (no progress feedback / duplicate actions)
- Lower frequency + high impact: F4 (entry/orientation), F3 (progress/status clarity)
- Low frequency + lower impact: F6 (example project), F5 (help fallback — a symptom)

### 2.4 Segments observed (descriptive only; no size estimates possible)

- Team administrators (I02, I07): need predictability and visibility of invitation side effects and status.
- Invited teammates (I03): need a clear landing and confirmation that they joined.
- New individual / first-project users (I01, I04, I08): need orientation, action feedback, and context.
- Returning users (I05): need persisted progress and a clear next step.
- Constrained-network users (I06): need submit states that stay safe and understandable on slow connections.

### 2.5 Contradictions and surprises
- No direct contradictions between notes.
- Of note: the only explicit positive signal (I08: checklist helped) is about the same checklist that confused I05. This suggests the checklist itself is useful and the gap is in its state persistence and labels, not its existence. (Interpretation; 2 notes.)
- Behavior vs. stated preference: I02's "invitation preview" and I08's "example project" are stated wishes, not observed behavior. Treat them as hypotheses.

---

## 3. PART B — RECOMMENDATIONS (proposals; not findings)

> Everything in this section is a proposal by the analyst. None of it was
> observed in the interviews, and none of it has been tested.

Ordered by proposed priority (impact x feasibility, judged qualitatively).

R1 (from F2) — Make submit actions safe to repeat and show progress
- Disable the control and show an in-progress state immediately after Create Project, account-form submit and Send Invitations.
- Make these submissions idempotent so a retry does not create a duplicate project or account, or show a contradictory "email already exists" error to the same user mid-signup.
- Proposed: smallest change, addresses 3 notes (I04, I06, I07).

R2 (from F1) — Invitation status list and send-confirmation
- Before sending: state clearly that sending will email each invitee now (a confirmation summary or preview) (I02).
- After sending: show a per-invitee status list (e.g., Pending / Accepted); prevent or warn on re-inviting someone with a pending invite (I07).

R3 (from F1, F4) — Invite landing page with a clear accept / sign-in path
- The invite link should open a non-empty page that names the workspace, offers sign-in/sign-up, and confirms "You've joined <workspace>" after acceptance (I03).

R4 (from F3) — Persistent checklist with a "next step" and plain-language statuses
- Persist checklist completion across sessions and show "Next required step" on return (I05).
- Replace or explain ambiguous labels such as "Ready" (I08).

R5 (from F4) — Workspace selector clarity
- Add an explanation/default for the workspace selector on first sign-in (I01). Further investigation recommended first (one note; root cause unclear).

R6 (from F6) — Optional example project (investigate, don't build yet)
- Single stated preference (I08); validate before building.

---

## 4. Open Questions (not answerable from this evidence)

- How often each issue occurs in real usage — no analytics or volume data exists in the fixture.
- Whether "email already existed" (I06) means a duplicate account was actually created or the first request succeeded silently — unknown.
- What specifically about the workspace selector confused I01 (labels, number of workspaces, default)?
- Whether invite emails were actually delivered in I07 or only unconfirmed in the UI.
- Whether the I05 checklist state was actually lost or just not shown.

Suggested follow-up methods (proposals): usability test of the invite flow with admins and invitees; funnel instrumentation of signup -> workspace -> invite -> first project to establish baselines; slow-network test of form submits.
