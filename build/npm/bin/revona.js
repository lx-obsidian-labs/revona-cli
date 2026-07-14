#!/usr/bin/env node

/**
 * Revona CLI — bin wrapper.
 * Invokes the platform-specific PyInstaller binary downloaded at install time.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const BINARY_DIR = path.join(__dirname, '..', 'binary');
const BINARY_NAME = process.platform === 'win32' ? 'revona.exe' : 'revona';
const BINARY_PATH = path.join(BINARY_DIR, BINARY_NAME);

if (!fs.existsSync(BINARY_PATH)) {
  console.error('');
  console.error('  \x1b[31mRevona CLI binary not found.\x1b[0m');
  console.error('');
  console.error('  Run \x1b[33mnpm install\x1b[0m to download the binary for your platform.');
  console.error('  If the install step failed, check:');
  console.error('    - Your platform is supported (Windows/macOS/Linux, x64/arm64)');
  console.error('    - You have a working internet connection');
  console.error('    - GitHub Releases are accessible');
  console.error('');
  process.exit(1);
}

const args = process.argv.slice(2);
const child = spawn(BINARY_PATH, args, {
  stdio: 'inherit',
  env: { ...process.env },
});

child.on('exit', (code) => {
  process.exit(code ?? 0);
});

child.on('error', (err) => {
  console.error(`\x1b[31mFailed to launch Revona CLI: ${err.message}\x1b[0m`);
  process.exit(1);
});
