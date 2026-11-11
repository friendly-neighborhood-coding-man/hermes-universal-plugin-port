# PRD: Onboarding Clarity v1 — Safe Actions & Visible Invitation Status

Skill applied: ported-product-management:write-spec
Input: research-synthesis.md (derived only from fictional fixture I01-I08)
Status: DRAFT PROPOSAL — not approved; all targets are hypotheses.

> FIXTURE NOTICE: Evidence is 8 synthetic interview notes. "n of 8" refers to
> those notes only. No baseline metrics exist; every numeric target below is
> an explicitly labeled PROPOSED HYPOTHESIS, not an observed value.

---

## 1. Problem Statement

During onboarding, users cannot tell whether their actions worked or what state they are in. Submit actions show no progress, so users retry and create duplicates or errors (I04, I06; plus a duplicate invite in I07). Invitations are opaque: admins don't know what sending does or who has accepted (I02, I07), and invitees land on an empty page without confirmation (I03). If we don't fix this, teams don't get invited (I02 skipped it), duplicate data gets created (I04), and users need a teammate or support to continue (I01, I05).

Evidence mapping: F1 (I02, I03, I07), F2 (I04, I06, I07), F3 (I03, I05, I08) from research-synthesis.md.

## 2. Scope (v1)

In scope (minimal viable improvement):
1. In-progress feedback and duplicate-safe submission for three actions: account creation, Create Project, Send Invitations. (R1)
2. Invitation send confirmation + per-invitee status list for admins. (R2)
3. Invite landing page with a clear accept/sign-in path and a joined confirmation. (R3)

Fast follow (P1, same initiative, not required to ship v1):
4. Persistent onboarding checklist with "next required step" and plain-language status labels. (R4)

## 3. Goals (outcomes; targets are PROPOSED HYPOTHESES)

G1. Users do not create duplicate objects through repeat submission.
    Proposed hypothesis target: 0 duplicate projects / accounts / pending invites created by repeat submit in QA and test scenarios; post-launch duplicate rate to be baselined first.
G2. Admins can see the status of every invitation they sent without contacting support.
    Proposed hypothesis: in a moderated usability test, admins can correctly state each invitee's status (Pending/Accepted) for all invitees.
G3. Invited teammates reach their workspace from the invite link without searching for sign-in.
    Proposed hypothesis: in a usability test, invitees reach the workspace and see a joined confirmation with no dead-end page.
G4. (Business, lagging) Fewer onboarding-related support contacts.
    No baseline exists; first step is to instrument and baseline. Any reduction target is TBD after baselining.

## 4. Non-Goals (with rationale)

NG1. Redesign of the workspace selector (I01). Rationale: 1 of 8 notes; root cause unclear. Needs investigation first (roadmap: Later).
NG2. Example/sample project (I08). Rationale: single stated preference, not observed behavior; validate first.
NG3. Changes to email delivery infrastructure or external identity providers / SSO. Rationale: we only need to show the status the system already knows; delivery provider changes are a separate initiative and out of evidence.
NG4. Full onboarding flow redesign or new onboarding steps. Rationale: I08 shows the short checklist works; we are fixing state and feedback, not re-architecting the flow.
NG5. Analytics dashboards. Rationale: v1 adds only the minimum events needed to baseline the goals (see Section 8), not reporting UI.

## 5. User Stories (grouped by persona; priority order)

Team administrator (I02, I07)
- US1. As a team admin, I want to know before sending that invitees will be emailed immediately, so that I can invite coworkers with confidence instead of skipping the step. (I02)
- US2. As a team admin, I want to see each invitation's status (Pending / Accepted) after sending, so that I know who still needs a nudge. (I07)
- US3. As a team admin, I want to be warned when I re-invite someone who already has a pending invite, so that I don't send duplicates by accident. (I07)

Invited teammate (I03)
- US4. As an invited teammate, I want the invite link to open a page that names the workspace and tells me how to sign in or sign up, so that I'm not left on an empty page. (I03)
- US5. As an invited teammate, I want explicit confirmation that I've joined, so that I know the invitation was accepted. (I03)

New user creating account or first project (I04, I06)
- US6. As a new user, I want to see that my submission is in progress, so that I don't click again and create duplicates. (I04, I06)
- US7. As a mobile user on a slow connection, I want a retry of account creation to continue my signup rather than show "email already exists", so that I'm not blocked by my own first attempt. (I06) [edge case: slow network / timeout]
- US8. As a researcher creating my first project, I want a second click on Create Project not to create a second project, so that I don't have to clean up duplicates. (I04) [edge case: double submit]

Returning / completing user (I05, I08) — P1
- US9. As a returning user, I want to see which checklist steps I've completed and the next required step, so that I can continue without asking support. (I05)
- US10. As a new user, I want each checklist status label (e.g., "Ready") to say in plain language what it means, so that I know whether I can proceed. (I08)

## 6. Requirements and Acceptance Tests

Acceptance tests are written to be independently verifiable (manual QA or automated E2E). Each has an ID for traceability.

### P0 — Must-Have

REQ-1 Submission progress state (US6) — Account form, Create Project, Send Invitations
- AT-1.1 Given a user on any of the three forms, When they activate submit, Then within the same UI frame the submit control becomes disabled and shows an in-progress indicator.
- AT-1.2 Given a submit is in progress, When the user clicks/taps submit again, Then no additional request is sent (verify via network log: exactly 1 request).
- AT-1.3 Given a submit succeeds, Then a success state is shown naming the result (e.g., "Project <name> created").
- AT-1.4 Given a submit fails or times out (simulate slow-3G + server timeout), Then the control re-enables and a message states the action did not complete and can be retried. Negative: the spinner never remains indefinitely without a message (timeout threshold to be set by engineering; see OQ-2).

