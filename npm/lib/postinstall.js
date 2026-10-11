'use strict';
// Runs after `npm install`: fetch the program now so the first `deskbuddy` command starts at once.
// Never fails the install: if anything goes wrong here, the first run simply tries again.

const { ensureInstalled, platformKey } = require('./launcher');

async function postinstall(env = process.env) {
  const key = platformKey();
  if (env.DESKBUDDY_SKIP_DOWNLOAD || env.DESKBUDDY_BINARY || !key) return false;
  try {
    await ensureInstalled({ key, env });
    return true;
  } catch {
    return false;
  }
}

if (require.main === module) {
  postinstall().then(() => {
    process.exitCode = 0;
  });
}

module.exports = { postinstall };
