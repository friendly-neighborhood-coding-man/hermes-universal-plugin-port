# Onboarding Roadmap (Now / Next / Later) — PROPOSAL

> EDITORIAL REVIEW CANDIDATE (P6.7). This is NOT the executed run-001 artifact. Items whose open questions are marked blocking were moved from Now to Next. Original SHA-256 a7892715e129a0e94b41ddace9a799309de5f7f7347e9cc8dfc20dce7c858eb8.

Skill applied: ported-product-management:roadmap-update (operation: Create new roadmap)
Input: onboarding-prd.md (which traces to research-synthesis.md -> fictional fixture I01-I08)

> NOTICE: Every placement, priority and sequence below is a RECOMMENDATION,
> not a fact from the interviews. There is no existing roadmap, project
> tracker, team capacity data or date commitment in the evidence. Owners and
> dates are TBD and must be assigned by the team. Fixture data is fictional.

---

## 1. Status Overview

- Items: 9 proposed (0 in progress, 0 completed, 0 at risk). All are Not Started.
- Format: Now (current sprint/month) / Next (1-3 months) / Later (3-6+ months), proposed horizons.
- Prioritization method: MoSCoW from the PRD (P0/P1/P2) + qualitative value-vs-effort. RICE was not used because no reach data exists (using it would require inventing numbers).

## 2. Proposed Priorities (explicit)

| Rank | Item                                        | PRD ref       | MoSCoW (proposed) | Value / Effort (judgment) | Evidence         |
|------|---------------------------------------------|---------------|-------------------|---------------------------|------------------|
| 1    | A. Baseline instrumentation                 | Sec. 8, OQ-5  | Must              | Enabler / Low             | (enables G1-G4)  |
| 2    | B. Submit progress state                    | REQ-1         | Must              | High / Low (quick win)    | I04, I06         |
| 3    | C. Idempotent submission                    | REQ-2         | Must              | High / Medium             | I04, I06, I07    |
| 4    | D. Invitation status model (backend)        | REQ-4 dep.    | Must              | Enabler / Medium          | I03, I07         |
| 5    | E. Invite send confirmation                 | REQ-3         | Must              | High / Low                | I02              |
| 6    | F. Invitation status list + re-invite guard | REQ-4         | Must              | High / Medium             | I07              |
| 7    | G. Invite landing + join confirmation       | REQ-5         | Must              | High / Medium             | I03              |
| 8    | H. Persistent checklist + status labels     | REQ-6, REQ-7  | Should            | Medium / Medium           | I05, I08         |
| 9    | I. Discovery: workspace selector & example project | P2, OQ-6 | Could (research only) | Unknown / Low      | I01, I08         |

Rationale for order (recommendation): fix "did my action work?" first because it is the smallest change and stops new duplicate data (F2); then make the invitation lifecycle visible end to end (F1, the highest-frequency theme, 3 of 8 notes); then progress persistence (F3); leave single-note items (I01, I08 example project) for research before committing.

## 3. Roadmap Items

### NOW (proposed: current sprint / month) — committed if approved

| Item | Description | Status | Target | Owner | Key dependencies |
|------|-------------|--------|--------|-------|------------------|
| A. Baseline instrumentation | Add submit_started/succeeded/failed, invite_sent/accepted, idempotent_replay_detected events so goals have baselines | Not Started | Now | TBD (Eng + Data) | None. Should ship first so pre/post comparison is possible |
| B. Submit progress state (REQ-1) | Disable + in-progress indicator + timeout message on account form, Create Project, Send Invitations | Not Started | Next (blocked: OQ-2 must be answered before this is committed) | TBD (Frontend + Design) | OQ-2 timeout threshold (blocking) |
| C. Idempotent submission (REQ-2) | Retried submits don't create duplicate projects/accounts/invites; signup retry continues instead of "email already exists" | Not Started | Next (blocked: OQ-3 must be answered before this is committed) | TBD (Backend) | OQ-3 idempotency strategy (blocking); must preserve existing-account check (AT-2.3) |

