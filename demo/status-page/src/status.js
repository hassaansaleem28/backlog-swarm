const ms = require('ms');

// Turns the latest health checks into the lines shown on the status page.
function statusLines(checks, now = Date.now()) {
  return checks.map(({ service, ok, checkedAt }) => {
    const age = ms(Math.max(0, now - checkedAt), { long: true });
    return `${ok ? '🟢' : '🔴'} ${service}: ${ok ? 'operational' : 'down'} (checked ${age} ago)`;
  });
}

module.exports = { statusLines };
