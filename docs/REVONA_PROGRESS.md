# Revona Bot desktop — development and release gate

**Status (2026-11-09): development candidate, not production-ready.**

This branch is the Electron/React Revona workforce prototype based on OpenMausBot. The repository's `main` branch is a separate Python CLI project. Do not treat CLI smoke tests as evidence that the desktop app works.

## Evidence

- Last verified desktop commit: `fe3f3619762a039cada262da8de1bb028259d315`.
- [Foundation verification](https://github.com/lx-obsidian-labs/revona-cli/actions/runs/42005126814), [Windows compatibility](https://github.com/lx-obsidian-labs/revona-cli/actions/runs/42005126897), and [unsigned Windows installer candidate](https://github.com/lx-obsidian-labs/revona-cli/actions/runs/42005126915) passed on 2026-11-05.
- The installer artifact is an **unsigned candidate**; workflow success is not evidence of successful installation on a real Windows machine.
- Revona onboarding can propose a team, provision agent profiles through the existing bot API, attempt Chief designation, and navigate to the Chief. A delegation **preview** exists. Do not describe it as proof of live delegation.
- The upstream OpenMausBot README and other inherited identity remain on this branch; their external download links are **not Revona installers**.

## Required release gates (not yet verified)

- [ ] Resolve product naming, Electron metadata, installer naming and update publisher; confirm no upstream auto-update feed is used.
- [ ] Review OpenMausBot and third-party license obligations; exclude separately licensed enterprise content from distribution.
- [ ] Test onboarding, interrupted provisioning, rollback failure and duplicate prevention against the real API.
- [ ] Confirm Chief designation persists and native `coordinate_bots` delegates to specialists with returned results.
- [ ] Validate model setup, provider authentication and permission boundaries without exposing secrets.
- [ ] Verify approvals for external messages, publishing, financial actions and credential access.
- [ ] Verify desktop persistence, restart, error recovery and Windows installation on a clean machine.
- [ ] Run typecheck, automated tests, production build, Electron tests, and Windows CI on the **same release commit**.
- [ ] Publish a versioned, accurately labeled Revona test release with checksums, limitations and installation instructions.

## Engineering next actions

1. Audit the current branch against this gate and fix real defects, not just UI.
2. Add end-to-end evidence for Chief-to-specialist execution and provisioning failure recovery.
3. Complete Revona-specific identity and distribution checks.
4. Build and test a Windows release candidate; publish only after the security and license gates are satisfied.

**Policy:** Never claim that simulated workflows, passing CI or an unsigned installer prove commercial readiness. Never use upstream OpenMausBot release assets as Revona downloads.
