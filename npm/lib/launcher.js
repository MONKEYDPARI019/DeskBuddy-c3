'use strict';
// The `deskbuddy` command installed by `npm install -g deskbuddy-c3`.
//
// The real tool is a ready-made program (the Python tool packed with PyInstaller, see
// scripts/build_app.py) attached to each GitHub Release. On its first run this launcher downloads
// the one for this computer, checks it against the release's SHA256SUMS, unpacks it into
// ~/.deskbuddy/app/<version>-<platform>/ and from then on just runs it with the same arguments.

const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const REPO = 'MONKEYDPARI019/DeskBuddy-C3';
const VERSION = require('../package.json').version;
const PIP_HINT =
  'Use the Python version instead:\n' +
  'pip install "git+https://github.com/MONKEYDPARI019/DeskBuddy-C3#subdirectory=tool"';

// same exit codes as the tool itself (tool/src/deskbuddy/errors.py)
const EXIT_ERROR = 1;
const EXIT_USAGE = 2;
const EXIT_NETWORK = 5;
const EXIT_INTEGRITY = 6;

// <platform>-<arch> names used in the release file names (scripts/build_app.py)
const SUPPORTED = new Set(['win32-x64', 'linux-x64', 'linux-arm64', 'darwin-arm64', 'darwin-x64']);

class LauncherError extends Error {
  constructor(message, hint = '', exitCode = EXIT_ERROR) {
    super(message);
    this.hint = hint;
    this.exitCode = exitCode;
  }
}

function platformKey(platform = process.platform, arch = process.arch) {
  // Windows on ARM runs x64 programs through its built-in emulation
  const key = platform === 'win32' && arch === 'arm64' ? 'win32-x64' : `${platform}-${arch}`;
  return SUPPORTED.has(key) ? key : null;
}

function exeName(key) {
  return key.startsWith('win32') ? 'deskbuddy.exe' : 'deskbuddy';
}

function assetName(version, key) {
  return `deskbuddy-${version}-${key}.tar.gz`;
}

/** Parse sha256sum output ("<hex>  <name>" per line); ignores anything else. */
function parseSums(text) {
  const sums = new Map();
  for (const line of text.split(/\r?\n/)) {
    const match = /^([0-9a-fA-F]{64}) [ *](.+)$/.exec(line.trim());
    if (match) sums.set(match[2].trim(), match[1].toLowerCase());
  }
  return sums;
}

function homeDir(env = process.env) {
  return env.DESKBUDDY_HOME ? path.resolve(env.DESKBUDDY_HOME) : path.join(os.homedir(), '.deskbuddy');
}

function appDir(env, version, key) {
  return path.join(homeDir(env), 'app', `${version}-${key}`);
}

/** Where the release files come from: the GitHub release, another URL, or a local folder. */
function downloadBase(env, version) {
  const base = env.DESKBUDDY_DOWNLOAD_BASE || `https://github.com/${REPO}/releases/download/v${version}`;
  return isUrl(base) ? base.replace(/\/+$/, '') : path.resolve(base);
}

function isUrl(base) {
  return /^https?:\/\//i.test(base);
}

/** A release file from a local folder (offline installs, CI): its text, or a copy and its sha256. */
function localFile(folder, name) {
  const file = path.join(folder, name);
  if (!fs.existsSync(file)) {
    throw new LauncherError(
      `${file} not found`,
      name === 'SHA256SUMS'
        ? 'DESKBUDDY_DOWNLOAD_BASE must be a folder holding the release files and their SHA256SUMS.'
        : `This release has no ready-made program for your computer.\n${PIP_HINT}`,
      EXIT_NETWORK,
    );
  }
  return file;
}

