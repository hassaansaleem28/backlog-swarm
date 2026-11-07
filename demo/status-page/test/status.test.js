const test = require('node:test');
const assert = require('node:assert/strict');
const { statusLines } = require('../src/status');

test('one line per service, with its age', () => {
  const now = 1_000_000;
  assert.deepEqual(
    statusLines(
      [
        { service: 'api', ok: true, checkedAt: now - 60_000 },
        { service: 'billing', ok: false, checkedAt: now - 5_000 },
      ],
      now,
    ),
    ['🟢 api: operational (checked 1 minute ago)', '🔴 billing: down (checked 5 seconds ago)'],
  );
});
