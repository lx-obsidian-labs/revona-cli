#!/usr/bin/env node
// Revona non-UI baseline checks. Run: node scripts/revona-baseline.mjs
// This script only reads files and does not contact providers or modify user data.
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const problems = [];
function requirePath(path) {
  if (!existsSync(resolve(root, path))) problems.push(`Missing: ${path}`);
}
for (const path of ['package.json', 'pnpm-lock.yaml', 'electron/main.mjs', 'server/openmausbot.ts', 'vite.config.ts', 'tsconfig.json']) requirePath(path);
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));
if (pkg.engines?.node !== '>=24') problems.push('Review Node runtime requirement: expected >=24');
if (pkg.packageManager !== 'pnpm@10.33.0') problems.push('Review pnpm version: expected 10.33.0');
for (const script of ['build', 'typecheck', 'test', 'test:electron']) {
  if (!pkg.scripts?.[script]) problems.push(`Missing package script: ${script}`);
}
console.log('Revona foundation baseline (read-only)');
console.log(`Package: ${pkg.name} ${pkg.version}`);
console.log(`Runtime: ${pkg.engines?.node ?? 'unspecified'}; manager: ${pkg.packageManager ?? 'unspecified'}`);
console.log('UI changes: none');
if (problems.length) {
  for (const p of problems) console.error('FAIL:', p);
  process.exitCode = 1;
} else {
  console.log('PASS: structural prerequisites present.');
  console.log('NOT VERIFIED: dependency install, typecheck, tests, desktop launch, data security.');
  console.log('Next: corepack enable && pnpm install --frozen-lockfile && pnpm typecheck && pnpm build && pnpm test:electron');
}
