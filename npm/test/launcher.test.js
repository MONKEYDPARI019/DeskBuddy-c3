'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { after, before, describe, test } = require('node:test');

const launcher = require('../lib/launcher');

const KEY = launcher.platformKey() || 'linux-x64';
const VERSION = '9.8.7';

function tmpdir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'deskbuddy-npm-'));
}

function tar() {
  const system = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
  return process.platform === 'win32' && fs.existsSync(system) ? system : 'tar';
}

/** A release folder like GitHub's: the program archive + SHA256SUMS. */
function makeRelease({ corrupt = false, listed = true } = {}) {
  const dir = tmpdir();
  const src = path.join(dir, 'src', 'deskbuddy');
  fs.mkdirSync(path.join(src, '_internal'), { recursive: true });
  fs.writeFileSync(path.join(src, launcher.exeName(KEY)), 'fake program\n');
  fs.writeFileSync(path.join(src, '_internal', 'base_library.zip'), 'x'.repeat(5000));
  const name = launcher.assetName(VERSION, KEY);
  const archive = path.join(dir, name);
  const made = spawnSync(tar(), ['-czf', archive, '-C', path.join(dir, 'src'), 'deskbuddy']);
  assert.equal(made.status, 0, String(made.stderr));
  let sha = crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex');
  if (corrupt) sha = sha.replace(/^./, sha[0] === 'a' ? 'b' : 'a');
  const lines = [`${'0'.repeat(64)}  deskbuddy-c3-c3-v${VERSION}.bin`];
  if (listed) lines.push(`${sha}  ${name}`);
  fs.writeFileSync(path.join(dir, 'SHA256SUMS'), `${lines.join('\n')}\n`);
  return dir;
}

let server;
let baseUrl;
const requests = [];
const releases = {};

