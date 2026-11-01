// Generate a separate, non-publishing Windows packaging configuration.
// This does not modify the upstream builder config or enable distribution.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import YAML from "yaml";

const root = process.cwd();
const source = YAML.parse(readFileSync(resolve(root, "electron-builder.yml"), "utf8"));
const config = {
  ...source,
  appId: "za.co.lxobsidian.revona",
  productName: "Revona Bot",
  artifactName: "Revona-Bot-${version}-${arch}.${ext}",
  protocols: [{ name: "Revona Bot", schemes: ["revona"] }],
  // Do not publish or generate update metadata targeting upstream releases.
  publish: null,
  generateUpdatesFilesForAllChannels: false,
  files: [...(source.files ?? []), "!enterprise/**", "!**/enterprise/**"],
  extraResources: source.extraResources,
  nsis: {
    ...source.nsis,
    shortcutName: "Revona Bot",
    artifactName: "Revona-Bot-${version}-setup.${ext}",
  },
};
if (config.publish !== null || config.appId === source.appId) {
  throw new Error("Revona packaging must not reuse upstream identity or updater");
}
const output = resolve(root, "dist-revona", "electron-builder.revona.yml");
mkdirSync(resolve(root, "dist-revona"), { recursive: true });
writeFileSync(output, YAML.stringify(config));
console.log("Generated non-publishing Revona packaging config:", output);
console.log("Note: packaged runtime updater and OSS-only content still require verification.");