### NEXT (proposed: 1-3 months) — planned

| Item | Description | Status | Target | Owner | Key dependencies |
|------|-------------|--------|--------|-------|------------------|
| D. Invitation status model | Backend Pending/Accepted state per invite, plus an invite_accepted event | Not Started | Next (start early) | TBD (Backend) | OQ-1 (delivery status available?) determines whether status is extensible beyond Pending/Accepted |
| E. Invite send confirmation (REQ-3) | Pre-send summary: "N people will be emailed now" with Cancel | Not Started | Next | TBD (Frontend + Design) | OQ-4 copy; independent of D, so it can ship in parallel |
| F. Invitation status list + re-invite guard (REQ-4) | Admin view of Pending/Accepted; warn + Resend instead of duplicate | Not Started | Next | TBD (Full-stack) | D (hard), C (duplicate guard reuses idempotency approach) |
| G. Invite landing + join confirmation (REQ-5) | Non-empty landing with workspace name, sign-in/up, "You've joined" message, expired-link state | Not Started | Next | TBD (Full-stack) | D (sets Accepted); auth/sign-in flow owners |

### LATER (proposed: 3-6+ months) — directional

| Item | Description | Status | Target | Owner | Key dependencies |
|------|-------------|--------|--------|-------|------------------|
| H. Persistent checklist + labels (REQ-6/7) | Server-side checklist state, "Next" step on return, defined status labels like "Ready" | Not Started | Later (could pull into Next if capacity allows) | TBD | Server-side persistence of checklist state; Design copy (OQ-4) |
| I. Discovery: workspace selector + example project | Usability study / instrumentation to validate I01 and I08 before scoping | Not Started | Later (research can start anytime) | TBD (Research) | A (instrumentation) for supporting data |

Won't have (this period): delivery/bounce invite status (unless OQ-1 says the data already exists), SSO/identity provider changes, full onboarding redesign, analytics dashboards (PRD NG3-NG5).

## 4. Dependency Map (sequence)

    A (instrumentation) ──► baselines for all goals; feeds I
    B (progress state) ──► independent; ship first (quick win)
    C (idempotency) ──────► F (re-invite guard reuses approach)
    D (invite status model) ─┬─► F (status list)
                             └─► G (Accepted on join)
    E (send confirmation) ──► independent of D; parallel
    H (checklist persistence) ──► server-side checklist state (new)
    I (discovery) ──► may produce future PRD items (P2)

Critical path (proposal): D -> F and D -> G. Recommend starting D during NOW, alongside B and C, if capacity allows, so Next isn't blocked.

Dependency types:
- Technical: D before F and G; C's approach reused by F.
- Knowledge: OQ-2 and OQ-3 block B and C; OQ-1 shapes D; OQ-6 gates I-derived work.
- Team: Backend (C, D), Frontend/Design (B, E, copy), Data (A), Research (I). Owners TBD.
- External: none required in v1 (email provider changes are a non-goal).

## 5. Risks

- R-1 Idempotency for signup (C) is the hardest item technically; weakening the existing-account check would be a security regression. Mitigation: AT-2.3 negative test; security review. Contingency: ship B first, which reduces retries even without C.
- R-2 D is on the critical path for two Next items. Mitigation: start D in Now. Contingency: ship E (independent) first.
- R-3 Evidence is 8 fictional notes; priorities may change once real baselines (A) exist. Mitigation: re-rank at the first roadmap review after baseline data is in.
- R-4 Capacity is unknown. If Now is over capacity, move C's account-signup part into Next and keep Create Project idempotency in Now (proposal).

## 6. Changes This Update

- New roadmap. Nothing removed or reprioritized versus a prior version, because there is no prior roadmap.
- Added: items A-I as listed. All are proposals awaiting owner assignment and approval.
