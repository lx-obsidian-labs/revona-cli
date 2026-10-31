# Revona Bot

**A desktop AI-agent workspace by LX Obsidian Labs.**

**Company website:** https://www.lxobsidianportal.co.za/  
**Project source:** https://github.com/lx-obsidian-labs/revona-cli

> Development preview. Revona is not yet approved for commercial release or end-user installation. The application currently retains substantial upstream OpenMausBot branding and behavior while customization proceeds.

## What Revona is becoming

Revona is designed as a local desktop workspace for conversations with AI agents, supervised task execution, and connected tools. The interface should be clear, consistent and visibly owned by LX Obsidian Labs. Existing UI components are preserved during the current backend-first customization phase.

## Developer quick start

Requirements: Node.js 24 or later and pnpm 10.33.0. Use the `import/openmausbot-base` development branch.

```bash
corepack enable
pnpm install --frozen-lockfile
pnpm typecheck
pnpm check:electron
pnpm exec vitest run server/revona/credential-boundary.test.ts
pnpm build
pnpm test:electron
```

For local development, see the upstream instructions in `README.md` and scripts in `package.json`. These commands validate source code but do not constitute Windows installation or full end-to-end agent verification.

## Current customization state

- Upstream foundation imported and its baseline CI established.
- Revona credential-filtering module and regression tests added.
- Live agent subprocess integration, settings migration, packaging, visual rebranding and Windows smoke tests remain open.
- The UI is intentionally unchanged pending coordinated design work.

## Quality and release requirements

- TypeScript, Electron checks, production build, and relevant unit tests must pass on every change.
- Validate startup, provider login, tool permission approvals/denials, agent execution, restart persistence and installer/uninstaller behavior on Windows.
- Keep error reporting actionable and redact credentials from logs.
- Preserve upstream license notices and review the separate `enterprise/` license and bundled third-party components before distribution.
- See `docs/REVONA-COMMERCIAL-REVIEW.md` and `docs/REVONA-INTEGRATION.md`.

## Ownership and attribution

Revona is developed by **LX Obsidian Labs**. Its current source is derived from **OpenMausBot**, originally by Milind Soni. Preserve the upstream license and required attribution. LX Obsidian Labs does not claim authorship of the original upstream code.

**Official website:** https://www.lxobsidianportal.co.za/
