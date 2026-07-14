#!/usr/bin/env node

/**
 * Revona CLI — install script.
 *
 * Detects platform, downloads the correct PyInstaller binary from
 * GitHub Releases, and places it in the `binary/` directory.
 *
 * Environment variables:
 *   REVONA_VERSION   — version to download (default: reads package.json)
 *   REVONA_DRY_RUN   — skip download, just report what would happen
 *   NODE_TLS_REJECT_UNAUTHORIZED — SSL verification (default: 0 for self-signed)
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { createHash } = require('crypto');

// ---- Config ------------------------------------------------------------

const PKG = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'package.json'), 'utf-8')
);
const VERSION = process.env.REVONA_VERSION || PKG.version;
const DRY_RUN = process.env.REVONA_DRY_RUN === 'true';

const REPO = 'lx-obsidian/revona-cli';
const BASE_URL = `https://github.com/${REPO}/releases/download/v${VERSION}`;

function getPlatform() {
  const os = process.platform;
  const arch = process.arch;
  const osMap = { win32: 'windows', darwin: 'macos', linux: 'linux' };
  const archMap = { x64: 'x86_64', arm64: 'aarch64' };
  const resolvedOs = osMap[os];
  const resolvedArch = archMap[arch];
  if (!resolvedOs || !resolvedArch) {
    throw new Error(
      `Unsupported platform: ${os} ${arch}. Supported: windows/macos/linux × x86_64/aarch64`
    );
  }
  return { os: resolvedOs, arch: resolvedArch };
}

function getAssetName(os, arch) {
  const ext = os === 'windows' ? '.zip' : '.tar.gz';
  return `revona-${os}-${arch}${ext}`;
}

function getBinaryName() {
  return process.platform === 'win32' ? 'revona.exe' : 'revona';
}

// ---- Download helpers --------------------------------------------------

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    console.log(`  \x1b[34m↓\x1b[0m Downloading ${url}`);
    https.get(url, { rejectUnauthorized: false }, (res) => {
      if (res.statusCode >= 400) {
        reject(new Error(`HTTP ${res.statusCode}: ${res.statusMessage}`));
        return;
      }
      const total = parseInt(res.headers['content-length'] || '0', 10);
      let downloaded = 0;
      res.on('data', (chunk) => {
        downloaded += chunk.length;
        if (total > 0) {
          const pct = ((downloaded / total) * 100).toFixed(1);
          process.stdout.write(`\r  \x1b[34m↓\x1b[0m Downloading... ${pct}%`);
        }
      });
      res.pipe(file);
      file.on('finish', () => {
        process.stdout.write('\n');
        file.close();
        resolve(dest);
      });
    }).on('error', (err) => {
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

function extractZip(zipPath, destDir) {
  return new Promise((resolve, reject) => {
    const AdmZip = require('adm-zip');
    try {
      const zip = new AdmZip(zipPath);
      zip.extractAllTo(destDir, true);
      resolve(destDir);
    } catch (err) {
      reject(err);
    }
  });
}

function extractTarGz(tarPath, destDir) {
  return new Promise((resolve, reject) => {
    const { createInflate } = zlib;
    const tar = require('tar');
    fs.createReadStream(tarPath)
      .pipe(createInflate())
      .pipe(
        tar.extract({ cwd: destDir, strip: 1 })
      )
      .on('finish', () => resolve(destDir))
      .on('error', reject);
  });
}

// ---- Install -----------------------------------------------------------

async function install() {
  console.log('');
  console.log(`  \x1b[36mRevona CLI v${VERSION}\x1b[0m`);
  console.log(`  \x1b[2mInstalling for ${process.platform} ${process.arch}\x1b[0m`);
  console.log('');

  const { os, arch } = getPlatform();
  const assetName = getAssetName(os, arch);
  const binaryName = getBinaryName();

  const binaryDir = path.join(__dirname, 'binary');
  const assetPath = path.join(binaryDir, assetName);
  const binaryPath = path.join(binaryDir, binaryName);

  // Create binary dir
  fs.mkdirSync(binaryDir, { recursive: true });

  // Check if already installed
  if (fs.existsSync(binaryPath)) {
    console.log(`  \x1b[32m✓\x1b[0m ${binaryName} already installed at ${binaryPath}`);
    console.log('');
    return;
  }

  if (DRY_RUN) {
    console.log(`  \x1b[33m[DRY RUN]\x1b[0m Would download: ${BASE_URL}/${assetName}`);
    console.log(`  \x1b[33m[DRY RUN]\x1b[0m Would extract to: ${binaryDir}`);
    console.log('');
    return;
  }

  // Download
  const url = `${BASE_URL}/${assetName}`;
  try {
    await download(url, assetPath);
  } catch (err) {
    console.error(`  \x1b[31m✗ Download failed: ${err.message}\x1b[0m`);
    console.error('');
    console.error('  Possible causes:');
    console.error(`    - Release v${VERSION} does not exist on GitHub`);
    console.error('    - No internet connection');
    console.error('    - Binary for this platform has not been built yet');
    console.error('');
    console.error('  Build it yourself: https://github.com/lx-obsidian/revona-cli');
    console.error('');
    process.exit(1);
  }

  // Extract
  console.log(`  \x1b[34m◇\x1b[0m Extracting...`);
  try {
    if (os === 'windows') {
      await extractZip(assetPath, binaryDir);
    } else {
      await extractTarGz(assetPath, binaryDir);
    }
  } catch (err) {
    console.error(`  \x1b[31m✗ Extraction failed: ${err.message}\x1b[0m`);
    process.exit(1);
  }

  // Make executable on Unix
  if (process.platform !== 'win32') {
    fs.chmodSync(binaryPath, 0o755);
  }

  // Clean up archive
  fs.unlinkSync(assetPath);

  // Verify
  if (!fs.existsSync(binaryPath)) {
    console.error(`  \x1b[31m✗ Binary not found after extraction: ${binaryPath}\x1b[0m`);
    process.exit(1);
  }

  console.log(`  \x1b[32m✓\x1b[0m Installed: ${binaryPath}`);
  console.log(`  \x1b[2m  Run \x1b[36mrevona --help\x1b[0m \x1b[2mto get started\x1b[0m`);
  console.log('');
}

install().catch((err) => {
  console.error(`\x1b[31mInstall failed: ${err.message}\x1b[0m`);
  process.exit(1);
});
