# User-Visible Delivery Standard

## Purpose

Ramin-OS is one operator product, not a collection of invisible scripts,
unrelated dashboards, ports, and chat-only deliverables. Every capability must
have a clear place in the unified user experience so the operator can see what
exists, run it, inspect the real result, test it, and give feedback.

This standard applies to every Codex, Claude Code, Gemini, OpenCode, Council,
autonomous-agent, and human-assisted construction session in this workspace.

## The Core Rule

> Nothing is complete merely because the backend, agent, workflow, API, or
> artifact works. It is complete when its governed capability is discoverable
> from the Ramin-OS front door, usable through an intentional operator journey,
> and demonstrated with a real visible result.

The default delivery unit is a vertical product slice:

`operator need -> UX placement -> implementation -> governance -> visible result -> user-side validation -> handoff`

Design and frontend work begin with the implementation; they are not postponed
until after the engine is declared finished.

## One Front Door, Many Purposeful Workspaces

- The Ramin-OS Hub is the canonical front door.
- Put a capability inside the domain workspace that owns the job: Ads, CX,
  Media, Creative, Audio, Video, Price, Influencer, Certification, Gateway, or
  another registered module.
- Add or update the relevant Hub card/navigation and `services.json` entry or
  capability metadata so a user can find it without remembering a command,
  folder, or port.
- Reuse the owning module's shell, navigation, components, language, and visual
  tokens. A specialized workspace may have its own route or service, but it
  must still feel and behave like part of Ramin-OS and remain reachable from the
  Hub.
- Do not ship duplicate home pages, orphan dashboards, temporary control panels,
  or standalone mini-products when an existing Ramin-OS surface can own the
  experience.

## Parallel Product Team

For material feature work, plan these lanes together:

| Lane | Responsibility |
| --- | --- |
| Product/operator | Defines the real job, entry point, success state, and handoff |
| UX/UI | Maps the flow and designs discoverable, consistent interface states |
| Backend/integration | Builds the governed capability and real data/output path |
| Security/governance | Applies permissions, checkpoints, privacy, and fail-closed behavior |
| QA/review | Tests the full journey and compares visible output with system truth |

When agent delegation is available, the lead agent should assign the UX/UI lane
in parallel with the engine work and retain responsibility for integration and
final acceptance. Parallel work must converge on one product; it must not create
five disconnected artifacts.

## Minimum Operator Journey

Every recurring capability should answer these questions on screen:

1. What is this and when should I use it?
2. What real input or source does it need?
3. What is happening now?
4. What succeeded, failed, or still needs attention?
5. Where is the actual result, report, media, decision, or artifact?
6. What evidence/source/status makes the result trustworthy?
7. What can I safely do next?

The interface must include the states relevant to its workflow: initial/empty,
loading or queued, progress, partial data, success, error, approval required,
and safe retry. Invalid actions should be disabled or clearly explained rather
than discovered through backend errors.

## Truthful UI

- Show the real artifact in the interface whenever possible: render the report,
  preview the image/video/audio, display the decision, or expose the actionable
  record. A filename, raw JSON response, console log, or success toast alone is
  not a result view.
- Never fill missing production data with demo values in a handoff. Mark the gap
  plainly and provide a real upload, manual-entry, or approved connection path.
- Separate source-backed values from calculated values and unavailable values.
- Keep outward actions such as publishing, sending, spending, deleting,
  credentialed browsing, and production writes behind the required human
  checkpoint. UX convenience never weakens security.

## Visual and Interaction Quality

The owning team must review the rendered experience, not just the source code.
At minimum verify:

- consistent navigation, hierarchy, spacing, typography, color, and controls;
- clear Azerbaijani operator language where appropriate;
- readable desktop layout and reasonable smaller-screen behavior;
- keyboard/focus behavior, labels, contrast, and meaningful status messages;
- useful empty, loading, partial, error, approval, and success states;
- no clipped content, broken assets, placeholder copy, unexplained jargon, or
  dead controls.

For visually important deliverables, use the established creative workflow:

`market/audience audit -> idea-studio -> KILL -> Atelier/Brand Brain -> Figma or DESIGN.md-first -> responsive implementation -> visual critique -> export`

## Definition of Done

A construction session may say **complete** only when all applicable items are
true:

- [ ] The capability belongs to an identified operator journey and owning module.
- [ ] The UX/UI was designed as part of the work, not left as an unspecified future task.
- [ ] The capability is discoverable from the Hub or the owning Hub workspace.
- [ ] `services.json` and self-description/docs are updated when system shape changed.
- [ ] The UI accepts real input or clearly exposes the approved connection/input path.
- [ ] Status, progress, errors, approvals, result preview, and next action are understandable.
- [ ] Security and permission controls cover the UI actions as well as the backend.
- [ ] The relevant automated checks pass.
- [ ] The full operator journey was exercised through the interface with representative input.
- [ ] The visible result was compared with the underlying system output.
- [ ] Responsive and visual review was performed for user-facing changes.
- [ ] The operator received the exact Hub path or verified URL, usage instructions,
      visible proof/preview, test scope, and honest remaining limitations.

If an applicable box is open, the status is **partial**. Record the missing item
and its blocker or follow-up; do not hide it behind `backend complete`.

## End-of-Session Handoff

Before ending a construction session:

1. Start or safely restart the relevant local surface if doing so will not
   disrupt unrelated work.
2. Open the Hub/module route or finished artifact for the operator when the
   environment supports it.
3. If direct opening is unavailable, provide a verified exact path or URL and a
   current screenshot/preview.
4. State in plain language what the user can now do, how to do it, what was
   tested from the UI, and what remains unavailable or unverified.

The handoff is part of the product. A user should never have to search source
folders, remember port numbers, infer commands, or ask which studio contains the
thing that was just built.

## Narrow Exceptions

Internal refactors, dependency maintenance, security hardening, and invisible
infrastructure changes do not each require a new page. They do require an
operator-visible effect when relevant, using an existing health, audit,
activity, settings, notification, or owning-module surface.

A backend-only handoff is acceptable only when the user explicitly requests
backend-only scope or when a documented external blocker prevents the UI. The
session must still state that the delivery is partial and identify the exact
front-end integration that remains.
