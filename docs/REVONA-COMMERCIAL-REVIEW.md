# Revona: commercial distribution and privacy release gate

Status: **NOT CLEARED FOR COMMERCIAL RELEASE**. This is an engineering checklist, not legal advice.

## Upstream attribution and licensing
- OpenMausBot identifies its open-source portion as Apache License 2.0. Preserve the LICENSE, required NOTICE information, attribution, and modification notices when redistributing.
- The upstream README expressly excludes `enterprise/` from Apache 2.0 and refers to `enterprise/LICENSE`. Do **not** ship, monetize, or relicense enterprise components until their separate terms have been reviewed and permission established. Prefer removing the directory from a commercial build unless a valid grant exists.
- Audit `third_party/`, native runtime assets, bundled fonts, dependency license manifests, and transitive dependencies. Include all required notices in installers and distribution archives.
- Replace upstream trademarks, application identifiers, update endpoints, package names and branding only after checking references and avoiding misleading affiliation claims.
- Check third-party providers' current commercial, API, data processing, and resale terms independently (including Composio, Boat, hosted model vendors, voice services, and agent CLIs). Apache licensing of the host does not grant rights to resell their services.

## Privacy and security gates
- Map all user data: conversations, tool traces, attachments, keys, local computer permissions, remote computers, telemetry, and backups.
- The upstream README describes local CLI setup API keys stored as plaintext in a private config file. Treat this as a release blocker until Revona's credential storage is audited and protected using an OS credential vault or equivalent encryption at rest with controlled key management.
- Keep sensitive tokens out of renderer state, logs, analytics, exports, support bundles, and error reports. Redact secrets in test fixtures.
- Require explicit permission for shell execution, destructive file changes, external sends, computer control, and paid API actions; test deny, timeout, and revocation paths.
- Document data retention, export, deletion, local versus cloud processing, subprocess access, remote transfer destinations, and telemetry opt-in.
- Review applicable South African POPIA obligations, plus GDPR/other jurisdictions if serving their residents. Publish privacy notices and operator/provider roles before onboarding paying customers.

## Monetization gates
- Specify the product sold, whether model/provider subscriptions are included, payment/refund/cancellation rules, taxes, support commitments, and service limitations.
- Verify distribution and commercial-use rights for every packaged component and provider; retain a dated evidence register.
- Do not advertise end-to-end encryption, zero collection, fully local execution, or unlimited usage without implementation and tests demonstrating each claim.

## Required technical evidence
1. CI green for frozen install, typecheck, Electron syntax, production build, and Electron tests.
2. Successful Windows installation, startup, model connection, chat, approval/denial, restart, and uninstall smoke tests.
3. Settings round-trip tests and persistence migration tests, including malformed and old config handling.
4. Security review of credential storage, auth/session boundaries, connector scopes, logging and exported data.
5. Signed-off licensing inventory and user-facing legal documents before paid release.

**UI constraint:** Do not redesign the interface in this phase. Internal changes must maintain existing API contracts.