function copyLocal(source, file) {
  fs.copyFileSync(source, file);
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

async function get(url) {
  let response;
  try {
    response = await fetch(url, { redirect: 'follow' });
  } catch (err) {
    throw new LauncherError(
      `Could not download ${url}`,
      `Check your internet connection and try again. (${err.cause?.code || err.message})`,
      EXIT_NETWORK,
    );
  }
  if (!response.ok) {
    throw new LauncherError(
      `Download failed: ${url} (HTTP ${response.status})`,
      response.status === 404
        ? `This release has no ready-made program for your computer yet.\n${PIP_HINT}`
        : 'GitHub may be busy. Wait a minute and try again.',
      EXIT_NETWORK,
    );
  }
  return response;
}

/** Download `url` into `file`; returns its sha256. Shows progress on a terminal. */
async function downloadTo(url, file, log) {
  const response = await get(url);
  const total = Number(response.headers.get('content-length')) || 0;
  const hash = crypto.createHash('sha256');
  const out = fs.createWriteStream(file);
  let done = 0;
  let shown = -1;
  try {
    for await (const chunk of response.body) {
      hash.update(chunk);
      done += chunk.length;
      if (!out.write(chunk)) await new Promise((resolve) => out.once('drain', resolve));
      const pct = total ? Math.floor((done * 100) / total) : -1;
      if (log.tty && pct !== shown && pct >= 0) {
        shown = pct;
        log.progress(`  ${pct}%  (${(done / 1e6).toFixed(1)} of ${(total / 1e6).toFixed(1)} MB)`);
      }
    }
  } finally {
    await new Promise((resolve) => out.end(resolve));
    if (log.tty && shown >= 0) log.progress(null);
  }
  return hash.digest('hex');
}

function tarCommand() {
  // Windows 10+ ships bsdtar as System32\tar.exe; prefer it over a GNU tar from Git Bash,
  // which would read "C:\..." as a remote host.
  if (process.platform === 'win32') {
    const system = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
    if (fs.existsSync(system)) return system;
  }
  return 'tar';
}

function extract(archive, dest) {
  const result = spawnSync(tarCommand(), ['-xzf', archive, '-C', dest], { encoding: 'utf8' });
  if (result.error || result.status !== 0) {
    const detail = result.error ? result.error.message : (result.stderr || '').trim();
    throw new LauncherError(`Could not unpack ${path.basename(archive)}`, detail || 'tar failed', EXIT_ERROR);
  }
}

function removeQuietly(target) {
  try {
    fs.rmSync(target, { recursive: true, force: true });
  } catch {
    // a program that is still running (Windows) can't be deleted; try again next update
  }
}

/** Remove other versions' copies for this platform, and stale downloads. */
function cleanOld(env, version, key) {
  const root = path.join(homeDir(env), 'app');
  for (const name of fs.readdirSync(root)) {
    const old = name.endsWith(`-${key}`) && name !== `${version}-${key}`;
    if (old || name.startsWith('.download-')) removeQuietly(path.join(root, name));
  }
}

function silentLog() {
  return { tty: false, info() {}, progress() {} };
}

function terminalLog(stream = process.stderr) {
  return {
    tty: Boolean(stream.isTTY),
    info(text) {
      stream.write(`${text}\n`);
    },
    progress(text) {
      stream.write(text === null ? '\n' : `\r${text}`);
    },
  };
}

/** Make sure the program for `version`/`key` is unpacked; returns the path of the executable. */
async function ensureInstalled({ version = VERSION, key, env = process.env, log = silentLog() }) {
  const target = appDir(env, version, key);
  const exe = path.join(target, 'deskbuddy', exeName(key));
  if (fs.existsSync(exe) && fs.existsSync(path.join(target, '.complete'))) return exe;

  const root = path.join(homeDir(env), 'app');
  fs.mkdirSync(root, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(root, '.download-'));
  try {
    const base = downloadBase(env, version);
    const remote = isUrl(base);
    const name = assetName(version, key);
    const sumsText = remote
      ? await (await get(`${base}/SHA256SUMS`)).text()
      : fs.readFileSync(localFile(base, 'SHA256SUMS'), 'utf8');
    const sums = parseSums(sumsText);
    const expected = sums.get(name);
    if (!expected) {
      throw new LauncherError(
        `Release v${version} has no ready-made program for ${key} (${name})`,
        PIP_HINT,
        EXIT_NETWORK,
      );
    }
    log.info(`Getting the DeskBuddy program for ${key} (first run of v${version} only)...`);
    const archive = path.join(tmp, name);
    const actual = remote
      ? await downloadTo(`${base}/${name}`, archive, log)
      : copyLocal(localFile(base, name), archive);
    if (actual !== expected) {
      throw new LauncherError(
        `${name} failed the checksum test (expected ${expected.slice(0, 12)}..., got ${actual.slice(0, 12)}...)`,
        'The download is damaged or was tampered with. Run the command again; if it keeps failing, report it on GitHub.',
        EXIT_INTEGRITY,
      );
    }
    const unpacked = path.join(tmp, 'unpacked');
    fs.mkdirSync(unpacked);
    extract(archive, unpacked);
    if (!fs.existsSync(path.join(unpacked, 'deskbuddy', exeName(key)))) {
      throw new LauncherError(`${name} does not contain deskbuddy/${exeName(key)}`, 'Report this on GitHub.');
    }
    fs.writeFileSync(path.join(unpacked, '.complete'), `${name} ${expected}\n`);
    removeQuietly(target); // an earlier, interrupted unpack
    try {
      fs.renameSync(unpacked, target);
    } catch (err) {
      if (!fs.existsSync(path.join(target, '.complete'))) throw err; // else another run finished first
    }
    log.info(`Installed in ${target}`);
  } finally {
    removeQuietly(tmp);
  }
  try {
    cleanOld(env, version, key);
  } catch {
    // tidying up is optional
  }
  return exe;
}

/** Run the tool with `args` and resolve with its exit code. */
async function run(
  args,
  { env = process.env, platform = process.platform, arch = process.arch, version = VERSION, log } = {},
) {
  let exe = env.DESKBUDDY_BINARY;
  if (!exe) {
    const key = platformKey(platform, arch);
    if (!key) {
      throw new LauncherError(`There is no ready-made DeskBuddy program for ${platform}/${arch}`, PIP_HINT, EXIT_USAGE);
    }
    exe = await ensureInstalled({ version, key, env, log: log || terminalLog() });
  }
  return new Promise((resolve, reject) => {
    const child = spawn(exe, args, { stdio: 'inherit', env: { ...env, DESKBUDDY_LAUNCHER: 'npm' } });
    // Ctrl+C reaches the program directly (same console); the launcher just waits for it
    const ignore = () => {};
    const forward = (signal) => child.kill(signal);
    process.on('SIGINT', ignore);
    process.on('SIGTERM', forward);
    const done = () => {
      process.off('SIGINT', ignore);
      process.off('SIGTERM', forward);
    };
    child.on('error', (err) => {
      done();
      reject(new LauncherError(`Could not start ${exe}`, err.message));
    });
    child.on('exit', (code, signal) => {
      done();
      if (code !== null) resolve(code);
      else resolve(128 + (os.constants.signals[signal] || 1));
    });
  });
}

async function main(argv = process.argv.slice(2)) {
  try {
    return await run(argv);
  } catch (err) {
    if (err instanceof LauncherError) {
      process.stderr.write(`✗ ${err.message}\n`);
      for (const line of String(err.hint).split('\n')) if (line) process.stderr.write(`  -> ${line}\n`);
      return err.exitCode;
    }
    process.stderr.write(`✗ Unexpected error: ${err && err.message}\n`);
    return EXIT_ERROR;
  }
}

module.exports = {
  LauncherError,
  VERSION,
  appDir,
  assetName,
  downloadBase,
  ensureInstalled,
  exeName,
  homeDir,
  main,
  parseSums,
  platformKey,
  run,
};
