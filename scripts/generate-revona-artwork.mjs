import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { Resvg } from "@resvg/resvg-js";

const svg = readFileSync("assets/revona/revona-mark.svg", "utf8");
const render = (size) => Buffer.from(new Resvg(svg, { fitTo: { mode: "width", value: size } }).render().asPng());
const sizes = [16, 24, 32, 48, 64, 128, 256];
const pngs = sizes.map(render);
const header = Buffer.alloc(6 + sizes.length * 16);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
for (let i = 0; i < sizes.length; i++) {
  const at = 6 + i * 16;
  header.writeUInt8(sizes[i] === 256 ? 0 : sizes[i], at);
  header.writeUInt8(sizes[i] === 256 ? 0 : sizes[i], at + 1);
  header.writeUInt16LE(1, at + 4);
  header.writeUInt16LE(32, at + 6);
  header.writeUInt32LE(pngs[i].length, at + 8);
  header.writeUInt32LE(offset, at + 12);
  offset += pngs[i].length;
}
mkdirSync("build", { recursive: true });
mkdirSync("electron/resources", { recursive: true });
mkdirSync("public", { recursive: true });
writeFileSync("build/icon.ico", Buffer.concat([header, ...pngs]));
writeFileSync("electron/resources/app-icon.png", render(512));
writeFileSync("public/app-icon-192.png", render(192));
writeFileSync("public/app-icon-512.png", render(512));
writeFileSync("public/apple-touch-icon.png", render(180));
writeFileSync("public/app-icon.svg", svg);
console.log("Generated Revona Bot Windows ICO, Electron PNG and web icons.");
