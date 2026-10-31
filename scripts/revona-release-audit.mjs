#!/usr/bin/env node
// Read-only release gate. Default mode reports blockers without breaking foundation CI.
// Use --strict before distributing a Revona installer.
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const file = (name) => readFileSync(resolve(root, name), "utf8");
const blockers = [];
const check = (ok, message) => { if (!ok) blockers.push(message); };

for (const required of ["LICENSE", "NOTICE", "LICENSING.md", "REVONA.md", "electron-builder.yml"]) {
  check(existsSync(resolve(root, required)), `Missing required release document: ${required}`);
}
if (existsSync(resolve(root, "electron-builder.yml"))) {
  const builder = file("electron-builder.yml");
  check(/^appId:\s*com\.(?!openmausbot\.)[\w.-]+/m.test(builder),
    "Electron appId still uses upstream identity or is missing");
  check(/^productName:\s*Revona(?: Bot)?\s*$/m.test(builder),
    "Electron productName is not Revona");
  check(!/^\s*owner:\s*milind-soni\s*$/m.test(builder),
    "Auto-update publisher still targets upstream GitHub account");
  check(!/^\s*repo:\s*OpenMausBot\s*$/m.test(builder),
    "Auto-update repository still targets upstream releases");
  check(!/^artifactName:\s*OpenMausBot/m.test(builder),
    "Installer artifact name still identifies upstream");
  check(/from:\s*NOTICE/.test(builder) && /from:\s*LICENSE/.test(builder),
    "Installer does not explicitly bundle upstream LICENSE and NOTICE");
}
if (existsSync(resolve(root, "package.json"))) {
  const pkg = JSON.parse(file("package.json"));
  check(pkg.name !== "openmausbot", "Package still uses upstream name");
  check(!String(pkg.homepage ?? "").includes("openmausbot"),
    "Package homepage still points to upstream");
}
check(!existsSync(resolve(root, "enterprise")),
  "Separately licensed enterprise/ directory is present: exclude from commercial distribution");

const output = {
  project: "Revona Bot",
  releaseReady: blockers.length === 0,
  blockerCount: blockers.length,
  blockers,
  note: "Passing these static checks does not certify third-party licenses, security, or runtime behavior.",
};
process.stdout.write(JSON.stringify(output, null, 2) + "\n");
if (process.argv.includes("--strict") && blockers.length) process.exitCode = 1;
