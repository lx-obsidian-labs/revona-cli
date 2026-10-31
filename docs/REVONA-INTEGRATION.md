# Revona internal customization — phase 1

This branch preserves the imported UI. Revona's initial customization introduces a **separate, tested credential boundary** for future untrusted tool subprocesses.

## Integration contract
Import `revonaToolEnvironment` from `server/revona/credential-boundary.ts` at subprocess launch boundaries that execute untrusted tools. Supply a deliberately reviewed allowlist for any nonsecret environment variables. **This function is not yet wired into every process launcher**, and no security guarantee is implied until each launcher is audited and integrated.

Do not apply this function indiscriminately to provider CLIs: those may legitimately require provider credentials. Distinguish trusted provider adapters from untrusted command/tool execution; use explicit scoped credentials only when required.

## Tests
Run `pnpm exec vitest run server/revona/credential-boundary.test.ts`. The repository's CI verification should also include this test explicitly.

## Next tasks
- Enumerate all `spawn`, `exec`, and agent tool subprocess paths.
- Classify trusted versus untrusted execution and integrate the boundary only at the correct sites.
- Audit local credential persistence and migration without losing existing settings.
- Test deny/revoke and process restart behavior.
- Preserve existing React components and Electron layouts.
