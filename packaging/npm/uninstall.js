#!/usr/bin/env node

/**
 * Revona CLI — uninstall script.
 * Removes downloaded binary to free disk space.
 */

const fs = require('fs');
const path = require('path');

const binaryDir = path.join(__dirname, 'binary');

if (fs.existsSync(binaryDir)) {
  fs.rmSync(binaryDir, { recursive: true, force: true });
  console.log(`  \x1b[32m✓\x1b[0m Removed ${binaryDir}`);
} else {
  console.log(`  \x1b[2mNo binary directory found.\x1b[0m`);
}