REQ-2 Duplicate-safe (idempotent) submission (US7, US8)
- AT-2.1 Given Create Project is submitted twice with the same idempotency key (simulated double request), Then exactly one project exists afterwards.
- AT-2.2 Given account creation succeeded server-side but the client did not receive the response (simulate dropped response), When the same user retries from the same signup session, Then they proceed to the next onboarding step and do NOT see "email already exists".
- AT-2.3 Negative: Given a different person submits an email that already has an account (separate session), Then the existing "account exists — sign in" path is shown (behavior unchanged; no account takeover).

REQ-3 Invitation send confirmation (US1)
- AT-3.1 Given an admin has entered N invitee emails, When they click Send, Then a confirmation lists the N addresses and states that each will be emailed immediately, with Send and Cancel options.
- AT-3.2 Given the admin clicks Cancel, Then no invitations are created and no emails are queued (verify: 0 invite records, 0 queued emails).

REQ-4 Invitation status list (US2, US3)
- AT-4.1 Given an admin has sent invitations, When they open the members/invitations view, Then each invitee is listed with status Pending or Accepted and the date sent.
- AT-4.2 Given an invitee accepts, When the admin refreshes the view, Then that invitee shows Accepted.
- AT-4.3 Given an invitee has a Pending invite, When the admin tries to invite the same email again, Then a warning states an invite is already pending and offers "Resend"; no second pending record is created (verify: 1 record).
- Note: "Delivered/Bounced" statuses are out of scope unless engineering confirms the data is already available (OQ-1; NG3).

REQ-5 Invite landing and join confirmation (US4, US5)
- AT-5.1 Given a valid invite link, When opened by a signed-out user, Then the page shows the workspace name and Sign in / Create account actions (no empty page).
- AT-5.2 Given the user completes sign-in or sign-up from that page, Then they land in the invited workspace with a visible "You've joined <workspace>" confirmation, and the invite becomes Accepted (cross-check with AT-4.2).
- AT-5.3 Given an expired or already-used invite link, Then the page explains the state and how to proceed (e.g., ask admin to resend / sign in). Negative: never renders blank.

### P1 — Nice-to-Have (fast follow)

REQ-6 Persistent checklist + next step (US9)
- AT-6.1 Given a user completed steps A and B and signed out, When they sign back in (any later session), Then steps A and B show as complete and the first incomplete required step is labeled "Next".
- AT-6.2 Given all required steps are complete, Then the checklist states onboarding is complete.

REQ-7 Plain-language status labels (US10)
- AT-7.1 Every checklist status label has visible helper text or a tooltip defining it (e.g., what "Ready" means and what action, if any, is next). Verify by inspecting each label in the checklist.

### P2 — Future Considerations (design for, do not build)
- Workspace selector clarity (I01) — keep the post-signup routing flexible enough to add a default-workspace or explainer step.
- Optional example project (I08) — keep project creation able to seed a template later.
- Delivery-level invite status (Delivered/Bounced) — keep invite status as an extensible enum.

## 7. Traceability

| Req   | Stories     | Finding | Interviews        |
|-------|-------------|---------|-------------------|
| REQ-1 | US6         | F2      | I04, I06          |
| REQ-2 | US7, US8    | F2      | I04, I06          |
| REQ-3 | US1         | F1      | I02               |
| REQ-4 | US2, US3    | F1, F2  | I07               |
| REQ-5 | US4, US5    | F1, F4  | I03               |
| REQ-6 | US9         | F3, F5  | I05               |
| REQ-7 | US10        | F3, F6  | I08               |

## 8. Success Metrics (ALL targets are PROPOSED HYPOTHESES; no baselines exist)

Leading (days-weeks):
- Duplicate-creation rate from repeat submits (projects, accounts, pending invites). Proposed: baseline for 2 weeks pre-launch via new events; hypothesis = near-zero after launch.
- Invite acceptance completion: % of opened invite links that reach the "joined" confirmation. Proposed: baseline first; no target until measured.
- Submit error/timeout messages shown per form (to confirm AT-1.4 behavior is reachable and not frequent).
Lagging (weeks-months):
- Onboarding-related support contacts. Baseline first; target TBD.
Measurement method: product event instrumentation added in v1 (submit_started/succeeded/failed, invite_sent/accepted, idempotent_replay_detected). Evaluate 4 weeks post-launch (proposal).

## 9. Open Questions

- OQ-1 (Engineering, non-blocking): Does the email system already expose delivery/bounce status? If not, v1 shows Pending/Accepted only.
- OQ-2 (Engineering + Design, blocking for REQ-1): What timeout threshold turns the in-progress state into a retryable failure message?
- OQ-3 (Engineering, blocking for REQ-2): Idempotency key strategy for account creation across a slow/dropped mobile connection without weakening the existing-account check (AT-2.3).
- OQ-4 (Design, non-blocking): Exact copy for the send confirmation and status label definitions.
- OQ-5 (Data, non-blocking): Can baseline instrumentation ship before the UX changes to get pre/post comparison?
- OQ-6 (Research, non-blocking): Validate I01 (workspace selector) and I08 (example project) before they enter scope.

## 10. Timeline Considerations

- No hard deadlines are known from the evidence.
- Dependencies: REQ-2 depends on a backend idempotency mechanism; REQ-4 depends on an invitation status model (Pending/Accepted) on the backend; REQ-5 and REQ-4 share the invite-accepted event; REQ-6 depends on server-side checklist state persistence.
- Suggested phasing (proposal): Phase 1 = instrumentation + REQ-1/REQ-2; Phase 2 = REQ-3/4/5; Phase 3 = REQ-6/7. See onboarding-roadmap.md.
