# Revona Bot branding audit

Product: Revona Bot
Company: LX Obsidian Labs
Official website: https://www.lxobsidianportal.co.za/

## Applied
- Electron Builder's isolated Revona packaging configuration sets the product name, app ID, installer filename and shortcut.
- HTML title and installable web manifest use Revona Bot.
- Desktop startup and recovery messages use Revona Bot.
- Original layout remains unchanged.

## Still required before claiming complete branding
- Replace or redesign visual icons and splash artwork; ensure new artwork is owned or properly licensed.
- Audit renderer strings, menus, About, settings, onboarding, notifications and user-facing URLs for upstream branding.
- Distinguish user-facing names from internal protocol, storage, migration, import and API identifiers. Never bulk-replace internal identifiers without compatibility testing.
- Audit Windows executable metadata, installer UI, uninstall entries, deep links and taskbar icon on a packaged build.
- Preserve Apache-2.0 LICENSE, NOTICE, third-party notices and upstream attribution; do not remove legal attribution to make the product look independently authored.
- Review separately licensed enterprise components and bundled output before any redistribution.
- Confirm the LX Obsidian Labs website link appears in the actual application UI.

Status: partial implementation, not release approval.
