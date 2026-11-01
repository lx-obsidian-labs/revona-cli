import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { startupScreenHtml } from "./startup-screen.mjs";

test("Revona startup splash carries the company identity", () => {
  const html = startupScreenHtml("electron/resources/app-icon.png");
  assert.match(html, /<title>Revona Bot<\/title>/);
  assert.match(html, /<h1>Revona Bot<\/h1>/);
  assert.match(html, /LX Obsidian Labs/);
  assert.match(html, /data:image\/png;base64,/);
  assert.doesNotMatch(html, /OpenMaus/i);
});

test("generated desktop icon is a PNG", () => {
  const icon = readFileSync("electron/resources/app-icon.png");
  assert.equal(icon.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
});
