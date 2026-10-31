# Revona Bot — Experience & Product Specification (Draft v0.1)

## Product promise
A beautiful, approachable AI company that works for you. Users explain their goals in everyday language; Revona's Chief of Staff assembles and coordinates the right people, departments and tools.

## Non-negotiable experience principles
- Love at first sight: elegant typography, generous whitespace, clear hierarchy, restrained motion, accessible contrast and a premium visual identity.
- No coding knowledge required: never expose raw tool traces, stack traces, configuration JSON or internal jargon in the default conversation.
- Speak plainly: tell the user what Revona understood, what it is doing, what it needs, and what is complete.
- Progressive disclosure: advanced controls are available, but not forced on ordinary users.
- Trust: separate proposed actions from completed actions, show evidence and request approval for consequential operations.
- Local-first and privacy-aware: retain OpenMausBot's existing boundaries unless explicitly redesigned and tested.

## First-run journey
1. Welcome: 'What do you do, and what would you like help with?'
2. Learn whether the user is an individual, freelancer, business or multi-business operator. Allow multiple roles.
3. Ask only essential follow-ups, one at a time, in conversational language.
4. Draft a user profile, labeling confirmed details versus suggestions.
5. Recommend an organizational chart and preconfigured departments; allow review and edits.
6. Explain required service connections and permissions individually.
7. Offer a simple starter task and show a verifiable result.

## Default organization
- Chief of Staff: single primary point of contact, routes work and summarizes decisions.
- Executives/directors: Finance, Operations, Technology, Marketing, Administration; provision only relevant departments.
- Project managers: own scope, milestones, delegation and progress.
- Specialists: Mail, Social, Developer, Research, Office, Browser, Scheduler, Finance and others.
- Agent profiles: title, purpose, manager, capabilities, permissions, model, cost limits, work history.
- Agent Architect: create, customize or duplicate an agent through conversation; reuse existing agents where possible.

## Core application layout
- Left navigation: Home, Conversations, Projects, Organization, Agents, Activity.
- Center: Chief of Staff conversation with concise messages and actionable progress cards.
- Right contextual workspace: current task, live preview, files, approvals, and outcomes. Collapsible on smaller screens.
- Organization view: interactive hierarchy with department and employee cards.
- Accessibility: keyboard navigation, screen-reader labels, reduced motion, readable sizes and responsive layout.

## Communication design
Every agent response should be organized around:
1. **Understood:** short summary of the requested outcome.
2. **Working on:** concise human-readable steps, not raw logs.
3. **Needs your decision:** only when genuinely blocked or approval is required.
4. **Result:** artifact, preview, evidence and next action.
Advanced 'Technical details' reveals logs and diagnostics on demand.

## Execution and safety
- Task lifecycle: proposed → approved (if required) → queued → running → reviewing → completed/failed.
- Clearly show who owns each task and who approved sensitive operations.
- Never claim success based only on intent or an attempted tool call.
- Require explicit approval for payments, publishing, production deployments, deletion, and external messages unless separately authorized by a clear policy.
- Isolate agent workspaces; restrict credentials; record audit events; set spending and execution limits.
- Dormant agents should not consume model tokens or resources.

## Technical integration strategy
- First import and baseline-test upstream OpenMausBot without modifying core behavior.
- Inspect existing agent schemas, orchestration, local harness, UI components, permissions and persistence.
- Add Revona domain models as adapters and migrations rather than invasive rewrites.
- Introduce organization/workspace, department, role, agent-template, task and approval models.
- Add human-readable response rendering while retaining technical logs for debugging.
- Build model-provider adapters only after verifying engine compatibility.

## First-release acceptance criteria
- A nontechnical user can complete onboarding without editing prompts or code.
- Onboarding produces an editable profile, proposed organization and usable starter agents.
- Chief of Staff can delegate a test task to a specialist and show traceable status.
- Every status label matches actual task execution.
- No raw developer log is shown in the default conversation.
- Sensitive actions request approval; rejected actions do not execute.
- Keyboard, mobile-width layouts and reduced-motion mode remain usable.
- Upstream baseline build and tests are recorded before modifications.

## Current implementation status
Specification only. Upstream import, build verification, redesigned UI and runtime features are not yet complete.
