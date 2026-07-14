/**
 * Revona CLI — build script.
 * Runs PyInstaller and packages the binary for the current platform.
 *
 * Usage: node build.js [--version=X.X.X]
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const VERSION = process.env.REVONA_VERSION || '1.0.0';
const PKG = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf-8'));

function getPlatformTag() {
  const os = { win32: 'windows', darwin: 'macos', linux: 'linux' }[process.platform] || process.platform;
  const arch = { x64: 'x86_64', arm64: 'aarch64' }[process.arch] || process.arch;
  return `${os}-${arch}`;
}

function run(cmd) {
  console.log(`\n  \x1b[36m>\x1b[0m ${cmd}`);
  execSync(cmd, { stdio: 'inherit', cwd: path.join(__dirname, '..') });
}

async function build() {
  const platformTag = getPlatformTag();
  const archiveName = `revona-${platformTag}`;
  const outDir = path.join(__dirname, 'dist');
  const binaryName = process.platform === 'win32' ? 'revona.exe' : 'revona';

  console.log('');
  console.log(`  \x1b[36mBuilding Revona CLI v${VERSION} for ${platformTag}\x1b[0m`);
  console.log('');

  fs.mkdirSync(outDir, { recursive: true });

  // Step 1: Install Python deps
  run('pip install -r requirements.txt');
  run('pip install pyinstaller');

  // Step 2: Run PyInstaller
  run('pyinstaller --clean --noconfirm build/revona.spec');

  // Step 3: Copy binary to dist
  const pyinstallerDist = path.join(__dirname, '..', 'dist', binaryName);
  const outBinary = path.join(outDir, binaryName);
  if (fs.existsSync(pyinstallerDist)) {
    fs.copyFileSync(pyinstallerDist, outBinary);
  }

  // Step 4: Copy bundled data dirs
  for (const dir of ['Skills', 'Blueprints', 'Accelerators', 'AI', '.user']) {
    const src = path.join(__dirname, '..', dir);
    const dst = path.join(outDir, dir);
    if (fs.existsSync(src)) {
      fs.cpSync(src, dst, { recursive: true });
    }
  }

  // Step 5: Create archive
  console.log(`\n  \x1b[34m◇\x1b[0m Creating archive: ${archiveName}`);
  const cwd = process.cwd();
  process.chdir(outDir);

  if (process.platform === 'win32') {
    run(`powershell -Command "Compress-Archive -Path * -DestinationPath '${archiveName}.zip' -Force"`);
  } else {
    run(`tar -czf ${archiveName}.tar.gz *`);
  }

  process.chdir(cwd);

  // Step 6: Verify
  const archivePath = path.join(outDir, process.platform === 'win32' ? `${archiveName}.zip` : `${archiveName}.tar.gz`);
  const stats = fs.statSync(archivePath);
  console.log(`\n  \x1b[32m✓\x1b[0m Built: ${archivePath} (${(stats.size / 1024 / 1024).toFixed(1)} MB)`);
  console.log('');
}

build().catch((err) => {
  console.error(`\x1b[31mBuild failed: ${err.message}\x1b[0m`);
  process.exit(1);
});
