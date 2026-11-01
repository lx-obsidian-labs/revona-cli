import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import YAML from "yaml";

test("Revona packaging has independent identity and no upstream update feed", () => {
  execFileSync(process.execPath, ["scripts/generate-revona-builder.mjs"], { stdio: "pipe" });
  const config = YAML.parse(readFileSync(resolve("dist-revona/electron-builder.revona.yml"), "utf8"));
  assert.equal(config.appId, "za.co.lxobsidian.revona");
  assert.equal(config.productName, "Revona Bot");
  assert.equal(config.publish, null);
  assert.equal(config.generateUpdatesFilesForAllChannels, undefined);
  assert.equal(config.nsis.shortcutName, "Revona Bot");
  assert.match(config.nsis.artifactName, /^Revona-Bot-/);
  assert.ok(config.files.includes("!enterprise/**"));
  assert.ok(config.files.includes("!**/enterprise/**"));
  assert.notEqual(config.protocols[0].schemes[0], "openmausbot");
});
