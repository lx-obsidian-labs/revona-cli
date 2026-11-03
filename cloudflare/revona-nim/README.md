# Revona onboarding and NVIDIA NIM deployment

## Current state
- `src/components/onboarding/RevonaOnboarding.tsx`: guided conversational onboarding and a review/export of a proposed workforce plan. **Not yet mounted in App.tsx.** It does not provision agents or call an LLM.
- `src/lib/revona-workforce.ts`: deterministic workforce templates; all permissions remain off.
- `cloudflare/revona-nim/src/index.ts`: non-streaming OpenAI-compatible chat-completions proxy for NVIDIA NIM. **Not yet deployed or integrated with the desktop provider configuration.**

## Worker deployment
From `cloudflare/revona-nim`:
```sh
npx wrangler secret put NVIDIA_NIM_API_KEY
npx wrangler secret put REVONA_CLIENT_TOKEN
npx wrangler deploy
```
Set `NVIDIA_NIM_MODEL` to a model currently available to your NVIDIA account. The example model is not a guaranteed free entitlement; confirm current NVIDIA NIM availability and quotas. Never commit the API key or put it in `wrangler.jsonc`.

### Security caveat — must resolve before production
`REVONA_CLIENT_TOKEN` is only a temporary shared-token gate for private development. **Do not embed this token in a distributed desktop application**: it can be extracted and used by anyone. Production requires per-user authenticated sessions, server-side authorization, quotas, rate limits, abuse controls, token revocation and a secure desktop-to-Worker auth flow. Keep the Worker private until then. The NVIDIA API key remains a Worker secret.

## Integration work
1. Mount `RevonaOnboarding` from the app shell, with an explicit user-triggered entry point.
2. Wire reviewed workforce plans into the existing bot/team creation APIs; require confirmation before creating each role.
3. Integrate a Revona provider adapter with the existing model picker, using authenticated Worker requests. Do not force a default for users with existing provider settings.
4. Add streaming support only after a tested contract with the existing agent runtime.
5. Add automated tests for input validation, auth, quotas, onboarding progression, creation/retry behavior, and Windows runtime.
6. Build a fresh Windows test installer only after those checks pass.

## Cost
NVIDIA's free developer access may have rate and usage limits. Cloudflare Workers also have plan quotas. This design cannot guarantee unlimited zero-cost usage.