before(async () => {
  releases.good = makeRelease();
  releases.corrupt = makeRelease({ corrupt: true });
  releases.unlisted = makeRelease({ listed: false });
  server = http.createServer((req, res) => {
    requests.push(req.url);
    const [, release, file] = req.url.split('/');
    const full = releases[release] && path.join(releases[release], file || '');
    if (!full || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    const data = fs.readFileSync(full);
    res.writeHead(200, { 'content-length': data.length });
    res.end(data);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

function envFor(release, home = tmpdir()) {
  return { DESKBUDDY_HOME: home, DESKBUDDY_DOWNLOAD_BASE: `${baseUrl}/${release}` };
}

describe('names', () => {
  test('platform keys', () => {
    assert.equal(launcher.platformKey('win32', 'x64'), 'win32-x64');
    assert.equal(launcher.platformKey('win32', 'arm64'), 'win32-x64');
    assert.equal(launcher.platformKey('linux', 'x64'), 'linux-x64');
    assert.equal(launcher.platformKey('linux', 'arm64'), 'linux-arm64');
    assert.equal(launcher.platformKey('darwin', 'arm64'), 'darwin-arm64');
    assert.equal(launcher.platformKey('darwin', 'x64'), 'darwin-x64');
    assert.equal(launcher.platformKey('linux', 'ia32'), null);
    assert.equal(launcher.platformKey('freebsd', 'x64'), null);
  });

  test('file names match scripts/build_app.py', () => {
    assert.equal(launcher.assetName('2.1.0', 'win32-x64'), 'deskbuddy-2.1.0-win32-x64.tar.gz');
    assert.equal(launcher.exeName('win32-x64'), 'deskbuddy.exe');
    assert.equal(launcher.exeName('darwin-arm64'), 'deskbuddy');
  });

  test('SHA256SUMS parsing', () => {
    const a = 'a'.repeat(64);
    const B = 'B'.repeat(64);
    const sums = launcher.parseSums(`${a}  one.tar.gz\r\n${B} *two.bin\n# comment\nnot a line\n\n`);
    assert.deepEqual([...sums], [
      ['one.tar.gz', a],
      ['two.bin', 'b'.repeat(64)],
    ]);
  });

  test('download base defaults to the GitHub release of this version', () => {
    assert.equal(
      launcher.downloadBase({}, '2.1.0'),
      'https://github.com/MONKEYDPARI019/DeskBuddy-C3/releases/download/v2.1.0',
    );
    assert.equal(launcher.downloadBase({ DESKBUDDY_DOWNLOAD_BASE: 'http://x/y/' }, '2.1.0'), 'http://x/y');
    assert.equal(launcher.downloadBase({ DESKBUDDY_DOWNLOAD_BASE: 'dist' }, '2.1.0'), path.resolve('dist'));
  });

  test('package, tool and firmware versions agree', (t) => {
    const root = path.join(__dirname, '..', '..');
    const init = path.join(root, 'tool', 'src', 'deskbuddy', '__init__.py');
    const config = path.join(root, 'firmware', 'src', 'config.h');
    if (!fs.existsSync(init) || !fs.existsSync(config)) {
      t.skip('not inside the DeskBuddy-C3 repository');
      return;
    }
    const tool = /^__version__ = "([^"]+)"/m.exec(fs.readFileSync(init, 'utf8'))[1];
    const fw = /#define FW_VERSION\s+"c3-([^"]+)"/.exec(fs.readFileSync(config, 'utf8'))[1];
    assert.equal(launcher.VERSION, tool, 'npm/package.json version vs tool/src/deskbuddy/__init__.py');
    assert.equal(launcher.VERSION, fw, 'npm/package.json version vs FW_VERSION in firmware/src/config.h');
  });
});

describe('ensureInstalled', () => {
  test('downloads, checks, unpacks once, then reuses it', async () => {
    const env = envFor('good');
    const before = requests.length;
    const exe = await launcher.ensureInstalled({ version: VERSION, key: KEY, env });
    assert.equal(exe, path.join(launcher.appDir(env, VERSION, KEY), 'deskbuddy', launcher.exeName(KEY)));
    assert.equal(fs.readFileSync(exe, 'utf8'), 'fake program\n');
    assert.equal(requests.length - before, 2); // SHA256SUMS + the archive
    const again = await launcher.ensureInstalled({ version: VERSION, key: KEY, env });
    assert.equal(again, exe);
    assert.equal(requests.length - before, 2); // nothing downloaded the second time
    const left = fs.readdirSync(path.join(env.DESKBUDDY_HOME, 'app'));
    assert.deepEqual(left, [`${VERSION}-${KEY}`]); // no temporary folders left behind
  });

  test('removes older versions after installing a new one', async () => {
    const env = envFor('good');
    const old = path.join(env.DESKBUDDY_HOME, 'app', `1.0.0-${KEY}`);
    const other = path.join(env.DESKBUDDY_HOME, 'app', '1.0.0-some-other-platform');
    fs.mkdirSync(old, { recursive: true });
    fs.mkdirSync(other, { recursive: true });
    await launcher.ensureInstalled({ version: VERSION, key: KEY, env });
    assert.equal(fs.existsSync(old), false);
    assert.equal(fs.existsSync(other), true);
  });

  test('a checksum mismatch installs nothing', async () => {
    const env = envFor('corrupt');
    await assert.rejects(launcher.ensureInstalled({ version: VERSION, key: KEY, env }), (err) => {
      assert.equal(err.exitCode, 6);
      assert.match(err.message, /checksum/);
      return true;
    });
    assert.deepEqual(fs.readdirSync(path.join(env.DESKBUDDY_HOME, 'app')), []);
  });

  test('a release without this platform says to use pip', async () => {
    await assert.rejects(
      launcher.ensureInstalled({ version: VERSION, key: KEY, env: envFor('unlisted') }),
      (err) => err.exitCode === 5 && /pip install/.test(err.hint),
    );
  });

  test('a missing release is a network error', async () => {
    await assert.rejects(
      launcher.ensureInstalled({ version: VERSION, key: KEY, env: envFor('nope') }),
      (err) => err.exitCode === 5 && /HTTP 404/.test(err.message),
    );
  });

  test('no connection is a network error', async () => {
    const env = { DESKBUDDY_HOME: tmpdir(), DESKBUDDY_DOWNLOAD_BASE: 'http://127.0.0.1:9' };
    await assert.rejects(launcher.ensureInstalled({ version: VERSION, key: KEY, env }), (err) => err.exitCode === 5);
  });

  test('installs from a local release folder (offline)', async () => {
    const env = { DESKBUDDY_HOME: tmpdir(), DESKBUDDY_DOWNLOAD_BASE: releases.good };
    const before = requests.length;
    const exe = await launcher.ensureInstalled({ version: VERSION, key: KEY, env });
    assert.equal(fs.readFileSync(exe, 'utf8'), 'fake program\n');
    assert.equal(requests.length, before); // no network at all
  });

  test('a local folder still checks the checksum', async () => {
    const env = { DESKBUDDY_HOME: tmpdir(), DESKBUDDY_DOWNLOAD_BASE: releases.corrupt };
    await assert.rejects(launcher.ensureInstalled({ version: VERSION, key: KEY, env }), (err) => err.exitCode === 6);
  });

  test('a local folder without SHA256SUMS says what is missing', async () => {
    const env = { DESKBUDDY_HOME: tmpdir(), DESKBUDDY_DOWNLOAD_BASE: tmpdir() };
    await assert.rejects(launcher.ensureInstalled({ version: VERSION, key: KEY, env }), (err) => {
      assert.equal(err.exitCode, 5);
      assert.match(err.message, /SHA256SUMS not found/);
      return true;
    });
  });
});

describe('moveInto', () => {
  test('retries a rename that Windows refuses for a moment', () => {
    const dir = tmpdir();
    fs.mkdirSync(path.join(dir, 'from'));
    fs.writeFileSync(path.join(dir, 'from', 'x'), 'data');
    let calls = 0;
    const flaky = (a, b) => {
      calls += 1;
      if (calls < 3) throw Object.assign(new Error('locked'), { code: 'EPERM' });
      fs.renameSync(a, b);
    };
    launcher.moveInto(path.join(dir, 'from'), path.join(dir, 'to'), { rename: flaky });
    assert.equal(calls, 3);
    assert.equal(fs.readFileSync(path.join(dir, 'to', 'x'), 'utf8'), 'data');
  });

  test('copies when the rename keeps failing', () => {
    const dir = tmpdir();
    fs.mkdirSync(path.join(dir, 'from', 'sub'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'from', 'sub', 'x'), 'data');
    const never = () => {
      throw Object.assign(new Error('locked'), { code: 'EBUSY' });
    };
    launcher.moveInto(path.join(dir, 'from'), path.join(dir, 'to'), { attempts: 2, rename: never });
    assert.equal(fs.readFileSync(path.join(dir, 'to', 'sub', 'x'), 'utf8'), 'data');
  });

  test('other errors are not retried', () => {
    const dir = tmpdir();
    let calls = 0;
    const missing = () => {
      calls += 1;
      throw Object.assign(new Error('gone'), { code: 'ENOENT' });
    };
    assert.throws(() => launcher.moveInto(path.join(dir, 'a'), path.join(dir, 'b'), { rename: missing }), /gone/);
    assert.equal(calls, 1);
  });
});

describe('run', () => {
  test('passes the arguments through and returns the exit code', async () => {
    const env = { ...process.env, DESKBUDDY_BINARY: process.execPath };
    const code = await launcher.run(['-e', 'process.exit(Number(process.argv[1]))', '42'], { env });
    assert.equal(code, 42);
  });

  test('tells the program it was started by the npm launcher', async () => {
    const env = { ...process.env, DESKBUDDY_BINARY: process.execPath };
    const script = 'process.exit(process.env.DESKBUDDY_LAUNCHER === "npm" ? 0 : 3)';
    assert.equal(await launcher.run(['-e', script], { env }), 0);
  });

  test('an unsupported computer gets the pip command', async () => {
    await assert.rejects(launcher.run(['ports'], { env: {}, platform: 'freebsd', arch: 'x64' }), (err) => {
      assert.equal(err.exitCode, 2);
      assert.match(err.hint, /pip install/);
      return true;
    });
  });

  test('main prints errors like the tool and returns their exit code', async () => {
    const write = process.stderr.write;
    let text = '';
    process.stderr.write = (chunk) => {
      text += chunk;
      return true;
    };
    try {
      const old = process.env.DESKBUDDY_BINARY;
      process.env.DESKBUDDY_BINARY = path.join(tmpdir(), 'missing-program');
      const code = await launcher.main(['ports']);
      if (old === undefined) delete process.env.DESKBUDDY_BINARY;
      else process.env.DESKBUDDY_BINARY = old;
      assert.equal(code, 1);
    } finally {
      process.stderr.write = write;
    }
    assert.match(text, /✗ Could not start/);
  });
});
